import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from omatask.parser import parse
from omatask.timeutil import instant, parse_date
from omatask.persistence import Store, MIGRATIONS
from omatask.engine import Engine
from omatask.recurrence import Rule
from omatask.reminders import dispatch
from omatask.transfer import export_data, import_data, markdown

CLOCK=instant('2026-09-21T10:00:00+00:00')


class ParserTests(unittest.TestCase):
    def test_examples(self):
        task=parse('Deploy server tomorrow 18:00 #work !high','UTC',CLOCK)
        self.assertEqual(task['title'],'Deploy server')
        self.assertEqual(task['due'].isoformat(),'2026-09-22T18:00:00+00:00')
        self.assertEqual(task['priority'],'high')
        self.assertEqual(task['tags'],['work'])
        task=parse('Call client friday 14:00 remind 30m #work','UTC',CLOCK)
        self.assertEqual(task['due'].day,25)
        self.assertEqual(task['reminder_specs'],[{'seconds':1800}])

    def test_recurrence_and_project(self):
        task=parse('Gym monday 09:00 every mon,wed,fri count 30 +"Side Project"','UTC',CLOCK)
        self.assertEqual(task['recurrence']['weekdays'],[0,2,4])
        self.assertEqual(task['recurrence']['count'],30)
        self.assertEqual(task['project'],'Side Project')
        self.assertEqual(parse('Water in 2h every 2h','UTC',CLOCK)['recurrence']['interval'],2)

    def test_absolute_and_multiple_reminders(self):
        task=parse('Call tomorrow 10:00 remind 30m remind 1h remind at 18:00','UTC',CLOCK)
        self.assertEqual(len(task['reminder_specs']),3)
        self.assertEqual(task['reminder_specs'][2]['at'].hour,18)

    def test_invalid_input(self):
        for text in ('!bad title','Title tomorrow 25:00','Title every potato','Title count 0','Title remind 0m','Title tomorrow today','Title daily weekly','"unclosed'):
            with self.subTest(text=text), self.assertRaises(ValueError):parse(text,'UTC',CLOCK)

    def test_local_and_explicit_offset(self):
        self.assertEqual(parse_date('2026-09-22 09:00','Europe/Moscow',CLOCK).utcoffset().total_seconds(),10800)
        self.assertEqual(parse_date('2026-09-22T09:00:00-04:00','Europe/Moscow',CLOCK).utcoffset().total_seconds(),-14400)
        self.assertEqual(parse_date('09:00','UTC',CLOCK).day,22)


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:');self.e=Engine(self.store,'UTC',lambda:CLOCK)
    def tearDown(self):self.store.close()

    def test_atomic_create_reminder_failure(self):
        with self.assertRaises(ValueError):self.e.add('Fail',reminder_specs=[{'seconds':30}])
        self.assertEqual(self.store.all(),[])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM reminder_rules').fetchone()[0],0)

    def test_filters_search_and_checklist(self):
        task=self.e.add('Release',description='Deploy backend',tags=['work'],project='Work',priority='urgent',due=CLOCK)
        self.assertEqual(len(self.e.list(query='BACKEND',project='Work',tag='work',priority='urgent',due='2026-09-21')),1)
        self.assertEqual(self.e.list(tag='missing'),[])
        task=self.e.subtask(task.id,'add','run tests')
        task=self.e.subtask(task.id,'done',task.subtasks[0]['id'][:8])
        self.assertEqual(self.e.show(task.id)['subtask_progress'],{'done':1,'total':1})
        self.e.subtask(task.id,'delete',task.subtasks[0]['id'])
        self.assertEqual(self.e.show(task.id)['subtask_progress']['total'],0)

    def test_reopen_finite_series_keeps_audit(self):
        task=self.e.add('Daily',due=CLOCK,recurrence=Rule('day',count=1).to_dict())
        self.e.done(task.id);self.e.reopen(task.id)
        info=self.e.show(task.id)
        self.assertEqual(info['remaining_count'],1)
        self.assertEqual(info['completed_count'],0)
        self.assertEqual(info['execution_count'],1)
        self.assertIsNotNone(info['history'][0]['reopened_at'])
        self.e.done(task.id)
        info=self.e.show(task.id)
        self.assertEqual(info['remaining_count'],0)
        self.assertEqual(info['execution_count'],2)

    def test_checklist_snapshot_and_reset(self):
        task=self.e.add('Daily',due=CLOCK,recurrence=Rule('day',count=2).to_dict())
        task=self.e.subtask(task.id,'add','Item')
        task=self.e.subtask(task.id,'done',task.subtasks[0]['id'])
        task=self.e.done(task.id)
        self.assertFalse(task.subtasks[0]['done'])
        self.assertTrue(json.loads(self.e.show(task.id)['history'][0]['subtasks'])[0]['done'])

    def test_full_roundtrip_and_atomic_conflict(self):
        task=self.e.add('Task',description='Notes',tags=['tag'],project='Work',due=CLOCK,recurrence=Rule('day',count=3).to_dict(),reminder_specs=[{'seconds':600}])
        self.e.subtask(task.id,'add','Sub');self.e.done(task.id);self.e.snooze(task.id,'30m')
        exported=export_data(self.store)
        target=Store(':memory:')
        try:
            import_data(target,exported)
            self.assertEqual(export_data(target),exported)
            before=export_data(target)
            with self.assertRaises(ValueError):import_data(target,exported)
            self.assertEqual(export_data(target),before)
            self.assertIn('Task',markdown(target))
        finally:target.close()

    def test_bad_import_rolls_back(self):
        task=self.e.add('Task')
        data=export_data(self.store)
        data['tables']['tasks'][0]['status']='broken'
        before=export_data(self.store)
        with self.assertRaises(ValueError):import_data(self.store,data)
        self.assertEqual(export_data(self.store),before)

    def test_edit_due_reschedules_pending(self):
        task=self.e.add('Task',due=CLOCK,reminder_specs=[{'seconds':600}])
        self.e.edit(task.id,due_at='2026-09-22T10:00:00+00:00')
        self.assertEqual(self.e.show(task.id)['deliveries'][0]['fire_at'],'2026-09-22T09:50:00.000000+00:00')
        with self.assertRaises(ValueError):self.e.edit(task.id,due_at=None)

    def test_cancel_reopen_and_delete_cascade(self):
        task=self.e.add('Task',due=CLOCK,reminder_specs=[{'at':CLOCK}])
        self.e.cancel(task.id);self.e.reopen(task.id)
        self.assertEqual(dispatch(self.store,lambda _:None,CLOCK),1)
        self.e.delete(task.id)
        for table in ('deliveries','reminder_rules','occurrences'):
            self.assertEqual(self.store.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0],0)

    def test_timezone_views(self):
        task=self.e.add('Late',due=instant('2026-09-20T23:30:00+00:00'))
        moscow=Engine(self.store,'Europe/Moscow',lambda:CLOCK)
        self.assertEqual(len(moscow.list('today')),1)
        self.assertEqual(self.e.list('today'),[])
        self.assertEqual(self.store.get(task.id).timezone,'UTC')


