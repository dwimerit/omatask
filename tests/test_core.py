import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from omatask.timeutil import instant, stamp, parse_date, UTC
from omatask.recurrence import Rule, occurrence, final_index
from omatask.persistence import Store
from omatask.engine import Engine
from omatask.reminders import dispatch, snooze_time


class RecurrenceTests(unittest.TestCase):
    def test_monthly_anchor_and_leap(self):
        anchor = instant('2024-01-31T09:00:00+00:00')
        rule = Rule('month',count=3)
        self.assertEqual(occurrence(anchor,rule,1,'UTC').day,29)
        self.assertEqual(occurrence(anchor,rule,2,'UTC').day,31)
        self.assertIsNone(occurrence(anchor,rule,3,'UTC'))
        self.assertEqual(final_index(anchor,rule,'UTC'),2)
        self.assertEqual(occurrence(anchor,Rule('month',12),1,'UTC').day,31)

    def test_weekdays_interval_count(self):
        anchor=instant('2026-09-21T09:00:00+00:00')
        rule=Rule('week',2,count=5,weekdays=[0,2,4])
        self.assertEqual([occurrence(anchor,rule,i,'UTC').day for i in range(5)],[21,23,25,5,7])
        self.assertIsNone(occurrence(anchor,rule,5,'UTC'))
        with self.assertRaises(ValueError):
            occurrence(anchor,Rule('week',weekdays=[1]),0,'UTC')

    def test_dst_gap_fold_calendar_vs_elapsed(self):
        anchor=instant('2026-03-07T02:30:00-05:00')
        day=Rule('day')
        self.assertEqual(occurrence(anchor,day,1,'America/New_York').hour,3)
        self.assertEqual(occurrence(anchor,day,2,'America/New_York').hour,2)
        fall=instant('2026-10-31T01:30:00-04:00')
        self.assertEqual(occurrence(fall,day,1,'America/New_York').utcoffset(),timedelta(hours=-4))
        self.assertEqual((occurrence(anchor,Rule('hour',24),1,'America/New_York')-anchor.astimezone(UTC)).total_seconds(),86400)

    def test_until_midnight(self):
        anchor=instant('2026-01-01T23:59:00+00:00')
        rule=Rule('minute',2,until='2026-01-02T00:03:00+00:00')
        self.assertEqual(occurrence(anchor,rule,1,'UTC').day,2)
        self.assertEqual(final_index(anchor,rule,'UTC'),2)
        self.assertIsNone(occurrence(anchor,rule,3,'UTC'))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/'tasks.db'
        self.store=Store(self.path)
        self.clock=instant('2026-09-21T10:00:00+00:00')
        self.engine=Engine(self.store,'UTC',lambda:self.clock)

    def tearDown(self):
        self.store.close(); self.tmp.cleanup()

    def test_create_complete_reopen_delete(self):
        task=self.engine.add('Buy milk')
        self.assertEqual(self.engine.done(task.id).status,'completed')
        self.assertEqual(self.engine.reopen(task.id).status,'active')
        self.engine.done(task.id)
        self.assertEqual(self.engine.show(task.id)['execution_count'],2)
        self.engine.delete(task.id)
        self.assertEqual(self.store.all(),[])

    def test_thirty_repeats_history(self):
        task=self.engine.add('English',due=self.clock,recurrence=Rule('day',count=30).to_dict())
        for _ in range(30):
            task=self.engine.done(task.id)
        self.assertEqual(task.status,'completed')
        details=self.engine.show(task.id)
        self.assertEqual(details['completed_count'],30)
        self.assertEqual(details['remaining_count'],0)
        with self.assertRaises(ValueError):self.engine.done(task.id)

    def test_reminder_restart_snooze_and_failure(self):
        task=self.engine.add('Call',due=self.clock)
        self.engine.remind(task.id,seconds=1800)
        self.engine.remind(task.id,at=self.clock)
        self.store.close();self.store=Store(self.path)
        self.engine=Engine(self.store,'UTC',lambda:self.clock)
        def fail(_):raise OSError('offline')
        with self.assertRaises(OSError):dispatch(self.store,fail,self.clock)
        sent=[]
        self.assertEqual(dispatch(self.store,sent.append,self.clock),2)
        self.assertEqual(dispatch(self.store,sent.append,self.clock),0)
        self.engine.snooze(task.id,'10m')
        self.assertEqual(dispatch(self.store,sent.append,self.clock+timedelta(minutes=9)),0)
        self.assertEqual(dispatch(self.store,sent.append,self.clock+timedelta(minutes=10)),1)
        self.assertEqual(dispatch(self.store,sent.append,self.clock-timedelta(days=1)),0)

    def test_cancel_and_repeat_reminders(self):
        task=self.engine.add('Water',due=self.clock,recurrence=Rule('hour',2,count=2).to_dict())
        self.engine.remind(task.id,seconds=60)
        self.engine.done(task.id)
        self.assertEqual(dispatch(self.store,lambda _:None,self.clock),0)
        self.assertEqual(dispatch(self.store,lambda _:None,self.clock+timedelta(hours=2)),1)
        self.engine.cancel(task.id)
        self.assertEqual(dispatch(self.store,lambda _:None,self.clock+timedelta(days=1)),0)

    def test_overdue_and_integrity(self):
        task=self.engine.add('Past',due=self.clock-timedelta(seconds=1))
        self.engine.add('Current',due=self.clock)
        self.assertEqual([t.id for t in self.engine.list('overdue')],[task.id])
        self.assertEqual(self.store.db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(self.store.db.execute('PRAGMA foreign_key_check').fetchall(),[])
        self.engine.cancel(task.id);self.assertEqual(self.engine.list('overdue'),[])

    def test_snooze_calendar(self):
        night=instant('2026-03-07T23:00:00-05:00')
        result=snooze_time('tomorrow','America/New_York',night)
        self.assertEqual(result.hour,9)
        self.assertEqual(result.utcoffset(),timedelta(hours=-4))
        self.assertEqual(snooze_time('evening','UTC',self.clock).hour,18)

    def test_atomic_invalid_and_backup(self):
        with self.assertRaises(ValueError):self.engine.add('')
        self.assertEqual(len(self.store.all()),0)
        self.engine.add('saved')
        backup=Path(self.tmp.name)/'backup.db';self.store.backup(backup)
        restored=Store(backup)
        self.assertEqual(restored.all()[0].title,'saved');restored.close()

if __name__=='__main__':unittest.main()
