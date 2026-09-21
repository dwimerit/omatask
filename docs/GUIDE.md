# Widget guide

[Back to Omatask](../README.md)

## Quick-entry syntax

| Element | Syntax |
|---|---|
| Date | today, tomorrow, monday…sunday, YYYY-MM-DD |
| Time | HH:MM after a date; on its own, the next occurrence of that time |
| Duration from now | in 30m / in 2h / in 3d |
| Priority/tags/project | !high #work +Work or +"Side Project" |
| Recurrence | daily / weekly / monthly / every 2h / every 3d / every 2w / every 2mo |
| Weekdays | every mon,wed,fri |
| Several reminders each day | daily 8x 08:00-22:00 |
| Series limit | count 30 / until 2026-12-31T23:59 |
| Reminder | remind 30m / remind at 10:00 / remind at "tomorrow 10:00" |

You can repeat `remind` to add several reminders. Recurrence requires a first
deadline, which may also be supplied using `--due`. A date without a time means
09:00 for today/tomorrow/weekday keywords and 00:00 for an ISO date. A weekday
means the nearest matching day, including today: a past time today stays overdue.
`until` is inclusive at the specified instant; use `T23:59:59` to include a full day.
Reserved keywords are parsed as metadata; `--literal` disables the parser.
CLI flags override inline title metadata for dates, priority, tags, project and
recurrence; `--remind` and `--remind-at` add to inline reminders. Recurrence
modifiers such as `--count` require `--repeat`, even with inline `daily`.
Input uses a lightweight
English grammar, not general-purpose natural-language processing.

### Daily goal: eight reminders

```text
Drink water daily 8x 08:00-22:00
```

This creates one daily task with eight reminders: 08:00, 10:00, 12:00, 14:00,
16:00, 18:00, 20:00 and 22:00. The longer spelling is
`Drink water daily goal 8 between 08:00-22:00`. The schedule appears in task details.
Complete the task once after meeting your daily goal to schedule the following day.
Individual glasses are not counted.

Without a date, the task starts today, or tomorrow if the window has ended.
Earlier slots on the creation day are skipped. Add `tomorrow` before
`daily 8x 08:00-22:00` to start with a full day. `count 30` limits the series to
thirty days; `8x` is the number of reminders per day. Times remain local across
daylight-saving changes.

The window must fit within one day. Reminders are spaced evenly between its
endpoints and rounded to the nearest minute, with at least one minute between
reminders. `1x` means one reminder at the end of the window. The task deadline is
the end of the window. This syntax requires daily recurrence and cannot be
combined with inline `remind` settings.

## Widget controls and settings

