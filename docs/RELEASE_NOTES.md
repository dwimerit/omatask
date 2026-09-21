# Omatask 0.4.0

The repository is now an installable Omarchy plugin with a root manifest and MIT
license. The widget invokes its bundled Python backend, and a singleton Omarchy
service delivers reminders without a separate systemd installation. Disabling or
removing the plugin stops that service while preserving task data.

Optional desktop setup preserves Git-managed checkouts and adds launchers that
follow plugin updates. Local snapshots exclude private artifacts. Existing
unmodified systemd units are backed up and retired during migration. The new
cleanup script preserves data, personal shortcuts and modified launchers.

Prepare a local source archive with `python3 scripts/prepare-release.py`.
Schema remains v4.

The description now emphasizes the offline widget: local SQLite storage, no
account, cloud sync or telemetry. Privacy documentation explains optional phone
forwarding and the boundaries of desktop notifications and user-selected storage.
Automated checks exercise the bundled backend with network attempts blocked and
fake desktop commands, including the default and opt-in phone delivery paths.
Detailed configuration and terminal commands have separate guides; plugin packaging
requirements are documented separately.

Empty task and subtask IDs are rejected instead of matching the only existing
item, preventing accidental changes or deletion when a shell variable is empty.

Notification backend errors omit task text, command arguments and device IDs.
Exports and SQLite backups are created with owner-only permissions. Backup
creation reserves the destination exclusively, including rejection of dangling
symlinks. Public testing instructions replace links to personal validation reports;
the installer copies only public documentation.

Optional OmaConnect phone reminders use KDE Connect's text ping to a configured
paired, reachable device. Enable the `omaconnect` section in `config.json`; it is
off by default and respects desktop Do Not Disturb unless configured otherwise.
Missing dependencies, offline phones, and send failures are logged without
retrying the desktop notification. Phone delivery is best effort, without an
offline queue. See the [widget guide](GUIDE.md#phone-reminders-through-omaconnect-optional)
for pairing and configuration instructions.

# Omatask 0.3.1

Pressing `/` in an empty task input now opens search immediately, including after
opening the panel or quick entry with a keyboard shortcut. The slash is consumed
as a command and is not added to the query. Slashes inside titles remain ordinary
text. The input hint and built-in help describe this shortcut.

The search footer now shows **Esc exits search**. Escape clears the search filter
and returns to the task list, keeping the panel open. It also cancels a search
that has not been submitted yet.

# Omatask 0.3.0

Daily reminders now fit on one line:

```text
Drink water daily 8x 08:00-22:00
```

This creates eight reminders at 08:00, 10:00, 12:00, 14:00, 16:00, 18:00,
20:00 and 22:00 in the task's time zone. Complete the task once after meeting
the day's goal to schedule the following day. Individual glasses are not counted.

- Add `tomorrow` to start with a full day, or `count 30` to limit the series to
  thirty days. Without a date, it starts today unless the window has ended.
  Earlier slots on the creation day are skipped.
- The longer form is `Drink water daily goal 8 between 08:00-22:00`.
  Times stay local across daylight-saving changes. Other window sizes are
  distributed evenly and rounded to minutes; `1x` uses the end of the window.
- The widget shows the daily reminder window in the list and every time in the
  task details.
- Built-in help is now entirely in English, with twelve editable examples.
  Open it with **F1** or **?**. **Insert example** fills the input without saving.
- The desktop installer creates a consistent SQLite backup before upgrading the
  default database, alongside its existing configuration backups.

## Upgrade

Run `python3 scripts/install-desktop.py` from the project directory. Widget code
updates restart the Omarchy shell to clear its component cache; the task database
and existing widget position are preserved.

Schema 4 adds local-time reminder rules. Existing databases migrate automatically,
and JSON exports from schema 3 can still be imported. Older releases cannot open
schema 4: use a pre-upgrade database backup when rolling back. Back up custom
databases explicitly with `omatask --db PATH backup COPY` before updating.

## Validation

Automated tests cover task lifecycle, reminders, recurrence, DST, migration,
import/export, CLI, TUI and installation. See [the testing guide](TESTING.md)
for reproducible checks and [the widget guide](GUIDE.md#testing-and-limitations)
for known limits. The widget targets Omarchy 4.0.0.alpha's
Quickshell plugin API.
