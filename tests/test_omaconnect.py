import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from omatask import notifications as n
from omatask.engine import Engine
from omatask.persistence import Store
from omatask.reminders import dispatch
from omatask.timeutil import instant


class OmaConnectTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict(os.environ, {'XDG_CONFIG_HOME': folder}))
        self.config = Path(folder) / 'omatask/config.json'
        self.config.parent.mkdir()
        self.task = SimpleNamespace(title='Позвонить <маме> $(echo hi)', id='12345678', due_at=None)
        self.run = self.enterContext(patch.object(n.subprocess, 'run'))
        self.which = self.enterContext(patch.object(n.shutil, 'which', return_value='/usr/bin/kdeconnect-cli'))
        self.dnd = self.enterContext(patch.object(n, 'do_not_disturb', return_value=False))

    def configure(self, **settings):
        self.config.write_text(json.dumps({'omaconnect': {'enabled': True, 'device_id': 'phone-id', **settings}}))

    def test_disabled_by_default_without_backend_calls(self):
        self.assertFalse(n.phone_notify(self.task))
        self.run.assert_not_called()
        self.which.assert_not_called()
        self.dnd.assert_not_called()

    def test_invalid_config_fails_closed(self):
        for data in ('{', '[]', '{"omaconnect": null}', '{"omaconnect": {"enabled": "true"}}',
                     '{"omaconnect": {"enabled": true}}',
                     '{"omaconnect": {"enabled": true, "device_id": "phone", "respect_dnd": 1}}'):
            with self.subTest(data=data):
                self.config.write_text(data)
                with self.assertLogs(n.log, level='WARNING'):
                    self.assertFalse(n.phone_notify(self.task))
        self.run.assert_not_called()

    def test_only_selected_reachable_device_receives_plain_text(self):
        self.configure()
        self.run.return_value = SimpleNamespace(stdout='other-device\nphone-id\n')
        self.assertTrue(n.phone_notify(self.task))
        self.assertEqual(self.run.call_count, 2)
        args = self.run.call_args.args[0]
        self.assertEqual(args, ['/usr/bin/kdeconnect-cli', '--device=phone-id',
                               '--ping-msg=Omatask: Позвонить <маме> $(echo hi)\nTask 12345678 · due unscheduled'])
        self.assertEqual(self.run.call_args.kwargs['timeout'], 3)

    def test_offline_or_missing_dependency_is_nonfatal(self):
        self.configure()
        self.which.return_value = None
        with self.assertLogs(n.log, level='WARNING'):
            self.assertFalse(n.phone_notify(self.task))
        self.run.assert_not_called()
        self.which.return_value = '/usr/bin/kdeconnect-cli'
        self.run.return_value = SimpleNamespace(stdout='another-phone-id\n')
        with self.assertLogs(n.log, level='WARNING'):
            self.assertFalse(n.phone_notify(self.task))
        self.assertEqual(self.run.call_count, 1)

    def test_dnd_and_live_config_reload(self):
        self.configure()
        self.dnd.return_value = True
        self.assertFalse(n.phone_notify(self.task))
        self.run.assert_not_called()
        self.configure(respect_dnd=False)
        self.run.return_value = SimpleNamespace(stdout='phone-id\n')
        self.assertTrue(n.phone_notify(self.task))
        self.configure(enabled=False)
        self.assertFalse(n.phone_notify(self.task))
        self.assertEqual(self.run.call_count, 2)

    def test_backend_errors_are_nonfatal(self):
        self.configure()
        for error in (OSError('missing'), subprocess.TimeoutExpired('kdeconnect-cli', 3),
                      subprocess.CalledProcessError(1, 'kdeconnect-cli')):
            for during_send in (False, True):
                with self.subTest(error=error, during_send=during_send):
                    self.run.side_effect = [SimpleNamespace(stdout='phone-id\n'), error] if during_send else error
                    with self.assertLogs(n.log, level='WARNING'):
                        self.assertFalse(n.phone_notify(self.task))

    def test_failed_phone_does_not_retry_desktop_delivery(self):
        self.configure()
        self.enterContext(patch.object(n, 'play_sound'))
        clock = instant('2026-09-21T10:00:00+00:00')
        store = Store(':memory:')
        self.addCleanup(store.close)
        Engine(store, 'UTC', lambda: clock).add('Reminder', due=clock)
        self.run.side_effect = [SimpleNamespace(returncode=0), SimpleNamespace(stdout='phone-id\n'),
                                subprocess.TimeoutExpired('kdeconnect-cli', 3)]
        with self.assertLogs(n.log, level='WARNING'):
            self.assertEqual(dispatch(store, clock=clock), 1)
        self.assertEqual(dispatch(store, clock=clock), 0)
        self.assertEqual(self.run.call_count, 3)

    def test_send_errors_do_not_log_task_or_device(self):
        self.configure()
        def fail_send(command, **kwargs):
            if '--id-only' in command:
                return SimpleNamespace(stdout='phone-id\n')
            raise subprocess.CalledProcessError(1, command, stderr='private backend output')
        self.run.side_effect = fail_send
        with self.assertLogs(n.log, level='WARNING') as logs:
            self.assertFalse(n.phone_notify(self.task))
        message = '\n'.join(logs.output)
        self.assertIn('status 1', message)
        for private in (self.task.title, self.task.id, 'phone-id', 'private backend output'):
            self.assertNotIn(private, message)
