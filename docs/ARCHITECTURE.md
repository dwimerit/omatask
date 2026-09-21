# Architecture

## Desktop compatibility

The native widget targets Omarchy `4.0.0.alpha` and its Quickshell/Lua APIs.
The reference branch is [quattro](https://github.com/omacom/omarchy/tree/quattro),
with its [shell plugin documentation](https://github.com/omacom/omarchy/blob/quattro/manual/32-shell-plugins.md).

The shell uses Quickshell, plugin manifests have `schemaVersion=1`, and user
plugins live in `~/.config/omarchy/plugins/<id>`. Hyprland shortcuts use Lua
`o.bind`. `omarchy launch tui` starts a terminal through uwsm/xdg-terminal-exec.
The built-in reminder command and ReminderFlow provide a quick-entry reference,
but their transient systemd timers are not persistent task storage. The clock
plugin provides a widget example. Omatask keeps these components intact and sends
freedesktop notifications through notify-send. Quickshell is the primary adapter;
Waybar is an optional adapter for older installations. The alpha API may change.
The core does not change desktop configuration; the desktop installer is explicit.

## Technology and boundaries

Python 3.11 or newer, using only the standard library: fast startup, sqlite3,
zoneinfo/IANA time zones, curses for the TUI, argparse for the CLI and unittest.
OS runtime dependencies are Python and tzdata, with libnotify for notifications
and curses/a terminal for the TUI. No server or third-party Python packages are
required. The TUI uses the terminal theme, Unicode and keyboard-driven lists
and prompts.

Source layout: `omatask/{domain,timeutil,recurrence,daily_window,persistence,engine,
reminders,notifications,parser,cli,ui,integrations,transfer}.py`, `tests/`,
`integrations/{omarchy,systemd}/`, `docs/` and `scripts/`. Domain and recurrence
logic have no SQL or UI dependencies. The engine coordinates transactions;
reminders accept an injected notifier and clock; the UI calls the engine.

## Network and data boundaries

The bundled Python backend has no network client, remote endpoint, telemetry or
cloud synchronization. Parsing, scheduling, SQLite operations, imports, exports
and backups run locally. The QML widget invokes the backend through process
argument arrays and reads JSON stdout; its help and resources are bundled, with
no remote content or network requests.

Runtime external commands are confined to `notify-send` (task title, short ID,
deadline and snooze hint), `omarchy-shell` (local IPC), `hyprctl` (monitor lookup in
the optional panel launcher), `pw-play`/`paplay` (a sound file), `omarchy launch tui`
(optional terminal UI), and the opt-in phone adapter.
That adapter invokes `kdeconnect-cli` only after valid configuration explicitly
enables it. Its phone message sends the title, short ID and deadline outside the
computer, without the database or task description.

Local processing does not isolate data from the user's desktop notification
service, notification mirroring tools, synced storage, or a custom backend chosen
in widget settings. See [privacy and data](GUIDE.md#privacy-and-data) for the user
contract and [privacy regression checks](TESTING.md#automated-checks) for its scope.

## Schema and lifecycle

Schema v1:

```text
tasks(id UUID, title, description, status, priority, created_at, due_at,
      completed_at, timezone, recurrence JSON, anchor_at, occurrence_index)
occurrences(id UUID, task_id FK, sequence, due_at, completed_at)
reminder_rules(id, task_id FK, kind absolute/relative, value)
deliveries(id, rule_id FK nullable, task_id FK, sequence, fire_at, state,
           delivered_at)
```

A task remains one entity; its `due_at` refers to the current occurrence.
Cancelling closes the series; reopening makes it active again. In the final
implementation, reopening revokes the counted completion of the current occurrence
and retains its history event with `reopened_at`. This also works for the last
occurrence of a finite series. Snoozing creates a new persistent delivery while
preserving the original history.

Schema v2 adds `tasks.tags` as a JSON array, `project` as a string, and `subtasks`
as a JSON array with id/title/done fields.

Schema v3 adds `occurrences.reopened_at` and checklist snapshots. A partial
`UNIQUE(task_id, sequence) WHERE reopened_at IS NULL` index preserves the audit
history of repeated completions. Completing an occurrence records its checklist
snapshot; the next occurrence starts with unchecked subtasks.

Schema v4 adds the `clock` reminder kind with `value=HH:MM`. Rebuilding
reminder_rules and deliveries preserves IDs, states and cascading foreign keys.
Import accepts JSON schemas v3 and v4; older code cannot open the newer database.

SQLite uses WAL, foreign_keys, CHECK/UNIQUE constraints, busy_timeout and
BEGIN IMMEDIATE. Sequential migrations use `PRAGMA user_version` and are atomic;
unknown newer database versions are rejected. Online backups use SQLite's backup
API. JSON export includes every table. Import merges unique IDs without
replacing existing records; a conflict rolls back the entire import. Markdown
is a readable report; restoration uses JSON or a SQLite backup.

For daily windows, the parser turns `daily 8x 08:00-22:00`, or the longer
`daily goal 8 between 08:00-22:00`, into daily recurrence, a deadline at the end
of the window, and eight clock rules. Reminders use the local date of the current
deadline; the shared wall-time resolver handles time zones and DST. Slots before
`created_at` are not queued, so a new task does not immediately send reminders
for the morning that has already passed. Existing deliveries survive downtime.
Completing the task schedules the following day; individual glasses are not
counted and days are not completed automatically. Edit/cancel/reopen preserve
these rules.

## Recurrence

```text
Rule {
  frequency: minute/hour/day/week/month,
  interval: >=1,
  count?: >=1,
  until?: time-zone-aware ISO instant,
  weekdays?: [0..6]
}
```

Count includes the first occurrence. `anchor_at` and the task's IANA time zone
preserve the intended schedule. Monthly recurrence uses the original anchor day,
clamped to the last day of a shorter month: Jan 31 → Feb 28 → Mar 31.
Days/weeks/months use the local calendar; minutes/hours use elapsed UTC time.
Weeks start on Monday, and weekday rules apply within every Nth week. The first
deadline must match the weekday rule or validation fails.

A DST gap shifts the time forward by the transition size; an ambiguous time in
a DST fold uses the first occurrence. The next deadline is calculated from the
anchor and sequence, not the completion time, so the schedule does not drift.
After downtime, overdue occurrences are not silently completed or skipped:
the user completes them in order. The series ends according to count or until.
Completed occurrences remain in history. The remaining count is exact; an
unbounded series has no final date. Until limits scheduled deadlines, not the
actual time of completion.

## Reminders

Without explicit rules, a task with a deadline gets a relative rule with an
offset of zero: an automatic reminder at the deadline. An explicit reminder
replaces that rule while preserving sent deliveries. Moving the deadline
recreates the automatic reminder; removing the deadline removes its unsent
deliveries. The rule applies to every occurrence of a recurring task.
Before delivery, the worker restores this rule for older active tasks that have
neither rules nor deliveries for their current occurrence. This runs within a
transaction and does not duplicate snoozes or previously sent notifications.

A relative rule subtracts an elapsed duration from the deadline; an absolute
rule fires once. Multiple rules create multiple deliveries. Completing an
occurrence cancels all its pending deliveries and schedules relative and clock
rules for the next occurrence. A singleton Omarchy plugin service polls a persistent queue
and delivers missed pending reminders after downtime, with a batch-size limit.
Pending reminders do not expire. Cancellation and deletion leave no orphaned
records.

Transaction locking serializes workers with task mutations; notify-send has a
timeout. Success means the D-Bus server accepted the message, not that a person
read it. A crash between the D-Bus send and database commit can repeat a
notification: delivery is at least once, not exactly once. Moving the clock
forward delivers overdue reminders; moving it backward does not resend sent
reminders. A task's IANA time zone is fixed; OS time zone changes affect views
and new tasks only. Snooze accepts 10m/30m/1h/evening/tomorrow; calendar values
use the task's time zone.

The notifications adapter calls notify-send with suppress-sound, then plays one
chime through pw-play, falling back to paplay. Volume, sound file and mute
settings come from config.json. Omarchy DND is read through IPC with a fallback
to its saved state. A sound error does not roll back delivery already accepted
by the notification server. No third-party Python packages are needed. The
bundled signal is a stereo PCM WAV with identical channels; its standard-library
generator reproduces the file without external dependencies.

Optional OmaConnect forwarding uses `kdeconnect-cli` to send a text ping to one
configured paired, reachable device after desktop delivery. It is disabled by
default and respects desktop DND unless configured otherwise. Phone failures do
not retry desktop delivery; there is no offline phone queue. Backend error
messages omit command arguments so task text and device IDs are not written to
the service journal by subprocess exception formatting.

## API and interaction

```text
omatask [--db PATH] [--timezone IANA] [--json] COMMAND

add | edit | delete | done | cancel | reopen | list | show | search |
remind | snooze | subtask | stats | export | import | backup | worker |
ui | quick | bar | widget
```

Views: today, tomorrow, upcoming, overdue, completed, recurring and all.
Filters cover status/priority/project/tag/due/recurring, with title and description
search. JSON stdout supports scripts; errors go to stderr. Exit codes are 2 for
validation errors, 3 for missing tasks and 1 for system errors. The name `omatask`
avoids a conflict with Taskwarrior's `task` command.

TUI shortcuts: a add; d complete; c cancel; r reopen; x delete with confirmation;
e edit; / search; f view; s snooze; p priority; m project; Enter details; q quit.
Additional fields are available through the edit form and CLI. Quick entry accepts
one line followed by Enter. The parser is independent and uses a predictable
English grammar rather than ambiguous natural-language interpretation.

## Implementation stages, checks and tradeoffs

1. MVP: domain/time/recurrence, schema v1, engine, reminders, CLI and curses.
   Calendar, DST, completion, count, snooze, recovery, database and CLI checks.
2. Schema v2, tags/projects/checklists/parser, adapters, exports and statistics.
   Parser, atomic import/full restore, filters and subprocess CLI checks.
3. Integration smoke checks and installation documentation.

All timestamps use time-zone-aware ISO values. Comparisons and SQL storage use
canonical UTC; calendar scheduling uses IANA time zones. Limitations include the
Gregorian calendar, a subset of recurrence rules, no synchronization and no
interactive action buttons in system notifications. The TUI keeps startup fast
and dependencies small; Quickshell acts as a thin adapter.

## Testing and limitations

See [the README](../README.md) and [testing guide](TESTING.md) for the implemented
API, reproducible checks and limitations. Completed tasks, including the last
occurrence of a finite series, can be reopened with history preserved by schema v3.

## Native widget, introduced in v0.2

`Widget.qml` uses the standard `qs.Ui.Panel`, `WidgetButton`, `KeyboardPanel`,
`TextField` and `qs.Commons` components for theming, focus, popup coordination
and multiple monitors. `omatask widget` returns a consistent list and counter
snapshot from a read transaction. Process calls the CLI with argument arrays;
there are no synchronous requests from the render loop. Mutations refresh all
instances of the widget. An outdated search response is ignored if the user has
changed the view or query. Commands are serialized. Backend errors preserve
input, with loading and error states visible in the UI. All user strings use
Text.PlainText.

Identical polling responses do not recreate list rows. Selection has a visible
border; clicking a row gives keyboard focus to the list handler. Deletion uses
a ConfirmDialog with Cancel selected by default and a saved task ID, so a list
refresh cannot redirect confirmation to another task.

CreationHelp provides local help without network access; F1 also works from the
input field. Opening help preserves the draft, and examples are inserted without
executing commands. The English text and twelve examples live in
CreationHelpData.js; all examples have been checked through the parser and engine,
and the CLI flags have been checked against argparse. In an empty task input,
`/` switches to search. Esc clears the search filter and returns to the list;
the footer displays the corresponding shortcut.

The native popup supports quick entry/search, views, complete/cancel/reopen/delete,
title/priority/project/tag edits, snooze and read-only details. The full TUI is
available through o or a middle click. Shell bar routing sends keyboard launches
to the focused monitor. Each output has a unique diagnostic IPC target.

The root manifest loads the widget and a singleton service. Both run the bundled
Python backend from the checkout; the service starts one `worker --once` per poll
and is destroyed with the plugin. Task data stays outside the checkout. Optional
desktop setup backs up configuration and the default database, preserves existing
Git checkouts, and adds only a managed Lua shortcut block and recorded launchers.
Git-managed updates use the plugin manager; take a database backup explicitly
before a schema upgrade. Local snapshot updates can restart the alpha shell to
clear cached QML. Omarchy source files are not modified.
