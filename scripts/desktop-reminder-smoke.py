#!/usr/bin/env python3
"""Opt-in real plugin reminder test: a deadline alone must create a toast.

Creates one uniquely tagged task due in one minute; removes only that task.
Observes the notification popup and the audio stream without changing volume/DND.
"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import time
import uuid

CLI = str(Path.home() / '.local/bin/omatask')
TAG = 'omatask-reminder-smoke-' + uuid.uuid4().hex[:8]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--delay', type=int, default=60, help='Seconds until the test reminder (default 60)')
parser.add_argument('--title', default='Omatask: проверка напоминания')
args = parser.parse_args()
assert 1 <= args.delay <= 300
TITLE = args.title


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE).strip()


def cli(*args):
    return json.loads(run(CLI, '--json', *args))


assert json.loads(run('omarchy-shell', 'local.omatask-reminders', 'status'))['ready']
assert run('omarchy-shell', 'notifications', 'dndState') == 'off', 'DND enabled; leave it unchanged'
popup_dir = Path.home() / '.local/state/omarchy/notifications'
started = time.time() * 1000
popup_seen = False
audio = None
sent = False
monitors = json.loads(run('hyprctl', 'monitors', '-j'))
monitor = next(m for m in monitors if m['focused'])
try:
    if args.delay == 60:
        task = cli('add', TITLE + ' in 1m #' + TAG)
    else:
        due = (datetime.now().astimezone() + timedelta(seconds=args.delay)).isoformat()
        task = cli('add', TITLE, '--literal', '--due', due, '--tag', TAG)
    info = cli('show', task['id'])
    assert len(info['reminders']) == 1 and info['reminders'][0]['value'] == '0', info
    print('SCHEDULED deadline-only reminder for ' + task['due_at'], flush=True)
    deadline = time.monotonic() + args.delay + 20
    next_db_check = 0
    while time.monotonic() < deadline:
        if not popup_seen:
            for path in popup_dir.glob('*.json'):
                try:
                    row = json.loads(path.read_text())
                except (OSError, ValueError):
                    continue
                if row.get('summary') == TITLE and row.get('timestamp', 0) >= started:
                    popup_seen = True
                    if monitor['scale'] == 1 and monitor['transform'] == 0:
                        # Current Omarchy theme: 380 logical units at 4/3 spacing.
                        # Capture only the top-right toast region, not the desktop.
                        time.sleep(0.2)
                        run('grim', '-g', f"{monitor['x']+monitor['width']-520},{monitor['y']+37} 515x220",
                            '/tmp/omatask-reminder-toast.png')
                    print('PASS notification entered the visible popup stack', flush=True)
                    break
        if audio is None:
            streams = json.loads(run('pw-dump'))
            for stream in streams:
                info = stream.get('info', {})
                props = info.get('props', {})
                if 'Node' in stream.get('type', '') and props.get('media.role') == 'Notification' and info.get('state') == 'running':
                    levels = next((p for p in info.get('params', {}).get('Props', []) if 'channelVolumes' in p), {})
                    if levels:
                        audio = {k: levels.get(k) for k in ('volume', 'mute', 'channelVolumes', 'channelMap')}
                        assert not audio['mute'] and max(audio['channelVolumes']) > 0, audio
                        print('PASS live notification audio stream: ' + json.dumps(audio), flush=True)
        if time.monotonic() >= next_db_check:
            sent = any(d['state'] == 'sent' for d in cli('show', task['id'])['deliveries'])
            next_db_check = time.monotonic() + 0.5
        if sent and popup_seen:
            break
        time.sleep(0.1)
    assert sent and popup_seen, {'sent':sent, 'popup_seen':popup_seen}
    print('PASS deadline-only task delivered by the plugin worker', flush=True)
    if audio is None:
        print('Audio stream not observed; check the shell log and confirm playback by listening', flush=True)
finally:
    for task in cli('list', 'all', '--tag', TAG):
        cli('delete', task['id'])
