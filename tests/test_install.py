"""Install/update safety with isolated HOME and fake desktop commands."""
import os
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent.parent


class InstallerTests(unittest.TestCase):
    def setup_home(self, directory):
        home=Path(directory)
        fake=home/'tools';fake.mkdir()
        dispatcher=fake/'fake'
        dispatcher.write_text('''#!/usr/bin/python3
import json, os, sys
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
if name=='hyprctl' and args==['binds','-j']:
    print(json.dumps([{'modmask':72,'key':'T'}] if os.environ.get('OMATASK_TEST_CONFLICT') else []))
elif name=='hyprctl' and args==['configerrors']:pass
else:print('ok')
''')
        dispatcher.chmod(0o755)
        for name in ('hyprctl','omarchy','omarchy-shell','systemctl'):(fake/name).symlink_to('fake')
        config=home/'.config'
        (config/'hypr').mkdir(parents=True)
        (config/'hypr/bindings.lua').write_text('-- Existing personal binding\n')
        return dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(config),
                    XDG_DATA_HOME=str(home/'.local/share'),
                    XDG_STATE_HOME=str(home/'.local/state'),PATH=str(fake)+':'+os.environ['PATH'])

    def test_install_update_preserves_data_and_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=self.setup_home(tmp)
            args=[sys.executable,str(ROOT/'scripts/install-desktop.py')]
            subprocess.run(args,env=env,check=True,capture_output=True,text=True)
            home=Path(tmp)
            cli=home/'.local/bin/omatask'
            subprocess.run([str(cli),'add','Keep this task'],env=env,check=True,capture_output=True)
            subprocess.run(args,env=env,check=True,capture_output=True,text=True)
            result=subprocess.check_output([str(cli),'--json','list'],env=env,text=True)
            self.assertIn('Keep this task',result)
            bindings=(home/'.config/hypr/bindings.lua').read_text()
            self.assertIn('-- Existing personal binding',bindings)
            self.assertEqual(bindings.count('-- BEGIN OMATASK'),1)
            plugin = home / '.config/omarchy/plugins/local.omatask'
            self.assertTrue((plugin/'integrations/omarchy/Widget.qml').exists())
            self.assertTrue((plugin/'manifest.json').exists())
            self.assertFalse((home/'.config/systemd/user/omatask-reminders.service').exists())
            installed_docs = plugin / 'docs'
            self.assertEqual({path.name for path in installed_docs.iterdir()},
                             {'ARCHITECTURE.md', 'RELEASE_NOTES.md', 'TESTING.md',
                              'GUIDE.md', 'CLI.md', 'PLUGIN.md'})
            self.assertEqual(len(list((home/'.local/state/omatask/backups').iterdir())),2)
            snapshots=list((home/'.local/state/omatask/backups').glob('*/tasks.db'))
            self.assertEqual(len(snapshots),1)
            restored=subprocess.check_output([str(cli),'--db',str(snapshots[0]),'--json','list'],env=env,text=True)
            self.assertIn('Keep this task',restored)

    def test_git_checkout_survives_in_place_setup_and_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.setup_home(tmp)
            plugin = Path(tmp) / '.config/omarchy/plugins/local.omatask'
            sys.path.insert(0, str(ROOT / 'scripts'))
            from release_files import copy_public
            copy_public(ROOT, plugin)
            subprocess.run(['git', 'init', '-q', str(plugin)], check=True)
            (plugin / 'user-notes.txt').write_text('preserve checkout notes')
            before = (plugin / '.git/config').read_bytes()
            script = plugin / 'scripts/install-desktop.py'
            subprocess.run([sys.executable, str(script)], env=env, check=True, capture_output=True)
            self.assertEqual((plugin / '.git/config').read_bytes(), before)
            self.assertEqual((plugin / 'user-notes.txt').read_text(), 'preserve checkout notes')
            launcher = Path(tmp) / '.local/bin/omatask'
            self.assertIn(str(plugin / 'scripts/omatask-backend'), launcher.read_text())
            # Changes from a future plugin update are used by the launcher immediately.
            backend = plugin / 'scripts/omatask-backend'
            backend.write_text('print("updated backend")\n')
            self.assertEqual(subprocess.check_output([str(launcher)], text=True).strip(), 'updated backend')
            result = subprocess.run([sys.executable, str(ROOT/'scripts/install-desktop.py')], env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Git checkout', result.stderr)
            self.assertEqual(backend.read_text(), 'print("updated backend")\n')

    def test_legacy_worker_is_backed_up_and_retired(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.setup_home(tmp)
            unit = Path(tmp) / '.config/systemd/user/omatask-reminders.service'
            unit.parent.mkdir(parents=True)
            content = (ROOT / 'integrations/systemd/omatask-reminders.service').read_bytes()
            unit.write_bytes(content)
            subprocess.run([sys.executable, str(ROOT/'scripts/install-desktop.py')], env=env, check=True, capture_output=True)
            self.assertFalse(unit.exists())
            backups = list((Path(tmp)/'.local/state/omatask/backups').glob('*/omatask-reminders.service'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), content)

    def test_uninstall_preserves_data_personal_keys_and_modified_launchers(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = self.setup_home(tmp)
            home = Path(tmp)
            subprocess.run([sys.executable, str(ROOT/'scripts/install-desktop.py')], env=env, check=True, capture_output=True)
            cli = home / '.local/bin/omatask'
            subprocess.run([str(cli), 'add', 'Keep this task'], env=env, check=True, capture_output=True)
            cli.write_text('#!/bin/sh\n# custom replacement\n')
            subprocess.run([sys.executable, str(ROOT/'scripts/uninstall-desktop.py')], env=env, check=True, capture_output=True)
            self.assertTrue(cli.exists())
            self.assertFalse((home/'.local/bin/omatask-panel').exists())
            self.assertFalse((home/'.local/share/applications/omatask.desktop').exists())
            keys = (home/'.config/hypr/bindings.lua').read_text()
            self.assertIn('-- Existing personal binding', keys)
            self.assertNotIn('-- BEGIN OMATASK', keys)
            backend = home/'.config/omarchy/plugins/local.omatask/scripts/omatask-backend'
            tasks = json.loads(subprocess.check_output([sys.executable, str(backend), '--json', 'list'], env=env, text=True))
            self.assertEqual(tasks[0]['title'], 'Keep this task')

    def test_key_conflict_aborts_before_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=self.setup_home(tmp);env['OMATASK_TEST_CONFLICT']='1'
            result=subprocess.run([sys.executable,str(ROOT/'scripts/install-desktop.py')],env=env,capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('occupied',result.stderr)
            self.assertFalse((Path(tmp)/'.local/bin/omatask').exists())
