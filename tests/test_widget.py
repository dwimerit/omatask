import unittest
from datetime import timedelta
from omatask.engine import Engine
from omatask.persistence import Store
from omatask.integrations import widget_snapshot
from omatask.timeutil import instant


class WidgetTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(':memory:')
        self.clock=instant('2026-09-21T10:00:00+00:00')
        self.engine=Engine(self.store,'UTC',lambda:self.clock)
    def tearDown(self):self.store.close()

    def test_snapshot_summary_matches_engine(self):
        self.engine.add('Past',due=self.clock-timedelta(days=1))
        self.engine.add('Today',due=self.clock+timedelta(hours=1))
        task=self.engine.add('Finished',due=self.clock)
        self.engine.done(task.id)
        data=widget_snapshot(self.engine)
        self.assertEqual(data['summary']['count'],1)
        self.assertEqual(data['summary']['overdue'],1)
        self.assertEqual([t['title'] for t in data['tasks']],['Today'])
        self.assertEqual(data['tasks'][0]['due_label'],'21 Sep · 11:00')
        self.assertEqual(len(widget_snapshot(self.engine,'all')['tasks']),3)
        self.assertEqual(widget_snapshot(self.engine,'completed')['tasks'][0]['title'],'Finished')

    def test_search_unicode_progress_and_html_are_plain(self):
        task=self.engine.add('<b>Купить молоко</b>',description='backend notes',due=self.clock,tags=['work'])
        task=self.engine.subtask(task.id,'add','Check')
        self.engine.subtask(task.id,'done',task.subtasks[0]['id'])
        data=widget_snapshot(self.engine,query='BACKEND')
        self.assertEqual(data['tasks'][0]['title'],'<b>Купить молоко</b>')
        self.assertEqual(data['tasks'][0]['progress'],{'done':1,'total':1})
        self.assertEqual(widget_snapshot(self.engine,query='absent')['tasks'],[])
        self.assertEqual(data['summary']['count'],1)

    def test_invalid_view_rolls_back_read_transaction(self):
        with self.assertRaises(ValueError):widget_snapshot(self.engine,'invalid')
        self.engine.add('Still writable')
        self.assertFalse(self.store.db.in_transaction)
