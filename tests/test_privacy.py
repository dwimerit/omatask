"""Exercise the real backend without contacting desktop services or a network."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parent.parent

# The hook lives only in each test child. Record attempts before raising so code
# that catches a network error cannot make the privacy check pass silently.
GUARDED_BACKEND = textwrap.dedent('''\
    import json
    import os
    from pathlib import Path
    import runpy
    import sys

    allowed = set(json.loads(os.environ['OMATASK_TEST_COMMANDS']))

    def guard(event, args):
        forbidden = event.startswith('socket.') or event == 'os.system'
        if event in ('subprocess.Popen', 'os.exec', 'os.posix_spawn', 'os.posix_spawnp'):
            forbidden = os.fsdecode(args[0]) not in allowed
        if forbidden:
            with open(os.environ['OMATASK_TEST_VIOLATIONS'], 'a') as output:
                output.write(event + '\\n')
            raise RuntimeError('Unexpected network or process operation: ' + event)

    sys.addaudithook(guard)
    sys.argv = sys.argv[1:]
    runpy.run_path(sys.argv[0], run_name='__main__')
''')

FAKE_COMMAND = textwrap.dedent('''\
    #!/usr/bin/python3 -I
    import json
    import os
    from pathlib import Path
    import sys

    name = Path(sys.argv[0]).name
    with open(os.environ['OMATASK_TEST_CALLS'], 'a') as output:
        output.write(json.dumps([name, *sys.argv[1:]]) + '\\n')
    if name == 'omarchy-shell':
        print('off')
    elif name == 'kdeconnect-cli' and '--list-available' in sys.argv:
        print('synthetic-phone')
''')


class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        commands = self.root / 'bin'
        commands.mkdir()
        allowed = []
        for name in ('notify-send', 'omarchy-shell', 'pw-play', 'paplay', 'kdeconnect-cli'):
            path = commands / name
            path.write_text(FAKE_COMMAND)
            path.chmod(0o755)
            allowed.extend((name, str(path)))
        self.calls_path = self.root / 'commands.jsonl'
        self.calls_path.touch()
        self.violations_path = self.root / 'violations.txt'
        self.violations_path.touch()
        self.env = {
            'HOME': str(self.root / 'home'),
            'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_DATA_HOME': str(self.root / 'data'),
            'XDG_STATE_HOME': str(self.root / 'state'),
            'XDG_CACHE_HOME': str(self.root / 'cache'),
            'PATH': str(commands),
            'LANG': 'C.UTF-8',
            'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/dev/null',
            'OMATASK_TEST_COMMANDS': json.dumps(allowed),
            'OMATASK_TEST_CALLS': str(self.calls_path),
            'OMATASK_TEST_VIOLATIONS': str(self.violations_path),
        }
        self.title = 'Offline task https://example.invalid/task'
        self.description = 'Private synthetic notes, never included in phone delivery'

    def run_backend(self, *args, database=None):
        options = ['--db', str(database)] if database else []
        result = subprocess.run(
            [sys.executable, '-I', '-B', '-c', GUARDED_BACKEND,
             str(ROOT / 'scripts/omatask-backend'), '--json', '--timezone', 'UTC',
             *options, *args],
            env=self.env, cwd=self.root, text=True, capture_output=True, timeout=10)
        self.assertEqual(self.violations_path.read_text(), '')
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout) if result.stdout.strip() else None

    def calls(self):
        return [json.loads(line) for line in self.calls_path.read_text().splitlines()]

    def create_due_task(self):
        due = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        return self.run_backend('add', self.title, '--literal', '--due', due,
                                '--description', self.description)

    def test_default_lifecycle_is_local_even_with_kdeconnect_available(self):
        task = self.create_due_task()
        snapshot = self.run_backend('widget', 'all')
        self.assertEqual(snapshot['tasks'][0]['title'], self.title)
        self.assertEqual(self.run_backend('search', 'Offline')[0]['id'], task['id'])
        self.assertEqual(self.calls(), [])

        self.assertEqual(self.run_backend('worker', '--once'), {'sent': 1})
        self.assertEqual(self.run_backend('worker', '--once'), {'sent': 0})
        calls = self.calls()
        self.assertEqual([call[0] for call in calls], ['notify-send', 'omarchy-shell', 'pw-play'])
        self.assertIn(self.title, calls[0])

        export = self.root / 'export.json'
        backup = self.root / 'backup.db'
        restored = self.root / 'restored.db'
        self.run_backend('export', str(export))
        self.run_backend('backup', str(backup))
        self.run_backend('import', str(export), database=restored)
        for database in (backup, restored):
            self.assertEqual(self.run_backend('show', task['id'], database=database)['title'], self.title)
        self.assertEqual(self.run_backend('done', task['id'])['status'], 'completed')
        self.assertEqual(self.calls(), calls)
        self.assertTrue((self.root / 'data/omatask/tasks.db').is_file())

    def test_phone_delivery_requires_opt_in_and_sends_only_reminder_fields(self):
        config = self.root / 'config/omatask/config.json'
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'omaconnect': {
            'enabled': True, 'device_id': 'synthetic-phone'}}))
        task = self.create_due_task()
        self.assertEqual(self.run_backend('worker', '--once'), {'sent': 1})
        phone_calls = [call for call in self.calls() if call[0] == 'kdeconnect-cli']
        self.assertEqual(phone_calls, [
            ['kdeconnect-cli', '--list-available', '--id-only'],
            ['kdeconnect-cli', '--device=synthetic-phone',
             '--ping-msg=' + f"Omatask: {self.title}\nTask {task['id'][:8]} · due {task['due_at']}"]])
        self.assertNotIn(self.description, json.dumps(phone_calls))

        config.write_text(json.dumps({'omaconnect': {
            'enabled': False, 'device_id': 'synthetic-phone'}}))
        self.create_due_task()
        self.assertEqual(self.run_backend('worker', '--once'), {'sent': 1})
        self.assertEqual([call for call in self.calls() if call[0] == 'kdeconnect-cli'], phone_calls)