The widget targets the `4.0.0.alpha` source and the
[quattro plugin documentation](https://github.com/omacom/omarchy/blob/quattro/manual/32-shell-plugins.md).
Install and update the complete plugin as described below. The Python backend
and reminder service are included in the repository.

The bar shows the number of active tasks due **today**, with overdue tasks shown
separately as `N!`. It refreshes every ten seconds, every three seconds while the
list is open, and immediately on both monitors after an action. Colors, fonts,
dimensions, hover states and popups follow the Omarchy theme.

- Left click / **Super+Alt+T**: open the native task list and quick input.
- Right click / **Super+Alt+N**: quick entry; the panel closes after creating a task.
- Middle click / **o** in the list: open the full terminal editor.
- **?** in the header or **F1**: built-in English help for all task creation options,
  including dates, durations, recurrence, reminders, priorities, tags, projects
  and CLI flags. **Insert example** fills the input for editing; Enter creates
  the task. Scroll with the mouse wheel, arrows, PgUp or PgDn; Esc returns to
  the input. Opening and closing help preserves your draft.
- Enter in the input: submit; Down or Tab: focus the list.
- **/** in an empty task input: switch directly to search, including immediately
  after opening the panel or quick entry. A slash inside a title remains text.
- **Esc** during search: clear the filter and return to the task list, keeping
  the panel open. The footer shows **Esc exits search**.
- Up/Down or j/k: select; d: complete; r: reopen; c: cancel.
- a: add; /: search; e: title; m: project; t: tags; p: priority.
- s: snooze, with 10m/30m/1h/evening/tomorrow choices.
- Clicking a row selects it with a border. The **Delete** button on the right,
  **Delete**, or **x** (also the equivalent key on a Russian keyboard layout)
  opens a dialog with the task title and Cancel / Delete buttons. Cancel is
  selected by default; Esc cancels, and Right followed by Enter confirms deletion.
- f/Tab in the list: next view; Enter: details; Esc: back/close.
- All includes every status, so cancelled tasks can also be reopened.

Global shortcuts require the optional desktop setup below. Keyboard launches use the focused monitor. Input is passed as an argument array
without shell interpolation; titles and descriptions render as plain text.
Errors remain visible in the panel and preserve your input. The core implements
all date and recurrence rules. The widget's `database` setting selects another
database; `executable` selects another compatible backend. By default the widget
and reminder service use the bundled `scripts/omatask-backend` through Python.
Both read the same bar settings. Custom paths must be absolute; `~` is not expanded. If the backend is unavailable, the bar shows
`Tasks: !`; the error clears when the backend recovers.

Commands: `omatask-panel toggle|open|close|quick`, `omatask widget today --query deploy`.
`omatask bar` remains compatible with Waybar. For per-monitor diagnostics, use
`omarchy-shell local.omatask-DP-1 status`, replacing DP-1 with your output name.

To configure shortcuts manually, add the contents of
[integrations/hypr-bindings.lua](../integrations/hypr-bindings.lua) to
`~/.config/hypr/bindings.lua`. First check `omarchy menu keybindings --print`:
the suggested Super+Alt+T/N shortcuts may already be in use. Choose free keys,
or use `hl.unbind` when intentionally replacing a binding. After editing, run
`hyprctl reload` and `hyprctl configerrors`.

Omarchy source files are not modified.

## Installation

Install and update through Omarchy:

```bash
omarchy plugin add https://github.com/dwimerit/omatask.git --enable
omarchy plugin update local.omatask
```

The plugin contains its own Python backend. Enabling it starts one reminder
service in the existing Omarchy shell, shared by all monitors. No pip, root access,
installer hook or separate systemd service is required. Disabling or removing the
plugin stops that service. Data stays in `$XDG_DATA_HOME/omatask/tasks.db`, or
`~/.local/share/omatask/tasks.db`, outside the plugin checkout.

Requirements: Omarchy 4.0.0.alpha / Quattro, Python 3.11+ with sqlite3 and system
tzdata. Notifications need libnotify (`notify-send`), a notification daemon and
the session D-Bus. Sound uses `pw-play` or `paplay`. The optional terminal editor
also uses curses, a terminal, uwsm and xdg-terminal-exec. Phone forwarding is off
by default and additionally needs KDE Connect.

### Local installation and optional shortcuts

For a local source checkout, or to add launchers and Super+Alt+T/N shortcuts to an
existing plugin checkout, run from that checkout:

```bash
python3 scripts/install-desktop.py
```

Use `--without-keys` to leave global shortcuts alone. The script checks conflicts,
backs up configuration and the default SQLite database to
`$XDG_STATE_HOME/omatask/backups/` (usually `~/.local/state/omatask/backups/`), then
installs an explicit source-only snapshot when needed. It does not copy local
reports, screenshots or task data. When run inside an installed Git checkout, it
leaves the checkout in place. It refuses to overwrite a Git-managed plugin from
another directory. Optional launchers follow the installed plugin's backend, so
subsequent plugin updates apply to both the widget and those launchers.

Upgrades from the old installer retire its unmodified `omatask-reminders.service`
after backing it up. A customized unit requires manual migration; setup stops
before changing it. The old application releases and task database are retained.
Widget code changes in a local snapshot can restart the shell to clear the alpha
QML cache. `--restart-shell` forces that refresh. Running applications stay open.

### Updates and backups

The plugin manager updates its checkout; it does not run the desktop installer.
Before upgrading a database schema, make an explicit backup with the bundled tool:

```bash
python3 ~/.config/omarchy/plugins/local.omatask/scripts/omatask-backend backup ~/omatask-backup.db
omarchy plugin update local.omatask
```

For a custom database, put `--db /absolute/path` before `backup`. Database schemas
migrate on first access by the new backend. Old code may require a pre-upgrade
backup when rolling back. If the alpha shell keeps stale components after an
update, run `omarchy restart shell`.

## Reminders and sound

A task with a deadline automatically gets a reminder **at its deadline**.
For example, `Reminder check in 1m` creates a task that displays a notification
and plays a sound a minute later, with up to ten seconds of polling delay.
`remind 30m` replaces the automatic reminder with one thirty minutes before the
deadline. You can specify several explicit reminders. A task without a deadline
does not notify unless you add a separate reminder or snooze it. Moving a deadline
moves the automatic reminder; removing the deadline cancels it. Recurring tasks
get reminders for each new occurrence.

After an upgrade, the worker adds missing reminders to active tasks with a
deadline that have neither reminder rules nor deliveries for the current occurrence.
Overdue reminders are delivered on the next poll. Existing explicit reminders,
snoozes and sent deliveries are preserved.

The plugin service checks the persistent queue every ten seconds. It starts with
the enabled plugin, uses the widget's database setting, and stops when the plugin
is disabled, removed, or the desktop shell exits. Missed reminders remain queued.
Each cycle runs the current bundled backend, so updates do not leave an old
Python worker running indefinitely. On failure it retries on the next cycle.

Diagnostics: `omarchy-shell local.omatask-reminders status` and the Omarchy shell
log. A separate systemd worker is only needed for optional terminal-only use;
see the [terminal reference](CLI.md#standalone-reminder-service).

Notifications use a short bundled chime with identical left and right channels.
Its default volume is 60% relative to system volume. Omarchy's Do Not Disturb
mode suppresses the sound. Optional settings go in
`$XDG_CONFIG_HOME/omatask/config.json`, usually `~/.config/omatask/config.json`:

```json
{
  "notification_sound": true,
  "notification_sound_volume": 0.6
}
```

Set `notification_sound: false` to disable sound. Volume accepts values from 0 to 1.
To use a custom sound, set `notification_sound_file` to its absolute file path.
Settings are reread for every notification; no restart is needed. Audio errors
are logged and do not cause an already delivered notification to be sent again.

## Privacy and data

Omatask works offline: task entry, search, recurrence and reminder scheduling run
on your computer. It has no accounts, cloud sync, analytics, telemetry or automatic
crash uploads. With default settings, the bundled widget and Python backend do
not make network requests or send task data to third-party servers.

Tasks are stored in `$XDG_DATA_HOME/omatask/tasks.db`, usually
`~/.local/share/omatask/tasks.db`. Exports and backups are ordinary files; Omatask
does not upload, encrypt or sync them. A cloud-synced or
network-mounted directory can move data elsewhere through software outside Omatask.

Desktop reminders pass the title, short task ID and deadline to the local
notification service through `notify-send`. That service may retain notification
history; other software may mirror it to another device. Omatask does not control
that mirroring. Sound playback and Do Not Disturb checks use local desktop tools.

Phone forwarding is a separate, optional exception to keeping reminders on this
computer. It is **off by default**, even when KDE Connect is installed. Enabling
`omaconnect.enabled` sends the title, short ID and deadline through KDE Connect to
the selected paired, reachable device. The following section explains setup and
how to turn it off. Omatask does not provide a cloud relay or sync the task database.

Installing or updating from GitHub downloads plugin code through Omarchy's plugin
manager; this is separate from task processing. These privacy properties describe
the bundled backend. If you choose a custom widget `executable`, its behavior
depends on that program.

## Phone reminders through OmaConnect (optional)

[OmaConnect](https://github.com/jitendradara12/omaconnect) manages devices through
KDE Connect. Omatask uses the same backend: `kdeconnect-cli --ping-msg` sends the
reminder text to a selected phone. This integration is disabled by default;
KDE Connect is not a required Omatask dependency.

1. Install OmaConnect using its project instructions and install KDE Connect on
   your phone. Pair the device in OmaConnect and allow KDE Connect notifications
   on the phone.
2. Find the ID of the paired, reachable phone: `kdeconnect-cli --list-available`.
3. Add the following section to your existing `~/.config/omatask/config.json`
   or `$XDG_CONFIG_HOME/omatask/config.json`, preserving your other settings:

```json
{
  "omaconnect": {
    "enabled": true,
    "device_id": "YOUR_PHONE_DEVICE_ID",
    "respect_dnd": true
  }
}
```

Settings are reread for every reminder. Set `enabled: false` to disable forwarding.
With `respect_dnd: true`, forwarding is skipped while Omarchy Do Not Disturb is
enabled. Set it to `false` if the phone should receive reminders in that mode too.
The phone still applies its own notification and Do Not Disturb settings.

To check your setup, run `omatask add 'Phone reminder check in 1m'` while the
reminder service is running. The task title, short ID and deadline are sent as a
KDE Connect message, without complete or snooze buttons. If KDE Connect already
mirrors Omatask desktop notifications automatically, disable that mirroring for
Omatask to avoid duplicates.

Forwarding runs after the desktop notification and targets only the configured,
paired, reachable phone. If the phone is offline, the CLI is missing or the command
fails, the reason is logged in the shell; the desktop notification is not retried.
There is no separate queue or retry for phone delivery, including messages skipped
because of Do Not Disturb. A successful CLI call does not confirm receipt on the
phone. Invalid configuration disables phone forwarding.

## Data model and storage

See [the architecture document](ARCHITECTURE.md) for details.

```text
omatask/
  domain.py         shared Task model and validation
  timeutil.py       IANA/UTC handling and date parsing
  recurrence.py     pure calendar functions
  daily_window.py   reminder distribution in local time
  persistence.py    SQLite, migrations and backups
  engine.py         transactional use cases
  reminders.py      scheduling, snooze and delivery worker
  notifications.py  notifications, sound, volume settings and DND
  parser.py         independent input grammar
  cli.py / ui.py    command-line and curses adapters
  transfer.py       JSON import/export and Markdown
  integrations.py   consistent JSON snapshots for panels
integrations/       Quickshell, Waybar, systemd, Hyprland, desktop entry
scripts/            offline/desktop installers, panel launcher, live smoke checks
tests/              unit, integration, CLI and concurrency tests
```

Schema v4 contains `tasks` with task/recurrence/tags/project/subtasks fields;
`occurrences` with due/completed/reopened timestamps and checklist snapshots;
`reminder_rules` with absolute/relative/clock kinds; and `deliveries` with
pending/sent/cancelled states. It uses cascading foreign keys, CHECK constraints,
a partial UNIQUE index for the current completion of an occurrence, and deadline
indexes. SQLite runs with WAL, a busy timeout and BEGIN IMMEDIATE transactions.
Migrations use `PRAGMA user_version` and are atomic. Older code refuses to open
newer schemas. The optional desktop installer backs up the default database;
for plugin-manager updates, another database or a CLI-only install, run
`omatask --db PATH backup COPY`. Do not manually copy a live .db without its WAL.

Each Task stores its current occurrence. Completion atomically writes history,
cancels pending reminders for the old occurrence, calculates the next deadline
and schedules relative/clock reminders. Count includes the first deadline.
Reopening revokes the counted completion but keeps the event in audit history.
The final occurrence of a recurring task can be reopened and completed again.
Once a series has advanced to its next occurrence, its schedule is immutable:
create a new series and cancel the old one to change it.

Monthly recurrence keeps the original day and clamps to the last day of shorter
months: Jan 31 → Feb 28/29 → Mar 31. Days/weeks/months preserve local wall time;
minutes/hours use elapsed UTC time. A DST gap shifts the time forward; an ambiguous
time during a DST fold uses its first occurrence. After downtime, overdue
occurrences are handled in sequence without being silently skipped.
Absolute reminders fire once per task; relative reminders apply to each occurrence.
Clock reminders use local times on the daily task's current due date. Slots before
the task's creation time are not queued; already queued reminders survive downtime.

JSON from schema v3 or v4 restores all tables and delivery states. Import validates
data in a temporary database before an atomic merge. Duplicate IDs cause an error
without a partial import. Use a new database for a complete restore. Markdown is
a readable report, not a restore format. Transferred pending reminders may be in
the past and will be delivered when the worker starts.

## Testing and limitations

Run `python3 -m unittest discover -s tests -v` from the project root. The suite
uses temporary databases and mocked notification backends, includes TUI checks
in a PTY and installation in an isolated HOME, and sends no real notifications.
See [testing and release preparation](TESTING.md) for coverage, optional live
desktop checks, Qt 6 QML validation and the publication checklist.

Source tests use synthetic data and belong in the repository. Personal validation
reports, desktop screenshots, logs, task databases, exports and backups are local
artifacts. `.gitignore` excludes the designated paths; it does not remove files
already tracked or erase Git history. Inspect the staged content before publishing.

- The native popup covers common daily actions. Editing descriptions, deadlines,
  recurrence and checklists is available in the full TUI/CLI. The Quickshell API
  was validated against the installed alpha; future alpha compatibility is not
  guaranteed.
- Notification delivery is at least once: a crash after sending over D-Bus but
  before the SQLite commit can cause a duplicate. A successful send does not prove
  the notification was read. Notifications have no snooze/complete actions; use
  the TUI/CLI or widget.
- The worker polls every ten seconds and sends up to twenty messages per cycle.
  All missed pending reminders are delivered without an expiry limit; a long
  downtime can produce several notifications. On a backend error, the service
  retries on the next ten-second cycle.
- A write transaction remains open during delivery, with timeouts of five seconds
  for notify-send, two seconds per DND query and three seconds for sound. Optional
  phone forwarding adds up to two three-second KDE Connect calls and another DND
  query. This serializes delivery with cancellation and concurrent workers;
  slow backends can delay other writes or exceed SQLite's ten-second busy timeout.
- Recurrence supports a subset of RFC 5545 and uses the Gregorian calendar;
  leap seconds are not supported. OS time zone changes do not change a series'
  stored time zone.
- Projects and tags are strings; checklists have one level. Cancel applies to
  the entire series; there is no separate skip-occurrence action. Statistics
  provide counts without analytical charts.
- There is no synchronization, database encryption, full-text index or arbitrary
  sorting. In-memory filtering is intended for personal task volumes.
- The TUI rereads data on keyboard actions; external changes appear after the next
  keypress. Local snapshot setup keeps backups for rollback.

Possible improvements: a graphical editor for all fields, notification actions,
skipping/rescheduling individual occurrences, editing the future part of a series,
grouped summaries of missed reminders, FTS5 search, more efficient UI refreshes
and additional parser locales.

## Disabling the integration

```bash
omarchy plugin disable local.omatask
```

This stops the widget and its reminder service. The database and queued reminders
remain saved. Re-enabling the plugin resumes delivery, including overdue reminders.
An independently installed terminal-only systemd worker must be stopped separately.

## Removing the integration

For the standard plugin-manager installation:

```bash
omarchy plugin remove local.omatask
```

If you ran the optional desktop setup, remove its launchers and shortcuts first,
from the installed checkout:

```bash
python3 ~/.config/omarchy/plugins/local.omatask/scripts/uninstall-desktop.py --remove-plugin
```

The cleanup removes only unchanged managed launchers and the marked shortcut
block, then asks Omarchy to remove the plugin. Modified launchers are retained.
Omit `--remove-plugin` to keep the widget and remove only optional desktop setup.
Task data, configuration and backups are retained. To remove an old standalone
CLI installation, use the [terminal reference](CLI.md#removing-a-standalone-install).
