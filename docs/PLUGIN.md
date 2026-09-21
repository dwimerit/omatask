# Plugin packaging and release

Omatask follows the [Omarchy development contract](https://plugins.omarchy.org/develop.html).
The root `manifest.json` declares a `bar-widget` and a `service` under the stable
ID `local.omatask`. Both entry points are relative paths inside
`integrations/omarchy/`. The repository includes the Python backend, generated
notification chime, installation/removal instructions, MIT license and
third-party notices. No installer hook or external Python package is needed.

## Runtime and updates

`Widget.qml` inherits the Omarchy panel lifecycle and uses the bundled
`scripts/omatask-backend`. `Service.qml` is loaded once per enabled plugin and
polls the same database every ten seconds. Each cycle starts current Python code;
disabling/removing/reloading the plugin destroys its service and stops the worker.
The worker is not detached. Both components use the widget's database/executable
settings from the Omarchy bar configuration. The data directory is outside the
checkout, so plugin removal does not erase tasks.

Git-managed installations update with `omarchy plugin update local.omatask`.
Optional desktop setup runs in place when invoked from the installed checkout;
it refuses to replace another Git checkout. Local source installs use a filtered
snapshot. Existing tasks, configuration and the previous plugin are backed up.
The old unmodified systemd unit is retired during this optional migration.

## Local release checks

Run from the project root:

```bash
omarchy plugin validate .
python3 -m unittest discover -s tests -v
OMATASK_QML_TESTS=1 python3 -m unittest discover -s tests -p test_plugin_runtime.py -v
python3 scripts/prepare-release.py
```

The last command builds `.local/release/omatask-0.4.0.tar.gz` without network access
or Git changes. It uses an explicit source-file list, includes tests and licenses,
excludes local reports/data, and refuses to overwrite an existing archive. Use
`--output PATH` for a different destination. Validate an extracted archive as well
as the working tree. Qt 6 QML checks and live desktop scenarios are described in
[TESTING.md](TESTING.md).

The offscreen service test uses a fake backend in an isolated HOME to exercise
load, unload, reload and paths containing spaces. It does not send notifications
or change the running desktop. An actual desktop check should additionally cover
appearance, pointer/keyboard interaction, shell open/close, disable/re-enable,
shell restart and removal on the target Omarchy version.

## Marketplace listing

The [publishing guide](https://plugins.omarchy.org/publish.html) requires a public
GitHub repository and a root manifest, README, license, and safe installation and
removal. A preview is optional. The repository is public; a marketplace listing
is a separate submission.

Before an owner-authorized marketplace listing: review the files/history,
check installation from its GitHub URL,
and submit the marketplace issue form with the repository, Productivity category
and task/reminder tags. Confirm the permanent plugin ID before the first listing.
If adding a preview, use invented tasks and inspect the entire image.
