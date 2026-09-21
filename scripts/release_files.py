"""Copy an explicit source-only distribution; never include local reports or data."""
from pathlib import Path
import shutil

ROOT_FILES = ('.gitignore', 'README.md', 'manifest.json', 'pyproject.toml',
              'LICENSE', 'THIRD_PARTY_NOTICES.md')
DOCS = ('ARCHITECTURE', 'RELEASE_NOTES', 'TESTING', 'GUIDE', 'CLI', 'PLUGIN')
SCRIPTS = ('install.sh', 'install-desktop.py', 'uninstall-desktop.py',
           'release_files.py', 'prepare-release.py', 'omatask-backend', 'omatask-panel',
           'generate-notification-sound.py', 'desktop-smoke.py',
           'desktop-delete-smoke.py', 'desktop-reminder-smoke.py')


def public_files(root, include_tests=False):
    root = Path(root)
    names = [Path(name) for name in ROOT_FILES]
    names += [Path('docs') / (name + '.md') for name in DOCS]
    names += [Path('scripts') / name for name in SCRIPTS]
    for folder, suffixes in (('omatask', {'.py', '.wav'}),
                             ('integrations', {'.qml', '.js', '.service', '.desktop', '.lua', '.jsonc'})):
        names += [path.relative_to(root) for path in (root / folder).rglob('*')
                  if path.is_file() and path.suffix in suffixes]
    if include_tests:
        names += [path.relative_to(root) for path in (root / 'tests').rglob('*')
                  if path.is_file() and path.suffix in {'.py', '.c', '.xml'}]
    for name in sorted(set(names)):
        path = root / name
        if any(part.is_symlink() for part in (path, *path.parents) if part != root.parent):
            raise ValueError(f'Release files must not use symlinks: {name}')
        if not path.is_file():
            raise ValueError(f'Missing release file: {name}')
        yield name


def copy_public(root, destination, include_tests=False):
    root, destination = Path(root), Path(destination)
    names = list(public_files(root, include_tests))  # Validate before writing.
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
