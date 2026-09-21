import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from zoneinfo import ZoneInfo

from omatask.daily_window import spread_times
from omatask.engine import Engine
from omatask.parser import parse
from omatask.persistence import MIGRATIONS, TABLES, Store
from omatask.reminders import dispatch
from omatask.timeutil import instant, stamp
from omatask.transfer import export_data, import_data


class DailyWindowTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(':memory:')
        self.clock = instant('2026-09-21T07:00:00+00:00')
        self.engine = Engine(self.store, 'Europe/Moscow', lambda: self.clock)

    def tearDown(self):
        self.store.close()

    def add(self, text):
        return self.engine.add(**parse(text, self.engine.zone, self.clock))

    def local_times(self, task):
        return [instant(d['fire_at']).astimezone(ZoneInfo(task.timezone)).strftime('%Y-%m-%d %H:%M')
                for d in self.engine.show(task.id)['deliveries'] if d['state'] == 'pending']

    def test_short_and_long_syntax_agree(self):
        short = parse('Выпить воду tomorrow daily 8x 08:00-22:00 #health', self.engine.zone, self.clock)
        long = parse('Выпить воду #health tomorrow daily goal 8 between 08:00-22:00', self.engine.zone, self.clock)
        self.assertEqual(short, long)
        task = self.engine.add(**short)
        self.assertEqual(task.title, 'Выпить воду')
        self.assertEqual(task.due_at, '2026-09-22T19:00:00.000000+00:00')
        self.assertEqual(self.local_times(task), [f'2026-09-22 {h:02d}:00' for h in range(8, 23, 2)])
        self.assertEqual(self.engine.show(task.id)['daily_reminders'], [f'{h:02d}:00' for h in range(8, 23, 2)])

    def test_eight_reminders_then_next_day_and_finite_days(self):
        task = self.add('Вода tomorrow daily 8x 08:00-22:00 count 2')
        sent = []
        for hour in range(8, 23, 2):
            at = instant(f'2026-09-22T{hour:02d}:00:00+03:00')
            self.assertEqual(dispatch(self.store, sent.append, at), 1)
            self.assertEqual(dispatch(self.store, sent.append, at), 0)
        self.assertEqual(len(sent), 8)
        self.engine.done(task.id)
        task = self.store.get(task.id)
        self.assertEqual(self.local_times(task), [f'2026-09-23 {h:02d}:00' for h in range(8, 23, 2)])
        self.engine.done(task.id)
        self.assertEqual(self.store.get(task.id).status, 'completed')
        self.assertEqual(dispatch(self.store, sent.append, instant('2026-09-24T23:00:00+03:00')), 0)

    def test_default_today_skips_hours_before_creation(self):
        self.clock = instant('2026-09-21T12:05:00+03:00')
        task = self.add('Вода daily 8x 08:00-22:00')
        self.assertEqual(self.local_times(task), [f'2026-09-21 {h:02d}:00' for h in (14, 16, 18, 20, 22)])
        self.assertEqual(dispatch(self.store, lambda _: None, self.clock), 0)
        self.engine.done(task.id)
        self.assertEqual(len(self.local_times(self.store.get(task.id))), 8)

    def test_after_window_defaults_to_tomorrow(self):
        self.clock = instant('2026-09-21T23:00:00+03:00')
        task = self.add('Вода daily 8x 08:00-22:00')
        self.assertTrue(all(t.startswith('2026-09-22') for t in self.local_times(task)))

    def test_one_slot_and_rounding(self):
        self.assertEqual(spread_times(1, '08:00-22:00'), ['22:00'])
        self.assertEqual(spread_times(4, '08:00-09:00'), ['08:00','08:20','08:40','09:00'])
        self.assertEqual(len(set(spread_times(8, '08:00-09:00'))), 8)

    def test_validation_and_atomicity(self):
        invalid = ['daily 8x', 'daily 08:00-22:00', 'weekly 8x 08:00-22:00',
                   'every 2d 8x 08:00-22:00', 'daily 0x 08:00-22:00', 'daily 8x 22:00-08:00',
                   'daily 8x 08:00-25:00', 'daily 9x 08:00-08:01', 'daily goal 8 goal 9 between 08:00-22:00',
                   'daily 8x 08:00-22:00 remind 1h', 'today 10:00 daily 8x 08:00-22:00']
        for text in invalid:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.add('Вода ' + text)
        self.assertEqual(self.store.all(), [])
        parsed = parse('Вода daily 8x 08:00-22:00', self.engine.zone, self.clock)
        parsed['recurrence'] = None
        with self.assertRaises(ValueError):
            self.engine.add(**parsed)
        self.assertEqual(self.store.all(), [])

    def test_local_hours_across_dst_transitions(self):
        self.engine.zone = 'America/New_York'
        for first, next_day, expected in [
            ('2026-03-07', '2026-03-08', ['2026-03-08T06:00:00.000000+00:00','2026-03-08T08:00:00.000000+00:00']),
            ('2026-10-31', '2026-11-01', ['2026-11-01T05:00:00.000000+00:00','2026-11-01T09:00:00.000000+00:00'])]:
            with self.subTest(first=first):
                self.clock = instant(first + 'T00:00:00-05:00')
                task = self.add('Water ' + first + ' daily 2x 01:00-04:00')
                self.engine.done(task.id)
                data = self.engine.show(task.id)
                self.assertEqual([d['fire_at'] for d in data['deliveries'] if d['state']=='pending'], expected)
                self.assertEqual(self.local_times(self.store.get(task.id)), [next_day+' 01:00', next_day+' 04:00'])

    def test_edit_date_and_cancel_reopen_preserve_schedule(self):
        task = self.add('Вода tomorrow daily 8x 08:00-22:00')
        self.engine.edit(task.id, due_at='2026-09-25T22:00:00+03:00')
        task = self.store.get(task.id)
        expected = [f'2026-09-25 {h:02d}:00' for h in range(8, 23, 2)]
        self.assertEqual(self.local_times(task), expected)
        before = export_data(self.store)
        for changes in ({'due_at':None}, {'recurrence':None}, {'due_at':'2026-09-25T12:00:00+03:00'}):
            with self.assertRaises(ValueError):self.engine.edit(task.id, **changes)
            self.assertEqual(export_data(self.store), before)
        self.engine.cancel(task.id)
        self.assertEqual(self.local_times(task), [])
        self.engine.reopen(task.id)
        self.assertEqual(self.local_times(task), expected)

    def test_roundtrip_and_corrupt_clock_rejected(self):
        self.add('Вода tomorrow daily 8x 08:00-22:00')
        data = export_data(self.store)
        target = Store(':memory:')
        try:
            import_data(target, data)
            self.assertEqual(export_data(target), data)
            before = export_data(target)
            data['tables']['reminder_rules'][0]['value'] = '25:00'
            with self.assertRaises(ValueError):import_data(target, data)
            self.assertEqual(export_data(target), before)
        finally:
            target.close()


