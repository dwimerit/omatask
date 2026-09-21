"""Versioned, lossless JSON transfer. Import is validated before an atomic merge."""
import json
import sqlite3
from .persistence import Store, TABLES, MIGRATIONS
from .timeutil import instant, stamp
from .recurrence import Rule, occurrence
from .daily_window import clock_fire

FORMAT = 'omatask-1'


def export_data(store):
    # Snapshot spans all tables, even with concurrent writers.
    store.db.execute('BEGIN')
    try:
        result = {'format':FORMAT, 'schema':len(MIGRATIONS), 'tables':{
            table:[dict(row) for row in store.db.execute(f'SELECT * FROM {table} ORDER BY id')]
            for table in TABLES}}
        store.db.execute('COMMIT')
        return result
    except BaseException:
        store.db.execute('ROLLBACK')
        raise


def _insert(store, tables):
    for table in TABLES:
        columns = [r['name'] for r in store.db.execute(f'PRAGMA table_info({table})')]
        rows = tables[table]
        if not isinstance(rows,list):raise ValueError('Table must be an array')
        for row in rows:
            if not isinstance(row,dict) or set(row) != set(columns):
                raise ValueError(f'Invalid columns in {table}')
            if not isinstance(row['id'],str) or not row['id']:
                raise ValueError('ID must be a non-empty string')
            # Every persisted instant uses the same UTC representation for SQL ordering.
            row = dict(row)
            for key in ('created_at','due_at','completed_at','anchor_at','fire_at','delivered_at','reopened_at'):
                if row.get(key) is not None:
                    row[key] = stamp(instant(row[key]))
            store.db.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",[row[k] for k in columns])


def import_data(store, data):
    if not isinstance(data,dict) or data.get('format') != FORMAT or data.get('schema') not in (3, len(MIGRATIONS)):
        raise ValueError('Unsupported export format/schema')
    if not isinstance(data.get('tables'),dict) or set(data['tables']) != set(TABLES):
        raise ValueError('Export must include every table')
    staging=Store(':memory:')
    try:
        with staging.transaction():
            _insert(staging,data['tables'])
            for task in staging.all():
                task.validate()
                if task.recurrence:
                    expected = occurrence(instant(task.anchor_at), Rule(**task.recurrence), task.occurrence_index, task.timezone)
                    if expected is None or stamp(expected) != task.due_at:
                        raise ValueError('Current due does not match recurrence')
                history = staging.db.execute('SELECT * FROM occurrences WHERE task_id=?', (task.id,)).fetchall()
                for event in history:
                    if event['sequence'] > task.occurrence_index:
                        raise ValueError('History sequence exceeds current occurrence')
                    snapshot = json.loads(event['subtasks'])
                    old_subtasks = task.subtasks
                    task.subtasks = snapshot
                    task.validate()
                    task.subtasks = old_subtasks
                current = [h for h in history if h['sequence'] == task.occurrence_index and h['reopened_at'] is None]
                if (task.status == 'completed') != bool(current):
                    raise ValueError('Completion history disagrees with task status')
                if current and current[0]['completed_at'] != task.completed_at:
                    raise ValueError('Completion time disagrees with history')
            for rule in staging.db.execute('SELECT * FROM reminder_rules'):
                if rule['kind']=='relative':
                    if int(rule['value']) < 0:raise ValueError('Invalid reminder offset')
                    if not staging.get(rule['task_id']).due_at:raise ValueError('Relative reminder needs due date')
                elif rule['kind']=='clock':
                    task = staging.get(rule['task_id'])
                    if not task.due_at or not task.recurrence or task.recurrence['frequency'] != 'day' or task.recurrence.get('interval',1) != 1:
                        raise ValueError('Daily reminders require daily recurrence')
                    clock_fire(instant(task.due_at), rule['value'], task.timezone)
                else:instant(rule['value'])
            bad=staging.db.execute('''SELECT d.id FROM deliveries d JOIN reminder_rules r ON r.id=d.rule_id
                WHERE d.task_id!=r.task_id''').fetchone()
            if bad:raise ValueError('Delivery rule/task mismatch')
            for delivery in staging.db.execute('SELECT * FROM deliveries'):
                task = staging.get(delivery['task_id'])
                if delivery['sequence'] > task.occurrence_index:
                    raise ValueError('Delivery sequence exceeds current occurrence')
                if (delivery['state'] == 'sent') != (delivery['delivered_at'] is not None):
                    raise ValueError('Delivery state disagrees with delivery timestamp')
                if delivery['state'] == 'pending' and (task.status != 'active' or delivery['sequence'] != task.occurrence_index):
                    raise ValueError('Pending delivery does not belong to active occurrence')
        # Use validated/canonicalized rows, never raw input identifiers in SQL.
        validated=export_data(staging)['tables']
        with store.transaction():
            _insert(store,validated)
    except (sqlite3.Error, KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f'Invalid or conflicting import: {exc}') from exc
    finally:
        staging.close()
    return {'imported':len(data['tables']['tasks'])}


def markdown(store):
    def escape(value):
        for char in ('\\','`','*','_','[',']','#','<','>'):
            value=value.replace(char,'\\'+char)
        return value.replace('\n',' ')
    lines=['# Omatask', '']
    for task in store.all():
        marker='x' if task.status=='completed' else ' '
        lines.append(f'- [{marker}] {escape(task.title)} ({task.status}; {task.priority})')
        lines.append(f'  - ID: {task.id}; due: {task.due_at or "—"}; project: {escape(task.project)}')
        if task.description:lines.append('  - '+escape(task.description))
        if task.tags:lines.append('  - Tags: '+', '.join(escape(t) for t in task.tags))
        if task.recurrence:lines.append('  - Repeat: '+json.dumps(task.recurrence))
        for sub in task.subtasks:
            lines.append(f'  - [{"x" if sub["done"] else " "}] {escape(sub["title"])}')
    return '\n'.join(lines)+'\n'
