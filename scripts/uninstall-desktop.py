#!/usr/bin/env python3
"""Remove optional launchers/shortcuts; retain tasks, configuration and backups."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

BEGIN = '-- BEGIN OMATASK (managed by install-desktop.py)'
END = '-- END OMATASK'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--remove-plugin', action='store_true', help='Also remove the plugin with Omarchy')
    args = parser.parse_args()
    home = Path.home()
    config = Path(os.environ.get('XDG_CONFIG_HOME', home / '.config'))
    state = Path(os.environ.get('XDG_STATE_HOME', home / '.local/state')) / 'omatask'
    ownership_path = state / 'desktop-install.json'
    ownership = json.loads(ownership_path.read_text()) if ownership_path.exists() else {}
    bindings = config / 'hypr/bindings.lua'
    original = bindings.read_text() if bindings.exists() else ''
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1 or (BEGIN in original and original.index(END) < original.index(BEGIN)):
        raise SystemExit('Malformed shortcut block; nothing removed')
    if BEGIN in original:
        backup = state / 'backups' / ('uninstall-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.mkdir(parents=True, mode=0o700)
        shutil.copy2(bindings, backup / 'bindings.lua')
        text = original[:original.index(BEGIN)] + original[original.index(END) + len(END):]
        bindings.write_text(text)
        subprocess.run(['hyprctl', 'reload'], check=True)
        errors = subprocess.check_output(['hyprctl', 'configerrors'], text=True).strip()
        if errors:
            bindings.write_text(original)
            subprocess.run(['hyprctl', 'reload'], check=True)
            raise SystemExit('Hyprland reports errors; bindings restored:\n' + errors)
    allowed = {str(home / '.local' / relative) for relative in
               ('bin/omatask', 'bin/omatask-panel', 'share/applications/omatask.desktop')}
    retained = {}
    for filename, digest in ownership.items():
        path = Path(filename)
        if filename not in allowed:
            raise SystemExit('Invalid launcher ownership record')
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            retained[filename] = digest
            print('Kept modified launcher:', path)
        else:
            path.unlink()
    if retained:
        ownership_path.write_text(json.dumps(retained, indent=2) + '\n')
    elif ownership_path.exists():
        ownership_path.unlink()
    if args.remove_plugin:
        subprocess.run(['omarchy', 'plugin', 'remove', 'local.omatask', '--yes'], check=True)
    print('Optional desktop setup removed. Task data and backups retained.')


if __name__ == '__main__':
    main()