class DailyWindowMigrationTests(unittest.TestCase):
    def test_v3_migration_preserves_all_delivery_states_and_foreign_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'v3.db'
            db = sqlite3.connect(path)
            db.row_factory = sqlite3.Row
            for migration in MIGRATIONS[:3]:
                for sql in migration:db.execute(sql)
            db.execute("INSERT INTO tasks VALUES ('keep','Existing','', 'active','normal',?, ?,NULL,'UTC',NULL,?,0,'[]','','[]')", ('2026-09-21T00:00:00.000000+00:00',)*3)
            for index, state in enumerate(('pending','sent','cancelled')):
                db.execute("INSERT INTO reminder_rules VALUES (?, 'keep', 'relative', '3600')", ('r'+str(index),))
                db.execute('INSERT INTO deliveries VALUES (?,?,?,0,?,?,?)', ('d'+str(index),'r'+str(index),'keep','2026-09-20T23:00:00.000000+00:00',state,'2026-09-20T23:00:00.000000+00:00' if state=='sent' else None))
            db.execute('PRAGMA user_version=3')
            old = {'format':'omatask-1','schema':3,'tables':{table:[dict(r) for r in db.execute('SELECT * FROM '+table+' ORDER BY id')] for table in TABLES}}
            db.commit();db.close()
            store = Store(path)
            try:
                self.assertEqual(export_data(store)['tables'], old['tables'])
                self.assertEqual(store.db.execute('PRAGMA foreign_key_check').fetchall(), [])
                target = Store(':memory:')
                try:
                    import_data(target, old)
                    self.assertEqual(export_data(target)['tables'], old['tables'])
                finally:target.close()
                Engine(store).delete('keep')
                for table in ('reminder_rules','deliveries'):
                    self.assertEqual(store.db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
            finally:store.close()

    def test_cli_short_syntax_and_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = [sys.executable,'-m','omatask','--db',str(Path(tmp)/'tasks.db'),'--json']
            result = subprocess.run(base+['add','Вода tomorrow daily 8x 08:00-22:00'],check=True,text=True,capture_output=True)
            task = json.loads(result.stdout)
            info = json.loads(subprocess.check_output(base+['show',task['id']],text=True))
            self.assertEqual(info['daily_reminders'],[f'{h:02d}:00' for h in range(8,23,2)])
            literal = json.loads(subprocess.check_output(base+['add','Water daily 8x','--literal'],text=True))
            self.assertEqual(literal['title'],'Water daily 8x')
            bad = subprocess.run(base+['add','Water daily 8x 08:00-22:00','--repeat','none'],text=True,capture_output=True)
            self.assertEqual(bad.returncode,2)
