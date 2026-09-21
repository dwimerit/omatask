import unittest
from datetime import timedelta
from omatask.engine import Engine
from omatask.persistence import Store
from omatask.recurrence import Rule
from omatask.reminders import dispatch
from omatask.timeutil import instant, stamp
from omatask.transfer import export_data, import_data


class DueReminderTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
        self.now = instant('2026-09-21T10:00:00+00:00')
        self.engine = Engine(self.store, 'UTC', lambda: self.now)
        self.sent = []

    def tearDown(self):
        self.store.close()

    def send_at(self, clock):
        return dispatch(self.store, lambda task: self.sent.append(task.id), clock)

    def test_deadline_alone_delivers_once_and_survives_export(self):
        due = self.now + timedelta(minutes=1)
        task = self.engine.add('Deadline only', due=due)
        self.assertEqual(self.engine.show(task.id)['deliveries'][0]['fire_at'], stamp(due))
        target = Store(':memory:')
        try:
            data = export_data(self.store)
            import_data(target, data)
            self.assertEqual(export_data(target), data)
            self.assertEqual(dispatch(target, lambda _: None, due), 1)
        finally:
            target.close()
        self.assertEqual(self.send_at(due - timedelta(seconds=1)), 0)
        self.assertEqual(self.send_at(due), 1)
        self.assertEqual(self.send_at(due + timedelta(days=1)), 0)
        self.assertEqual(self.sent, [task.id])

    def test_custom_reminder_replaces_default_and_preserves_sent_history(self):
        task = self.engine.add('Custom later', due=self.now)
        self.assertEqual(self.send_at(self.now), 1)
        self.engine.remind(task.id, at=self.now + timedelta(minutes=5))
        info = self.engine.show(task.id)
        self.assertEqual(len(info['reminders']), 1)
        self.assertEqual(sum(d['state'] == 'sent' for d in info['deliveries']), 1)
        self.assertEqual(self.send_at(self.now), 0)
        self.assertEqual(self.send_at(self.now + timedelta(minutes=5)), 1)
        other = self.engine.add('Explicit from start', due=self.now, reminder_specs=[{'seconds':60}])
        self.assertEqual(len(self.engine.show(other.id)['deliveries']), 1)
        self.assertEqual(self.send_at(self.now), 1)

    def test_edit_assign_move_remove_and_reassign_deadline(self):
        task = self.engine.add('Initially undated')
        self.assertEqual(self.engine.show(task.id)['deliveries'], [])
        self.engine.edit(task.id, due_at=stamp(self.now))
        self.engine.edit(task.id, due_at=stamp(self.now + timedelta(minutes=10)))
        self.assertEqual(self.send_at(self.now), 0)
        self.engine.edit(task.id, due_at=None)
        self.assertEqual(self.send_at(self.now + timedelta(hours=1)), 0)
        self.engine.edit(task.id, due_at=stamp(self.now))
        self.assertEqual(self.send_at(self.now), 1)
        # Moving a deadline after its old notification also schedules the new one.
        self.engine.edit(task.id, due_at=stamp(self.now + timedelta(minutes=20)))
        self.assertEqual(self.send_at(self.now), 0)
        self.assertEqual(self.send_at(self.now + timedelta(minutes=20)), 1)

    def test_recurring_default_snooze_and_cancellation(self):
        task = self.engine.add('Repeating', due=self.now, recurrence=Rule('day', count=3).to_dict())
        self.engine.snooze(task.id, '10m')
        self.assertEqual(self.send_at(self.now), 0)
        self.assertEqual(self.send_at(self.now + timedelta(minutes=10)), 1)
        self.engine.done(task.id)
        self.assertEqual(self.send_at(self.now + timedelta(days=1)), 1)
        self.engine.done(task.id)
        self.engine.cancel(task.id)
        self.assertEqual(self.send_at(self.now + timedelta(days=2)), 0)
        self.engine.reopen(task.id)
        self.assertEqual(self.send_at(self.now + timedelta(days=2)), 1)
        self.assertEqual(self.send_at(self.now + timedelta(days=3)), 0)

    def test_legacy_backfill_preserves_explicit_snoozed_and_inactive_tasks(self):
        legacy = self.engine.add('Old task', due=self.now)
        snoozed = self.engine.add('Old snooze', due=self.now)
        finished = self.engine.add('Old completed', due=self.now)
        self.engine.done(finished.id)
        # These rows reproduce an old installation: due dates, no reminder rules.
        with self.store.transaction():
            self.store.db.execute('DELETE FROM reminder_rules')
        self.engine.snooze(snoozed.id, '10m')
        custom = self.engine.add('Custom', due=self.now, reminder_specs=[{'at':self.now + timedelta(hours=1)}])
        self.engine.add('No date')
        self.assertEqual(self.send_at(self.now), 1)
        self.assertEqual(self.sent, [legacy.id])
        self.assertEqual(self.send_at(self.now), 0)
        self.assertEqual(self.send_at(self.now + timedelta(minutes=10)), 1)
        self.assertEqual(self.send_at(self.now + timedelta(hours=1)), 1)
        self.assertEqual(self.sent, [legacy.id, snoozed.id, custom.id])

    def test_invalid_custom_reminder_keeps_default(self):
        task = self.engine.add('Keep reminder', due=self.now)
        before = export_data(self.store)
        with self.assertRaises(ValueError):
            self.engine.remind(task.id, seconds=-1)
        self.assertEqual(export_data(self.store), before)
