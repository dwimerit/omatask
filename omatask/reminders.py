"""Persistent delivery queue, independent of UI and desktop notification backend."""
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo
from .notifications import desktop_notify
from .daily_window import clock_fire
from .timeutil import UTC, now, stamp, instant, duration, wall


def enqueue(store, task, fire_at, rule_id=None):
    store.db.execute("INSERT INTO deliveries VALUES (?,?,?,?,?,'pending',NULL)",
                     (str(uuid.uuid4()), rule_id, task.id, task.occurrence_index, stamp(fire_at)))


def ensure_due_reminder(store, task):
    """Default to the deadline when no explicit reminder has been configured.

    Relative zero is reserved for this automatic rule. Call in a transaction.
    """
    if task.status != 'active' or not task.due_at:
        return False
    if store.db.execute('SELECT 1 FROM reminder_rules WHERE task_id=?', (task.id,)).fetchone():
        return False
    rule_id = str(uuid.uuid4())
    store.db.execute("INSERT INTO reminder_rules VALUES (?,?,'relative','0')", (rule_id, task.id))
    enqueue(store, task, instant(task.due_at), rule_id)
    return True


def remove_due_reminder(store, task):
    """Replacing/clearing the default must keep past delivery history intact."""
    for row in store.db.execute("SELECT id FROM reminder_rules WHERE task_id=? AND kind='relative' AND value='0'", (task.id,)).fetchall():
        store.db.execute("UPDATE deliveries SET rule_id=NULL WHERE rule_id=? AND state='sent'", (row['id'],))
        # Unsent deliveries cascade away with the replaced rule. They must not
        # be revived later by reopen as if they were a snooze.
        store.db.execute('DELETE FROM reminder_rules WHERE id=?', (row['id'],))


def schedule(store, task):
    if ensure_due_reminder(store, task):
        return
    for rule in store.db.execute("SELECT * FROM reminder_rules WHERE task_id=?", (task.id,)):
        if rule['kind'] == 'relative' and task.due_at:
            enqueue(store, task, instant(task.due_at) - timedelta(seconds=int(rule['value'])), rule['id'])
        elif rule['kind'] == 'clock':
            fire = clock_fire(instant(task.due_at), rule['value'], task.timezone)
            # Do not send a burst for hours before the daily goal was created.
            # Outages after creation still use the persistent catch-up queue.
            if fire >= instant(task.created_at):
                enqueue(store, task, fire, rule['id'])
        elif rule['kind'] == 'absolute':
            # An absolute rule is once per task, never once per recurrence.
            exists = store.db.execute("SELECT 1 FROM deliveries WHERE rule_id=?", (rule['id'],)).fetchone()
            if not exists:
                enqueue(store, task, instant(rule['value']), rule['id'])


def snooze_time(value, zone, clock):
    if value not in ("evening", "tomorrow"):
        return clock.astimezone(UTC) + timedelta(seconds=duration(value))
    local = clock.astimezone(ZoneInfo(zone))
    target = local.replace(tzinfo=None, hour=18 if value == 'evening' else 9, minute=0, second=0, microsecond=0)
    if value == 'tomorrow' or target <= local.replace(tzinfo=None):
        target += timedelta(days=1)
    return wall(target, zone)


def dispatch(store, notifier=desktop_notify, clock=None, limit=20):
    """Serialize delivery with CRUD. Crash after notify may duplicate, never silently lose."""
    clock = clock or now()
    # Upgrade tasks created before default deadline reminders were introduced.
    # Preserve explicit reminders, snoozes, and already delivered occurrences.
    with store.transaction():
        legacy = store.db.execute("""SELECT t.id FROM tasks t WHERE t.status='active' AND t.due_at IS NOT NULL
            AND NOT EXISTS (SELECT 1 FROM reminder_rules r WHERE r.task_id=t.id)
            AND NOT EXISTS (SELECT 1 FROM deliveries d WHERE d.task_id=t.id AND d.sequence=t.occurrence_index)""").fetchall()
        for row in legacy:
            ensure_due_reminder(store, store.get(row['id']))
    sent = 0
    for _ in range(limit):
        with store.transaction():
            row = store.db.execute("""SELECT d.* FROM deliveries d JOIN tasks t ON t.id=d.task_id
                WHERE d.state='pending' AND d.fire_at<=? AND t.status='active'
                AND d.sequence=t.occurrence_index ORDER BY d.fire_at,d.id LIMIT 1""", (stamp(clock),)).fetchone()
            if row is None:
                break
            task = store.get(row['task_id'])
            notifier(task)
            store.db.execute("UPDATE deliveries SET state='sent',delivered_at=? WHERE id=?", (stamp(clock), row['id']))
            sent += 1
    return sent
