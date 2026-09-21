#!/usr/bin/env bash
# No network, sudo, pip, or edits to existing shell/Hyprland configuration.
set -euo pipefail
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
prefix="${OMATASK_PREFIX:-$HOME/.local}"
python3 -c 'import sys, sqlite3, curses, zoneinfo; assert sys.version_info >= (3,11), "Python 3.11+ required"'
install -d "$prefix/bin" "$prefix/share/omatask" "$prefix/share/applications"
# Versioned code directories and an atomic pointer switch keep updates restart-safe.
release="$(mktemp -d "$prefix/share/omatask/release.XXXXXXXX")"
# The same explicit public-file list is used for plugin snapshots and archives.
python3 - "$source_dir" "$release" <<'PY'
import pathlib, sys
sys.dont_write_bytecode = True
source, release = map(pathlib.Path, sys.argv[1:])
sys.path.insert(0, str(source / 'scripts'))
from release_files import copy_public
copy_public(source, release)
PY
python3 - "$prefix" "$release" <<'PY'
import os, pathlib, shlex, sys
prefix, release = map(pathlib.Path, sys.argv[1:])
base = prefix / 'share/omatask'
tmp = base / ('current.' + str(os.getpid()))
tmp.symlink_to(release.name)
os.replace(tmp, base / 'current')
wrapper = prefix / 'bin/omatask'
script = '#!/bin/sh\nexport PYTHONPATH=' + shlex.quote(str(base / 'current')) + '\nexec /usr/bin/python3 -m omatask "$@"\n'
tmp_wrapper = wrapper.with_name('omatask.' + str(os.getpid()))
tmp_wrapper.write_text(script)
tmp_wrapper.chmod(0o755)
os.replace(tmp_wrapper, wrapper)
PY
install -m 755 "$source_dir/scripts/omatask-panel" "$prefix/bin/omatask-panel"
install -m 644 "$source_dir/integrations/omatask.desktop" "$prefix/share/applications/omatask.desktop"
printf 'Installed %s/bin/omatask\nData untouched. See README for optional shell plugin and reminder service.\n' "$prefix"
