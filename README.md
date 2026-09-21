# Omatask

An offline task widget with local reminders for the Omarchy bar.

See today's tasks and overdue counts, add tasks in one line, and complete or
snooze them in the popup. Supports recurring tasks, daily reminder windows,
search, priorities, tags and projects.

No account, cloud sync or telemetry. Tasks stay in a local SQLite database;
the bundled widget and reminder backend do not upload them to third-party servers.
Optional phone forwarding is off by default; enabling it sends reminder text to
your selected device through KDE Connect. See [privacy and data](docs/GUIDE.md#privacy-and-data).

## Install

Requires Omarchy 4.0.0.alpha / Quattro, Python 3.11+, sqlite3, tzdata and libnotify.
Sound uses `pw-play` or `paplay`.

Install from GitHub:

```bash
omarchy plugin add https://github.com/dwimerit/omatask.git --enable
```

The widget includes its Python backend and runs reminders in the existing Omarchy
shell. No pip, sudo or separate systemd service is needed. Task data stays outside
the plugin folder. Update with `omarchy plugin update local.omatask`.

For a local, unpublished checkout, or to add optional global shortcuts and
launchers, run from the checkout:

```bash
python3 scripts/install-desktop.py
```

Setup backs up configuration and the default database, checks shortcut conflicts,
and preserves installed Git checkouts. Use `--without-keys` to leave shortcuts
alone. See [installation and upgrades](docs/GUIDE.md#installation).

## Use the widget

| Action | Control |
|---|---|
| Open task list | Left click |
| Quick entry | Right click |
| Create a task | Type in the top input and press **Enter** |
| Search | **/** in an empty input; **Esc** clears the search |
| Select a task | Click a row or use **Up/Down** |
| Complete / reopen / snooze | **d** / **r** / **s** in the list |
| Delete | Row's **Delete** button, then confirm |
| Examples and help | **F1** or **?** in the header |

Optional desktop setup adds **Super+Alt+T/N** for the list and quick entry.

Type these directly into the widget:

```text
Buy milk tomorrow 18:00
Call Alex friday 14:00 remind 30m
Drink water daily 8x 08:00-22:00
```

A deadline automatically gets a reminder at that time. `remind 30m` moves it
thirty minutes earlier. Complete a recurring task to schedule its next occurrence.
For a daily window, complete the task once after meeting the day's goal.

## Configure and remove

The widget follows the Omarchy theme. Sound is enabled by default; volume, mute,
and optional phone forwarding are described in the
[widget guide](docs/GUIDE.md#reminders-and-sound).

Disable the widget and its reminder service, or remove the plugin:

```bash
omarchy plugin disable local.omatask
# Or uninstall:
omarchy plugin remove local.omatask
```

Your tasks remain saved. See [removal instructions](docs/GUIDE.md#removing-the-integration)
if you also installed optional shortcuts and launchers.

## More

- [Widget guide](docs/GUIDE.md): input syntax, controls, sound, phone reminders and data.
- [Testing](docs/TESTING.md), [architecture](docs/ARCHITECTURE.md) and [release notes](docs/RELEASE_NOTES.md).
- [Plugin packaging](docs/PLUGIN.md): release checks and marketplace submission.
- [Terminal reference](docs/CLI.md): advanced editing, CLI/TUI, exports and backups.

MIT licensed. See [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md).
