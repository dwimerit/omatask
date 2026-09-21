import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from release_files import copy_public


class PackagingTests(unittest.TestCase):
    def test_source_bundle_runs_without_installation_and_keeps_data_outside_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin = root / 'plugin with spaces'
            copy_public(ROOT, plugin)
            self.assertFalse((plugin / 'docs/VALIDATION.md').exists())
            self.assertFalse((plugin / 'docs/screenshots').exists())
            self.assertFalse(list(plugin.rglob('__pycache__')))
            env = dict(os.environ, HOME=str(root/'home'), XDG_DATA_HOME=str(root/'data'))
            backend = [sys.executable, str(plugin / 'scripts/omatask-backend')]
            subprocess.run(backend + ['add', 'Bundled widget task'], cwd='/', env=env, check=True, capture_output=True)
            result = subprocess.check_output(backend + ['--json', 'list'], cwd='/', env=env, text=True)
            self.assertEqual(json.loads(result)[0]['title'], 'Bundled widget task')
            self.assertFalse(list(plugin.rglob('*.db')))
            self.assertFalse(list(plugin.rglob('__pycache__')))
            self.assertTrue((root/'data/omatask/tasks.db').is_file())

    def test_release_archive_is_private_data_free_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)/'source.tar.gz'
            command = [sys.executable, str(ROOT/'scripts/prepare-release.py'), '--output', str(target)]
            subprocess.run(command, check=True, capture_output=True)
            with tarfile.open(target) as archive:
                names = archive.getnames()
                self.assertTrue(any(name.endswith('/manifest.json') for name in names))
                self.assertTrue(any(name.endswith('/LICENSE') for name in names))
                self.assertTrue(any(name.endswith('/tests/test_packaging.py') for name in names))
                for name in names:
                    self.assertNotIn('/.git/', name)
                    self.assertNotIn('VALIDATION.md', name)
                    self.assertNotIn('/screenshots/', name)
                    self.assertNotIn('__pycache__', name)
                    self.assertFalse(name.endswith(('.db', '.log')))
                self.assertTrue(all(not item.issym() for item in archive.getmembers()))
            original = target.read_bytes()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(target.read_bytes(), original)
