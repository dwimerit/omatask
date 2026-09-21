# Testing and preparing a release

Run commands from the project root with Python 3.11+ and system tzdata installed.
Tests and synthetic fixtures belong in the repository. Reports from a personal
desktop session, screenshots, task databases, exports and backups stay local.

## Automated checks

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/install.sh
python3 -m compileall -q omatask scripts tests
```

With Omarchy installed, validate the current plugin directory:

```bash
omarchy plugin validate .
```

This validates the root manifest and both entry points. See
[plugin packaging](PLUGIN.md) for release preparation and submission.

The suite covers recurrence and DST, task lifecycle, reminder retry and restart,
daily reminder windows, migrations, JSON import/export, CLI exit codes, Unicode
input in a PTY, widget snapshots, concurrent workers and installation in an
isolated HOME. Notification backends are mocked: these checks do not send desktop
or phone messages, modify desktop settings or use your task database. The TUI
test needs a usable PTY and terminfo. Installation tests use fake desktop commands.
Privacy regressions cover notification errors and permissions on export/backup
files. `test_privacy.py` runs the bundled backend with an isolated HOME and PATH,
blocks and records Python socket operations and unexpected child processes, and
checks task entry, widget snapshots, reminders, export, backup and restore. Fake
desktop commands confirm that even an available KDE Connect client is not called
by default, and that explicit opt-in forwards only the documented reminder fields.
These checks cover Omatask's backend; they do not audit the network behavior of the
real desktop services, custom backends or file-sync tools. QML network/resource
access and process launches must also be reviewed when changing widget code.
The runner prints the current test count; no saved run report is required.

For changes to the native widget, also run Qt 6's `qmllint` with imports from the
target Omarchy shell. Consult `qmllint --help` for import-path options; Qt 5's
tool cannot validate this Qt 6 widget. Resolve errors and check dynamic host API
warnings in a live session. Automated Python tests do not prove visual or shortcut
compatibility with a different Omarchy version.

With Quickshell installed, run the isolated offscreen service lifecycle check:

```bash
OMATASK_QML_TESTS=1 python3 -m unittest discover -s tests -p test_plugin_runtime.py -v
```

It starts a synthetic offscreen test host, uses a fake backend and temporary HOME,
and checks that unloading stops the child process and loading again restarts it.
It does not connect to the active desktop, session D-Bus or notification server.
The regular Python suite skips this optional test unless explicitly enabled.

## Optional live desktop checks

These checks require an installed Omatask plugin and its reminder service in a
running Omarchy session, plus the optional desktop setup for launchers/shortcuts.
They control the real keyboard or pointer, create temporary tasks in the
configured default database, and can send notifications and play sound. Run them
only when the desktop is idle. Keep the CLI, widget and worker on the same database.

```bash
python3 scripts/desktop-smoke.py --shortcuts-only
python3 scripts/desktop-smoke.py
python3 scripts/desktop-delete-smoke.py
python3 scripts/desktop-reminder-smoke.py --delay 15
```

- `desktop-smoke.py`: quick entry, search, edits, task lifecycle and notifications.
  The shortcuts-only mode checks registered commands, search and Escape without
  creating tasks. It does not emulate physical global shortcut keypresses.
- `desktop-delete-smoke.py`: pointer selection and deletion confirmation. Requires
  wtype, grim, wayland-scanner, a C compiler and libwayland-client. Its pointer
  helper requires unrotated outputs at scale 1 with a layout starting at (0, 0).
- `desktop-reminder-smoke.py`: a deadline-only task and delivery by the real worker;
  defaults to a one-minute delay. The check also attempts to observe audio playback.

The full checks use unique task tags and attempt cleanup in `finally` blocks.
After a crash or forced termination, inspect any remaining test tasks before
removing them. The scripts save screenshots under `/tmp/omatask-*.png`; these can
include personal content. Desktop logs and failure output may also contain task
data, paths or details about the session. Do not attach them to public issues
without inspecting and redacting them first.

## Publication checklist

1. Run the automated checks above. Review code, documentation links and CLI examples.
2. Keep local reports and screenshots in `.local/`, `reports/`, or the ignored
   legacy paths `docs/VALIDATION.md` and `docs/screenshots/`. Keep personal exports
   and backups outside the project or in ignored `exports/` and `backups/` folders.
   Arbitrary export filenames are not automatically ignored.
3. Inspect the actual staged content before a commit:

   ```bash
   git status --short --ignored
   git diff --cached --stat
   git diff --cached
   git ls-files
   ```

   Include source tests, integration examples and public documentation. Exclude
   personal task data, device IDs, config files, logs, credentials and screenshots
   from a personal session. The installer copies only the public documentation.
4. `.gitignore` does not remove files already tracked or erase earlier commits.
   If private artifacts were tracked, remove the specific paths from the index
   with `git rm --cached` (use `-r` for a directory), preserving local copies.
   Inspect history before pushing; a new deletion commit leaves old content in
   history. If secrets were already published, revoke them as well.
5. Keep the package, `omatask/__init__.py` and plugin manifest versions aligned
   when making a release. Move finished changes from Unreleased into the release
   notes. Preserve LICENSE and THIRD_PARTY_NOTICES.md in distributions.

For public UI screenshots, use a separate demo database containing invented tasks
and inspect the complete image before adding it to the repository.
