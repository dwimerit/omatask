#!/usr/bin/env python3
"""Opt-in live mouse/keyboard deletion regression; only deletes its own task."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
CLI = str(Path.home() / '.local/bin/omatask')
PANEL = str(Path.home() / '.local/bin/omatask-panel')
TAG = 'omatask-delete-smoke-' + uuid.uuid4().hex[:8]


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def cli(*args):
    return json.loads(run(CLI, '--json', *args))


monitors = json.loads(run('hyprctl', 'monitors', '-j'))
monitor = next(m for m in monitors if m['focused'])
target = 'local.omatask-' + monitor['name']


def status():
    return json.loads(run('omarchy-shell', target, 'status'))


def wait(predicate, label, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.15)
    raise AssertionError('Timeout: ' + label + '; status=' + str(status()))


def input_keys(*args):
    assert status()['opened'], 'Panel closed; refusing to type into another app'
    run('wtype', *args)


def key(name):
    input_keys('-k', name)


def capture(name):
    r = status()['rect']
    geometry = f"{monitor['x']+r['x']},{monitor['y']+r['y']} {r['width']}x{r['height']}"
    run('grim', '-g', geometry, '/tmp/' + name)


def click_row(helper, task_id, delete=False):
    assert status()['opened'] and not status()['busy']
    row = wait(lambda: json.loads(run('omarchy-shell', target, 'rowRect', task_id)), 'visible test row')
    r = status()['rect']
    x = row['deleteX'] if delete else row['x'] + 50
    y = row['deleteY'] if delete else row['y'] + row['height'] / 2
    assert r['x'] <= x <= r['x'] + r['width'] and r['y'] <= y <= r['y'] + r['height'], (row, r)
    # This helper maps absolute positions to the desktop layout. Require the
    # simple layout it has been verified with, rather than clicking speculatively.
    assert min(m['x'] for m in monitors) == 0 and min(m['y'] for m in monitors) == 0
    assert all(m['scale'] == 1 and m['transform'] == 0 for m in monitors)
    width = max(m['x'] + m['width'] for m in monitors)
    height = max(m['y'] + m['height'] for m in monitors)
    run(str(helper), str(round(monitor['x'] + x)), str(round(monitor['y'] + y)), str(width), str(height))


before_ids = {t['id'] for t in cli('list', 'all')}
try:
    with tempfile.TemporaryDirectory(prefix='omatask-pointer-') as tmp:
        build = Path(tmp)
        protocol = str(ROOT / 'tests/desktop/virtual-pointer.xml')
        run('wayland-scanner', 'client-header', protocol, str(build / 'virtual-pointer.h'))
        run('wayland-scanner', 'private-code', protocol, str(build / 'virtual-pointer.c'))
        helper = build / 'click'
        run('cc', '-Wall', '-Wextra', '-I' + str(build), str(ROOT / 'tests/desktop/pointer-click.c'),
            str(build / 'virtual-pointer.c'), '-lwayland-client', '-o', str(helper))
        task = cli('add', 'Проверка удаления ' + TAG, '--literal', '--tag', TAG)
        run(PANEL, 'open')
        wait(lambda: status()['inputFocused'], 'input focus')
        key('Down')
        input_keys('--', '/')
        input_keys('-M', 'ctrl', 'a', '-m', 'ctrl')
        input_keys('--', TAG)
        key('Return')
        wait(lambda: status()['query'] == TAG, 'test search')
        # Always change view at least once to test an initially unselected row.
        while True:
            old_view = status()['view']
            input_keys('--', 'f')
            wait(lambda: status()['view'] != old_view, 'view change')
            if status()['view'] == 'all':
                break
        wait(lambda: status()['rows'] == 1 and not status()['selectedId'], 'unselected All row')
        click_row(helper, task['id'])
        wait(lambda: status()['selectedId'] == task['id'] and status()['listFocused'], 'mouse selection and focus')
        capture('omatask-selection.png')
        time.sleep(3.2)  # An automatic refresh must retain the selection/focus.
        assert status()['selectedId'] == task['id'] and status()['listFocused']
        print('PASS real pointer selection / focus / selection survives refresh', flush=True)

        key('Delete')
        wait(lambda: status()['deleteConfirm'] and status()['deleteTargetId'] == task['id'], 'Delete key confirmation')
        capture('omatask-delete-confirm.png')
        key('Escape')
        wait(lambda: not status()['deleteConfirm'], 'Escape cancels')
        assert cli('show', task['id'])['id'] == task['id']
        click_row(helper, task['id'], delete=True)
        wait(lambda: status()['deleteConfirm'], 'visible Delete button')
        key('Return')
        wait(lambda: not status()['deleteConfirm'], 'Cancel is the default button')
        assert cli('show', task['id'])['id'] == task['id']
        input_keys('--', 'x')
        wait(lambda: status()['deleteConfirm'], 'x opens confirmation')
        key('Escape')
        input_keys('--', 'ч')
        wait(lambda: status()['deleteConfirm'] and status()['deleteTargetId'] == task['id'], 'Russian key confirmation')
        key('Right')
        key('Return')
        wait(lambda: not cli('list', 'all', '--tag', TAG), 'confirmed deletion persisted')
        assert before_ids <= {t['id'] for t in cli('list', 'all')}, 'A pre-existing task disappeared'
        print('PASS Delete button / Delete, x, ч keys / Escape and default Cancel / confirmed removal / pre-existing tasks retained', flush=True)
finally:
    for task in cli('list', 'all', '--tag', TAG):
        cli('delete', task['id'])
    if status()['opened']:
        if status()['deleteConfirm']:
            key('Escape')
        if status()['query'] == TAG:
            if status()['inputFocused']:
                key('Down')
            input_keys('--', '/')
            input_keys('-M', 'ctrl', 'a', '-m', 'ctrl', '-k', 'BackSpace')
            key('Return')
            wait(lambda: not status()['query'], 'clear test search')
        run(PANEL, 'close')
    for m in monitors:
        run('omarchy-shell', 'local.omatask-' + m['name'], 'refresh')
