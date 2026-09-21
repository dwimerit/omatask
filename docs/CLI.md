# Terminal reference

[Back to Omatask](../README.md)

The widget covers everyday task management. The CLI and terminal editor provide
advanced editing, scripts, exports and backups. Run installation commands from
the repository root.

To install only the CLI/TUI, without changing desktop settings:

```bash
./scripts/install.sh
~/.local/bin/omatask --help
```

## CLI reference

Global options go **before the command**: `--db PATH`, `--timezone Europe/Moscow`,
`--json`. Each task stores its time zone; later OS time zone changes do not shift
its schedule. `--timezone` affects new tasks, date input and calendar views.

```bash
omatask add 'Buy milk'
omatask add 'Call client friday 14:00 remind 30m #work'
omatask add 'Gym monday 09:00 every mon,wed,fri +Work'
omatask add 'English today 19:00 daily count 30'
omatask add 'Water today 10:00 every 2h'
omatask add 'Drink water daily 8x 08:00-22:00'
omatask add 'Pay rent 2026-10-31 09:00 monthly'
omatask add 'Report' --due 'tomorrow 18:00' --priority high --tag work --project Work
omatask add 'Practice daily' --literal
omatask add 'Training' --due 'monday 09:00' --repeat week --interval 2 --weekdays mon,wed,fri --count 20
omatask add 'Habit' --due '2026-10-01 09:00' --repeat day --until '2026-10-31 23:59'
omatask edit ID --title 'New title' --description 'Notes' --priority urgent
omatask edit ID --due 'tomorrow 12:00' --tag backend --tag work --project 'Side Project'
omatask edit ID --clear-tags
omatask edit ID --repeat none
omatask list
omatask list today
omatask list overdue --priority urgent
omatask list all --status active --project Work --tag backend --due 2026-09-22 --recurring
omatask search deploy
omatask show ID
omatask done ID
omatask cancel ID
omatask reopen ID
omatask delete ID
omatask remind ID 30m
omatask remind ID --at 'tomorrow 10:00'
omatask snooze ID evening
omatask snooze ID tomorrow
omatask subtask ID add 'Run tests'
omatask subtask ID done SUBTASK_ID
omatask subtask ID reopen SUBTASK_ID
omatask subtask ID delete SUBTASK_ID
omatask stats
omatask export tasks.json
omatask export tasks.md --format markdown
omatask export > tasks.json
omatask import tasks.json
omatask backup tasks-backup.db
omatask worker --once
omatask ui all
omatask quick
omatask bar
```

IDs may be shortened to a unique prefix. `list` without a view includes all statuses;
date-based views default to active tasks. An empty result is a successful response.
Priority affects sorting only: urgent, high, normal, low, then deadline.
CLI deletion immediately removes the task, history and reminders. The TUI asks
for `yes`; the native widget shows a Cancel / Delete confirmation dialog.

To show JSON details, use `omatask --json show ID`. The result includes the current
deadline, next_occurrence (after the current one), completed_count (counted
completions), execution_count (all completion events), remaining_count (including
the current occurrence), final_due (the last scheduled deadline), history,
reminders and deliveries. For an unbounded series, remaining_count and final_due
are null. A cancelled series retains its bounds for reference but has no active
next_occurrence or notifications.

Exit codes: 0 success; 1 OS/SQLite/notification backend error; 2 invalid input,
an import conflict or an unsupported schema; 3 task not found; 130 Ctrl+C.
Errors go to stderr; `--json` produces JSON-only stdout. `export` writes its export
format; `bar` always writes JSON. Export and backup commands refuse to overwrite
an existing destination file. Files created by `export PATH` and `backup PATH`
are readable and writable only by their owner (mode 0600). Shell redirection
such as `export > tasks.json` uses your shell's permissions; use `umask 077`
before redirecting private data.

## TUI keyboard reference

| Key | Action |
|---|---|
| j/k, Down/Up | Select a task |
| a | Add a task in one line |
| d / c / r | Complete / cancel / reopen |
| x | Delete after typing `yes` |
| e | Choose a field: title, description, due, recurrence (JSON) |
| / | Search titles and descriptions |
| f | View and filters, such as `all tag=work project="Side Project"` |
| s / n | Snooze / add a reminder (`30m` or `at ...`) |
| p | Cycle priority |
| m / t | Project / tags |
| b | View checklist, then add/done/reopen/delete |
| Enter | Details and history; j/k scroll |
| q / Esc | Close the list or details |
| Esc / Ctrl+U in an input | Cancel input / clear the field |

Input supports Unicode, Backspace and Enter. There is no full multiline editor;
use the CLI for long descriptions. Quick entry accepts one line and closes on
Enter after successful creation; invalid input is preserved for correction.

## Waybar adapter

[integrations/waybar.jsonc](../integrations/waybar.jsonc) provides a separate custom
module. Merge it into your configuration and add `custom/omatask` to
`modules-right`. The core has no Waybar dependency.

## Standalone reminder service

The widget already has a reminder service. Use the following only if you want
reminders independently of the widget after a terminal-only installation:

```bash
mkdir -p ~/.config/systemd/user
cp integrations/systemd/omatask-reminders.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now omatask-reminders.service
```

After installing new standalone code, restart the service. For a custom prefix,
adjust ExecStart; for a custom database, add `--db /absolute/path` before `worker`.
Avoid running the standalone service alongside the plugin service. Stop it with
`systemctl --user disable --now omatask-reminders.service` before switching to the
plugin. Queue state survives restarts. Diagnostics use the service's journal.

## Removing a standalone install

Stop and disable its reminder service first. Remove only the files installed by
`install.sh`: `~/.local/bin/omatask`, `~/.local/bin/omatask-panel`, the
`~/.local/share/applications/omatask.desktop` entry, and the optional user service
unit; then run `systemctl --user daemon-reload`. Adjust paths for a custom prefix.
The versioned `~/.local/share/omatask/release.*` code directories and `current`
symlink can be removed after stopping the worker. Keep the parent directory and
its `tasks.db`/SQLite sidecars to preserve your task data. Configuration and backups
remain separate. Do not remove launchers you have replaced with your own scripts.
