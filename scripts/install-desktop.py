#!/usr/bin/env python3
"""Install a local plugin snapshot and optional launchers/shortcuts without sudo."""
import argparse
from contextlib import closing
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess
import tempfile
from release_files import copy_public, public_files

ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ID = 'local.omatask'
BEGIN = '-- BEGIN OMATASK (managed by install-desktop.py)'
END = '-- END OMATASK'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def managed_text(text):
    if text.count(BEGIN) != text.count(END) or text.count(BEGIN) > 1:
        raise ValueError('Malformed Omatask shortcut block; repair it before setup')
    if BEGIN in text and text.index(END) < text.index(BEGIN):
        raise ValueError('Malformed Omatask shortcut block')
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-keys', action='store_true')
    parser.add_argument('--restart-shell', action='store_true', help='Refresh the Quickshell component cache')
    args = parser.parse_args()
    home = Path.home()
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    state = Path(os.environ.get('XDG_STATE_HOME', home / '.local/state')) / 'omatask'
    prefix = home / '.local'
    plugin = config / 'omarchy/plugins' / PLUGIN_ID
    in_place = plugin.resolve() == ROOT
    # Never replace a checkout owned by Omarchy's Git-based plugin manager.
    if not in_place and (plugin / '.git').exists():
        raise SystemExit('Plugin is a Git checkout. Update it with omarchy plugin update local.omatask; run setup from that checkout.')
    list(public_files(ROOT))
    bindings = config / 'hypr/bindings.lua'
    original = bindings.read_text() if bindings.exists() else None
    text = managed_text(original or '')
    keys = [('SUPER + ALT + T', 'Omatask: tasks', 'omarchy-shell shell toggle local.omatask'),
            ('SUPER + ALT + N', 'Omatask: new task', str(prefix / 'bin/omatask-panel') + ' quick')]
    service = config / 'systemd/user/omatask-reminders.service'
    if service.exists() and service.read_bytes() != (ROOT / 'integrations/systemd/omatask-reminders.service').read_bytes():
        raise SystemExit('Custom omatask-reminders.service found. Disable and archive it manually before migrating to plugin-managed reminders.')
    run('omarchy-shell', 'shell', 'ping', stdout=subprocess.DEVNULL)
    if not args.without_keys and BEGIN not in text:
        actual = json.loads(run('hyprctl', 'binds', '-j', capture_output=True).stdout)
        for key, _, _ in keys:
            letter = key.split(' + ')[-1]
            if any(b.get('modmask') == 72 and str(b.get('key', '')).upper() == letter for b in actual):
                raise SystemExit(f'{key} is occupied. Choose other keys or use --without-keys.')
    backup = state / 'backups' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup.mkdir(parents=True, mode=0o700)
    database = Path(os.environ.get('XDG_DATA_HOME', home / '.local/share')) / 'omatask/tasks.db'
    if database.is_file():
        snapshot = backup / 'tasks.db'
        with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True)) as source_db, closing(sqlite3.connect(snapshot)) as backup_db:
            source_db.backup(backup_db)
        snapshot.chmod(0o600)
    for source, name in [(config / 'omarchy/shell.json', 'shell.json'), (bindings, 'bindings.lua'),
                         (service, 'omatask-reminders.service')]:
        if source.exists():
            shutil.copy2(source, backup / name)
    updating = plugin.exists()
    changed = False
    if not in_place:
        def widget_files(directory):
            return {str(p.relative_to(directory)): p.read_bytes() for p in directory.rglob('*')
                    if p.is_file() and p.suffix in ('.qml', '.js')}
        old_widgets = plugin / 'integrations/omarchy' if (plugin / 'integrations/omarchy').is_dir() else plugin
        changed = updating and widget_files(old_widgets) != widget_files(ROOT / 'integrations/omarchy')
        if updating:
            shutil.copytree(plugin, backup / 'plugin', symlinks=True)
        plugin.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.omatask-stage-', dir=config / 'omarchy'))
        try:
            copy_public(ROOT, stage)
            run('omarchy', 'plugin', 'validate', str(stage))
            if updating:
                old = stage.with_name(stage.name + '-old')
                os.replace(plugin, old)
                try:
                    os.replace(stage, plugin)
                except BaseException:
                    os.replace(old, plugin)
                    raise
                shutil.rmtree(old)  # Already backed up, never a Git checkout.
            else:
                os.replace(stage, plugin)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    # Migrate the old standalone worker. The plugin service now owns reminders.
    if service.exists():
        run('systemctl', '--user', 'disable', '--now', 'omatask-reminders.service')
        service.unlink()
        run('systemctl', '--user', 'daemon-reload')
    files = {
        prefix / 'bin/omatask': '#!/bin/sh\n# Omatask managed launcher\nexec /usr/bin/python3 ' + shlex.quote(str(plugin / 'scripts/omatask-backend')) + ' "$@"\n',
        prefix / 'bin/omatask-panel': (ROOT / 'scripts/omatask-panel').read_text(),
        prefix / 'share/applications/omatask.desktop': (ROOT / 'integrations/omatask.desktop').read_text(),
    }
    ownership = {}
    for path, content in files.items():
        if path.exists():
            shutil.copy2(path, backup / path.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        path.chmod(0o755 if path.parent.name == 'bin' else 0o644)
        ownership[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    ownership_path = state / 'desktop-install.json'
    ownership_path.write_text(json.dumps(ownership, indent=2) + '\n')
    ownership_path.chmod(0o600)
    if not args.without_keys:
        block = BEGIN + '\n' + '\n'.join('o.bind(' + ', '.join(json.dumps(v) for v in entry) + ')' for entry in keys) + '\n' + END
        if BEGIN in text:
            text = text[:text.index(BEGIN)] + block + text[text.index(END) + len(END):]
        else:
            text = text.rstrip() + '\n\n' + block + '\n'
        bindings.parent.mkdir(parents=True, exist_ok=True)
        bindings.write_text(text)
        run('hyprctl', 'reload')
        errors = run('hyprctl', 'configerrors', capture_output=True).stdout.strip()
        if errors:
            if original is None:
                bindings.unlink()
            else:
                bindings.write_text(original)
            run('hyprctl', 'reload')
            raise SystemExit('Hyprland reports errors; bindings restored:\n' + errors)
    run('omarchy-shell', 'shell', 'rescanPlugins')
    if updating:
        run('omarchy', 'plugin', 'enable', PLUGIN_ID)
    else:
        run('omarchy', 'plugin', 'enable', PLUGIN_ID, '--section', 'right')
    if changed or args.restart_shell:
        run('omarchy', 'restart', 'shell')
    print('Desktop setup complete. Backups:', backup)


if __name__ == '__main__':
    main()
