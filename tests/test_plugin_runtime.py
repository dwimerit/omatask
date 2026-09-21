"""Opt-in offscreen Quickshell lifecycle test, with no desktop or real notifier."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(os.environ.get('OMATASK_QML_TESTS') == '1' and shutil.which('qs'),
                     'Set OMATASK_QML_TESTS=1 with Quickshell installed')
class PluginRuntimeTests(unittest.TestCase):
    def test_service_stops_on_unload_and_restarts_with_current_settings(self):
        with tempfile.TemporaryDirectory(prefix='omatask-service-') as folder:
            root = Path(folder)
            backend = root / 'fake backend.py'
            backend.write_text('#!/usr/bin/python3\nimport os,sys,time,json\n'
                'with open(os.environ["OMATASK_TEST_CALLS"],"a") as f:\n'
                '    f.write(json.dumps({"pid":os.getpid(),"args":sys.argv[1:]})+"\\n")\n'
                'time.sleep(30)\n')
            backend.chmod(0o755)
            calls = root / 'calls.jsonl'
            source = (ROOT / 'integrations/omarchy/Service.qml').as_uri()
            config = {'barConfig': {'layout': {'right': [{'id': 'local.omatask',
                       'executable': str(backend), 'database': str(root / 'custom tasks.db')}]}}}
            harness = root / 'shell.qml'
            harness.write_text('''import QtQuick
import Quickshell
ShellRoot {
  Loader { id: worker; active: true; source: SOURCE; onLoaded: item.shell = SETTINGS }
  Timer { interval: 1000; running: true; onTriggered: worker.active = false }
  Timer { interval: 1600; running: true; onTriggered: worker.active = true }
  Timer { interval: 2600; running: true; onTriggered: worker.active = false }
  Timer { interval: 3100; running: true; onTriggered: Qt.quit() }
}
'''.replace('SOURCE', json.dumps(source)).replace('SETTINGS', json.dumps(config)))
            runtime = root / 'runtime'
            runtime.mkdir(mode=0o700)
            env = dict(os.environ, HOME=str(root), XDG_RUNTIME_DIR=str(runtime),
                       XDG_CONFIG_HOME=str(root/'config'), XDG_CACHE_HOME=str(root/'cache'),
                       QT_QPA_PLATFORM='offscreen', QT_QPA_PLATFORMTHEME='',
                       QT_QUICK_CONTROLS_STYLE='Basic', QT_STYLE_OVERRIDE='Fusion',
                       QT_QUICK_BACKEND='software', DISPLAY='', WAYLAND_DISPLAY='',
                       DBUS_SESSION_BUS_ADDRESS='unix:path=/dev/null', OMATASK_TEST_CALLS=str(calls))
            result = subprocess.run(['qs', '--no-color', '-p', str(harness)], env=env,
                                    capture_output=True, text=True, timeout=10)
            try:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertTrue(calls.exists(), result.stdout + result.stderr)
                entries = [json.loads(line) for line in calls.read_text().splitlines()]
                self.assertEqual(len(entries), 2, result.stdout + result.stderr)
                for entry in entries:
                    self.assertEqual(entry['args'], ['--db', str(root/'custom tasks.db'), 'worker', '--once'])
                    with self.assertRaises(ProcessLookupError):
                        os.kill(entry['pid'], 0)
            finally:
                if calls.exists():
                    for line in calls.read_text().splitlines():
                        try:
                            os.kill(json.loads(line)['pid'], 15)
                        except ProcessLookupError:
                            pass