class PersistenceTests(unittest.TestCase):
    def test_backup_refuses_dangling_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / 'backup.db'
            target = Path(tmp) / 'other.db'
            destination.symlink_to(target)
            store = Store(':memory:')
            try:
                with self.assertRaisesRegex(ValueError, 'already exists'):
                    store.backup(destination)
                self.assertFalse(target.exists())
            finally:
                store.close()

    def test_migrate_v1_without_data_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'old.db';db=sqlite3.connect(path)
            for stmt in MIGRATIONS[0]:db.execute(stmt)
            db.execute("INSERT INTO tasks VALUES ('abc','Old','', 'active','normal',?,NULL,NULL,'UTC',NULL,NULL,0)",(CLOCK.isoformat(),))
            db.execute('PRAGMA user_version=1');db.commit();db.close()
            store=Store(path)
            self.assertEqual(store.get('abc').title,'Old')
            self.assertEqual(store.get('abc').tags,[])
            self.assertEqual(store.db.execute('PRAGMA user_version').fetchone()[0],len(MIGRATIONS))
            store.close()

    def test_future_schema_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'new.db';db=sqlite3.connect(path)
            db.execute('PRAGMA user_version=999');db.close()
            with self.assertRaises(ValueError):Store(path)

    def test_two_workers_deliver_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tasks.db';store=Store(path)
            engine=Engine(store,'UTC',lambda:CLOCK)
            for i in range(4):engine.add(str(i),due=CLOCK,reminder_specs=[{'at':CLOCK}])
            store.close();sent=[];errors=[]
            def worker():
                try:
                    s=Store(path)
                    try:dispatch(s,lambda t:sent.append(t.id),CLOCK)
                    finally:s.close()
                except BaseException as e:errors.append(e)
            threads=[threading.Thread(target=worker) for _ in range(2)]
            for t in threads:t.start()
            for t in threads:t.join()
            self.assertEqual(errors,[]);self.assertEqual(len(sent),4);self.assertEqual(len(set(sent)),4)


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=str(Path(self.tmp.name)/'tasks.db')
    def tearDown(self):self.tmp.cleanup()
    def call(self,*args,code=0):
        result=subprocess.run([sys.executable,'-m','omatask','--db',self.db,'--timezone','UTC','--json',*args],text=True,capture_output=True)
        self.assertEqual(result.returncode,code,result.stderr)
        return json.loads(result.stdout) if result.stdout else None

    def test_cli_lifecycle(self):
        task=self.call('add','Deploy server tomorrow 18:00 #work !high remind 30m')
        self.assertEqual(task['title'],'Deploy server')
        self.assertEqual(len(self.call('list','tomorrow','--tag','work')),1)
        self.call('edit',task['id'],'--description','backend notes')
        self.assertEqual(len(self.call('search','backend')),1)
        self.call('done',task['id']);self.call('reopen',task['id']);self.call('cancel',task['id'])
        self.assertEqual(self.call('show',task['id'])['status'],'cancelled')
        self.call('delete',task['id']);self.call('show',task['id'],code=3)

    def test_exit_codes_atomic_invalid_literal(self):
        self.call('add','Task remind 30m',code=2)
        self.call('add','Task tomorrow','--repeat','day','--interval','0',code=2)
        self.assertEqual(self.call('list'),[])
        task=self.call('add','Practice daily','--literal')
        self.assertEqual(task['title'],'Practice daily')
        self.call('list','unknown',code=2)

    def test_empty_ids_cannot_mutate_the_only_task_or_subtask(self):
        task = self.call('add', 'Keep this task')
        for command in ('delete', 'done', 'cancel', 'reopen'):
            with self.subTest(command=command):
                self.call(command, '', code=2)
        self.assertEqual(self.call('show', task['id'])['status'], 'active')
        task = self.call('subtask', task['id'], 'add', 'Keep this item')
        for action in ('delete', 'done', 'reopen'):
            with self.subTest(action=action):
                self.call('subtask', task['id'], action, '', code=2)
        self.assertEqual(self.call('show', task['id'])['subtasks'], task['subtasks'])

    def test_cli_export_import_backup_and_stats(self):
        self.call('add','Water today 12:00 every 2h count 3')
        out=str(Path(self.tmp.name)/'out.json')
        self.call('export',out)
        self.call('backup',str(Path(self.tmp.name)/'backup.db'))
        self.db=str(Path(self.tmp.name)/'restored.db')
        self.assertEqual(self.call('import',out)['imported'],1)
        self.assertEqual(self.call('stats')['tasks'],1)
        self.assertEqual(self.call('bar')['count'],1)

    def test_exports_and_backups_are_private_and_refuse_overwrite(self):
        self.call('add', 'Private task')
        previous_umask = os.umask(0o022)
        try:
            for command, filename, options, error_code in (
                    ('export', 'tasks.json', (), 1),
                    ('export', 'tasks.md', ('--format', 'markdown'), 1),
                    ('backup', 'copy.db', (), 2)):
                with self.subTest(command=command, filename=filename):
                    destination = Path(self.tmp.name) / filename
                    self.call(command, str(destination), *options)
                    self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
                    contents = destination.read_bytes()
                    self.call(command, str(destination), *options, code=error_code)
                    self.assertEqual(destination.read_bytes(), contents)
        finally:
            os.umask(previous_umask)

if __name__=='__main__':unittest.main()
