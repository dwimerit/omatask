"""Application use cases. Every mutation is atomic; no UI-specific behavior."""
import uuid
import json
from datetime import date as calendar_date, timedelta
from zoneinfo import ZoneInfo
from .domain import Task, PRIORITIES, STATUSES
from .recurrence import Rule, occurrence, final_index
from .timeutil import UTC, now, stamp, instant, system_zone
from . import reminders
from .daily_window import clock_fire


def uid():
    return str(uuid.uuid4())


class Engine:
    def __init__(self, store, zone=None, clock=now):
        self.store, self.zone, self.clock = store, zone or system_zone(), clock
        ZoneInfo(self.zone)

    def add(self, title, description='', priority='normal', due=None, recurrence=None, tags=None, project='', reminder_specs=None):
        due = stamp(due) if due else None
        rule = Rule(**recurrence) if recurrence else None
        if rule and (not due or occurrence(instant(due), rule, 0, self.zone) is None):
            raise ValueError("Recurrence requires a valid first due date within its bounds")
        task = Task(uid(), title.strip(), description, 'active', priority, stamp(self.clock()), due,
                    None, self.zone, rule.to_dict() if rule else None, due)
        task.tags, task.project = sorted(set(tags or [])), project
        with self.store.transaction():
            self.store.save(task, new=True)
            for spec in reminder_specs or []:
                self._remind(task, **spec)
            reminders.ensure_due_reminder(self.store, task)
        return task

    def edit(self, task_id, **changes):
        allowed = {'title', 'description', 'priority', 'due_at', 'recurrence', 'tags', 'project', 'subtasks'}
        if set(changes) - allowed:
            raise ValueError("Unsupported edit fields")
        with self.store.transaction():
            task = self.store.get(task_id)
            previous_due = task.due_at
            schedule_changed = bool({'due_at','recurrence'} & changes.keys())
            if schedule_changed and task.recurrence and task.occurrence_index:
                raise ValueError("A started recurring schedule is immutable; create a new series")
            if schedule_changed and task.status != 'active':
                raise ValueError("Reopen before changing a schedule")
            for key, value in changes.items():
                setattr(task, key, value)
            if 'due_at' in changes:
                task.due_at = stamp(instant(task.due_at)) if task.due_at else None
            if schedule_changed:
                task.anchor_at = task.due_at
                if task.recurrence and (not task.due_at or occurrence(instant(task.anchor_at), Rule(**task.recurrence), 0, task.timezone) is None):
                    raise ValueError("Invalid recurrence start")
                if not task.due_at and self.store.db.execute("SELECT 1 FROM reminder_rules WHERE task_id=? AND ((kind='relative' AND value<>'0') OR kind='clock')", (task.id,)).fetchone():
                    raise ValueError("Cannot remove due date while relative or daily reminders exist")
                if not task.due_at or previous_due != task.due_at:
                    reminders.remove_due_reminder(self.store, task)
            self.store.save(task)
            if schedule_changed:
                rules = self.store.db.execute("SELECT * FROM reminder_rules WHERE task_id=? AND kind='relative'", (task.id,)).fetchall()
                for rule in rules:
                    fire = stamp(instant(task.due_at) - timedelta(seconds=int(rule['value'])))
                    self.store.db.execute("UPDATE deliveries SET fire_at=? WHERE rule_id=? AND sequence=? AND state='pending'", (fire, rule['id'], task.occurrence_index))
                for rule in self.store.db.execute("SELECT * FROM reminder_rules WHERE task_id=? AND kind='clock'", (task.id,)).fetchall():
                    self._validate_daily_rule(task)
                    fire = clock_fire(instant(task.due_at), rule['value'], task.timezone)
                    if fire < instant(task.created_at):
                        self.store.db.execute("DELETE FROM deliveries WHERE rule_id=? AND sequence=? AND state='pending'", (rule['id'], task.occurrence_index))
                    else:
                        delivery = self.store.db.execute('SELECT * FROM deliveries WHERE rule_id=? AND sequence=?', (rule['id'], task.occurrence_index)).fetchone()
                        if delivery is None:
                            reminders.enqueue(self.store, task, fire, rule['id'])
                        elif delivery['state'] == 'pending':
                            self.store.db.execute('UPDATE deliveries SET fire_at=? WHERE id=?', (stamp(fire), delivery['id']))
                reminders.ensure_due_reminder(self.store, task)
        return task

    def done(self, task_id):
        with self.store.transaction():
            task = self.store.get(task_id)
            if task.status != 'active':
                raise ValueError("Only active tasks can be completed")
            completed = stamp(self.clock())
            next_due = occurrence(instant(task.anchor_at), Rule(**task.recurrence), task.occurrence_index+1, task.timezone) if task.recurrence else None
            self.store.db.execute("INSERT INTO occurrences VALUES (?,?,?,?,?,NULL,?)", (uid(), task.id, task.occurrence_index, task.due_at, completed, json.dumps(task.subtasks)))
            self._cancel_pending(task)
            if next_due:
                task.occurrence_index += 1
                task.subtasks = [dict(s, done=False) for s in task.subtasks]
                task.due_at = stamp(next_due)
                reminders.schedule(self.store, task)
            else:
                task.status, task.completed_at = 'completed', completed
            self.store.save(task)
        return task

    def _cancel_pending(self, task):
        self.store.db.execute("UPDATE deliveries SET state='cancelled' WHERE task_id=? AND state='pending'", (task.id,))

    def cancel(self, task_id):
        with self.store.transaction():
            task = self.store.get(task_id)
            if task.status != 'active':
                raise ValueError("Only active tasks can be cancelled")
            task.status = 'cancelled'
            self._cancel_pending(task)
            self.store.save(task)
        return task

    def reopen(self, task_id):
        with self.store.transaction():
            task = self.store.get(task_id)
            if task.status == 'active':
                raise ValueError("Task is already active")
            if task.status == 'completed':
                self.store.db.execute('UPDATE occurrences SET reopened_at=? WHERE task_id=? AND sequence=? AND reopened_at IS NULL',
                                      (stamp(self.clock()), task.id, task.occurrence_index))
            task.status, task.completed_at = 'active', None
            self.store.save(task)
            # Existing cancelled deliveries belong to this occurrence and can resume.
            self.store.db.execute("UPDATE deliveries SET state='pending' WHERE task_id=? AND sequence=? AND state='cancelled'", (task.id, task.occurrence_index))
            existing = self.store.db.execute("SELECT 1 FROM deliveries WHERE task_id=? AND sequence=?", (task.id, task.occurrence_index)).fetchone()
            if not existing:
                reminders.schedule(self.store, task)
        return task

    def delete(self, task_id):
        with self.store.transaction():
            task = self.store.get(task_id)
            self.store.db.execute("DELETE FROM tasks WHERE id=?", (task.id,))
        return {'deleted': task.id}

    def remind(self, task_id, seconds=None, at=None):
        with self.store.transaction():
            task = self.store.get(task_id)
            reminders.remove_due_reminder(self.store, task)
            return self._remind(task, seconds, at)

    @staticmethod
    def _validate_daily_rule(task):
        if not task.due_at or not task.recurrence or task.recurrence['frequency'] != 'day' or task.recurrence.get('interval', 1) != 1:
            raise ValueError('Daily reminder windows require a due date and daily recurrence')

    def _remind(self, task, seconds=None, at=None, local_time=None):
        if sum(value is not None for value in (seconds, at, local_time)) != 1:
            raise ValueError("Specify exactly one reminder: relative duration, absolute time or daily local time")
        if seconds is not None and (type(seconds) is not int or seconds <= 0):
            raise ValueError("Reminder offset must be a positive number of seconds")
        if task.status != 'active':
            raise ValueError("Reminders require an active task")
        if seconds is not None and not task.due_at:
            raise ValueError("Relative reminders need a due date")
        rule_id = uid()
        if local_time is not None:
            self._validate_daily_rule(task)
            fire = clock_fire(instant(task.due_at), local_time, task.timezone)
            kind, value = 'clock', local_time
        else:
            kind, value = ('relative', str(seconds)) if seconds is not None else ('absolute', stamp(at))
            fire = instant(task.due_at)-timedelta(seconds=seconds) if seconds is not None else at
        self.store.db.execute("INSERT INTO reminder_rules VALUES (?,?,?,?)", (rule_id, task.id, kind, value))
        if local_time is None or fire >= instant(task.created_at):
            reminders.enqueue(self.store, task, fire, rule_id)
        return {'reminder_id': rule_id, 'fire_at': stamp(fire)}

    def subtask(self, task_id, action, value):
        with self.store.transaction():
            task = self.store.get(task_id)
            if action == 'add':
                task.subtasks.append({'id': uid(), 'title': value, 'done': False})
            else:
                if not isinstance(value, str) or not value:
                    raise ValueError('Subtask ID must be a non-empty string')
                matches = [s for s in task.subtasks if s['id'].startswith(value)]
                if len(matches) != 1:
                    raise ValueError('Unknown or ambiguous subtask ID')
                sub = matches[0]
                if action == 'delete':
                    task.subtasks.remove(sub)
                elif action in ('done', 'reopen'):
                    sub['done'] = action == 'done'
                else:
                    raise ValueError('Unknown subtask action')
            self.store.save(task)
        return task

    def snooze(self, task_id, value):
        with self.store.transaction():
            task = self.store.get(task_id)
            if task.status != 'active':
                raise ValueError("Snooze requires an active task")
            clock = self.clock()
            fire = reminders.snooze_time(value, task.timezone, clock)
            # Coalesce currently due reminders; later independent reminders remain scheduled.
            self.store.db.execute("UPDATE deliveries SET state='cancelled' WHERE task_id=? AND state='pending' AND fire_at<=?", (task.id, stamp(clock)))
            reminders.enqueue(self.store, task, fire)
        return {'task_id': task.id, 'fire_at': stamp(fire)}

    def list(self, view='all', query=None, status=None, priority=None, due=None, recurring=False, project=None, tag=None):
        if status is not None and status not in STATUSES:
            raise ValueError('Invalid status filter')
        if priority is not None and priority not in PRIORITIES:
            raise ValueError('Invalid priority filter')
        if due is not None:
            calendar_date.fromisoformat(due)
        clock = self.clock().astimezone(ZoneInfo(self.zone))
        today = clock.date()
        results = []
        if view not in ('all','today','tomorrow','upcoming','overdue','completed','recurring'):
            raise ValueError("Unknown view")
        for task in self.store.all():
            date = instant(task.due_at).astimezone(ZoneInfo(self.zone)).date() if task.due_at else None
            wanted = status or ('completed' if view == 'completed' else 'active' if view != 'all' else None)
            if wanted and task.status != wanted or priority and task.priority != priority:
                continue
            if project is not None and task.project != project or tag and tag not in task.tags:
                continue
            if query and query.casefold() not in (task.title+'\n'+task.description).casefold():
                continue
            if (recurring or view == 'recurring') and not task.recurrence:
                continue
            if due and str(date) != due:
                continue
            if view == 'today' and date != today or view == 'tomorrow' and date != today+timedelta(days=1):
                continue
            if view == 'upcoming' and (date is None or not today <= date <= today+timedelta(days=7)):
                continue
            if view == 'overdue' and (not task.due_at or instant(task.due_at) >= clock.astimezone(UTC)):
                continue
            results.append(task)
        return sorted(results, key=lambda t: (-PRIORITIES.index(t.priority), t.due_at or '9999', t.created_at, t.id))

    def show(self, task_id):
        task = self.store.get(task_id)
        history = [dict(r) for r in self.store.db.execute("SELECT * FROM occurrences WHERE task_id=? ORDER BY sequence", (task.id,))]
        result = task.to_dict()
        result.update(history=history, execution_count=len(history), completed_count=sum(h['reopened_at'] is None for h in history), remaining_count=None, next_occurrence=None, final_due=None)
        if task.recurrence:
            rule = Rule(**task.recurrence)
            anchor = instant(task.anchor_at)
            end = final_index(anchor, rule, task.timezone)
            if end is not None:
                result['remaining_count'] = max(0, end+1-result['completed_count'])
                final = occurrence(anchor, rule, end, task.timezone) if end >= 0 else None
                result['final_due'] = stamp(final) if final else None
            if task.status == 'active':
                following = occurrence(anchor, rule, task.occurrence_index+1, task.timezone)
                result['next_occurrence'] = stamp(following) if following else None
        result['subtask_progress'] = {'done': sum(s['done'] for s in task.subtasks), 'total': len(task.subtasks)}
        result['reminders'] = [dict(r) for r in self.store.db.execute("SELECT * FROM reminder_rules WHERE task_id=?", (task.id,))]
        result['daily_reminders'] = sorted(r['value'] for r in result['reminders'] if r['kind'] == 'clock')
        result['deliveries'] = [dict(r) for r in self.store.db.execute("SELECT * FROM deliveries WHERE task_id=? ORDER BY fire_at", (task.id,))]
        return result

    def stats(self):
        tasks = self.store.all()
        return {'tasks': len(tasks),
                'by_status': {s: sum(t.status == s for t in tasks) for s in ('active','completed','cancelled')},
                'by_priority': {p: sum(t.priority == p for t in tasks) for p in PRIORITIES},
                'completed_occurrences': self.store.db.execute('SELECT count(*) FROM occurrences WHERE reopened_at IS NULL').fetchone()[0],
                'overdue': len(self.list('overdue'))}
