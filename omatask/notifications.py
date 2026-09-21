"""Desktop notifications with optional sound and OmaConnect phone delivery."""
import html
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess

log = logging.getLogger(__name__)
DEFAULT_SOUND = Path(__file__).with_name('assets') / 'notification.wav'


def backend_error(exc):
    """Describe a backend failure without leaking arguments, output or paths."""
    if isinstance(exc, subprocess.TimeoutExpired):
        return 'command timed out'
    if isinstance(exc, subprocess.CalledProcessError):
        return f'command exited with status {exc.returncode}'
    if isinstance(exc, OSError):
        return f'OS error {exc.errno}' if exc.errno is not None else 'OS error'
    return type(exc).__name__


def sound_settings():
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'omatask/config.json'
    try:
        data = json.loads(config.read_text()) if config.exists() else {}
        enabled = data.get('notification_sound', True)
        volume = data.get('notification_sound_volume', 0.6)
        filename = data.get('notification_sound_file', str(DEFAULT_SOUND))
        if type(enabled) is not bool or type(volume) not in (int, float) or not 0 <= volume <= 1 or not isinstance(filename, str):
            raise ValueError('Invalid notification sound settings')
        return enabled, volume, Path(filename).expanduser()
    except (OSError, ValueError, AttributeError) as exc:
        log.warning('Cannot read sound settings: %s; using defaults', exc)
        return True, 0.6, DEFAULT_SOUND


def do_not_disturb():
    # Read the actual Omarchy state when available; never modify desktop DND.
    if shutil.which('omarchy-shell'):
        try:
            result = subprocess.run(['omarchy-shell', 'notifications', 'dndState'],
                                    capture_output=True, text=True, timeout=2)
            if result.returncode == 0 and result.stdout.strip() in ('on', 'off'):
                return result.stdout.strip() == 'on'
        except (OSError, subprocess.SubprocessError):
            pass
    state = Path.home() / '.local/state/omarchy/notifications.json'
    try:
        return json.loads(state.read_text()).get('dnd') is True
    except (OSError, ValueError, AttributeError):
        return False


def play_sound():
    """A broken/missing audio backend must not retry an already delivered toast."""
    enabled, volume, filename = sound_settings()
    if not enabled or volume == 0 or do_not_disturb():
        return False
    if not filename.is_file():
        log.warning('Notification sound file is missing: %s', filename)
        return False
    player = shutil.which('pw-play')
    if player:
        command = [player, '--media-role=Notification', '--volume=' + str(volume), '--', str(filename)]
    else:
        player = shutil.which('paplay')
        if not player:
            log.warning('No sound player found (pw-play or paplay)')
            return False
        command = [player, '--property=media.role=event', '--volume=' + str(round(volume * 65536)), '--', str(filename)]
    try:
        subprocess.run(command, check=True, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning('Notification sound could not be played: %s', backend_error(exc))
        return False


def phone_settings():
    """Fail closed: malformed config must never enable remote delivery."""
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'omatask/config.json'
    try:
        data = json.loads(config.read_text()) if config.exists() else {}
        settings = data.get('omaconnect', {})
        enabled = settings.get('enabled', False)
        device = settings.get('device_id', '')
        respect_dnd = settings.get('respect_dnd', True)
        if (type(enabled) is not bool or type(respect_dnd) is not bool
                or not isinstance(device, str) or '\x00' in device
                or (enabled and not device.strip())):
            raise ValueError('Expected enabled/respect_dnd booleans and a device_id')
        return enabled, device.strip(), respect_dnd
    except (OSError, ValueError, AttributeError) as exc:
        log.warning('Cannot read OmaConnect settings: %s; phone delivery disabled', exc)
        return False, '', True


def phone_notify(task):
    """Best effort via the KDE Connect backend used by OmaConnect.

    Never retry a desktop toast because the phone is offline. A successful CLI
    call means the ping was submitted, not that the user received or read it.
    """
    enabled, device, respect_dnd = phone_settings()
    if not enabled or (respect_dnd and do_not_disturb()):
        return False
    client = shutil.which('kdeconnect-cli')
    if not client:
        log.warning('OmaConnect delivery skipped: kdeconnect-cli is not installed')
        return False
    try:
        available = subprocess.run([client, '--list-available', '--id-only'],
                                   check=True, capture_output=True, text=True, timeout=3)
        if device not in available.stdout.splitlines():
            log.warning('OmaConnect delivery skipped: configured device is not paired and reachable')
            return False
        message = (f'Omatask: {task.title}\n'
                   f"Task {task.id[:8]} · due {task.due_at or 'unscheduled'}")
        subprocess.run([client, '--device=' + device, '--ping-msg=' + message],
                       check=True, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        return True
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        log.warning('OmaConnect phone notification failed: %s', backend_error(exc))
        return False


def desktop_notify(task):
    # Sound is supplied once by this adapter: prevent a sound-capable notification
    # server from adding a second signal. Current Omarchy doesn't play sound hints.
    try:
        subprocess.run(['notify-send', '--app-name=Omatask', '--expire-time=10000',
                        '--hint=boolean:suppress-sound:true', '--', task.title,
                        html.escape(f"Task {task.id[:8]} · due {task.due_at or 'unscheduled'}\n"
                                    f'Snooze: omatask snooze {task.id[:8]} 10m')],
                       check=True, timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    except (OSError, subprocess.SubprocessError) as exc:
        # The CLI prints this error to stderr (the service journal). Subprocess
        # exceptions otherwise include the full command, including task text.
        raise OSError('Desktop notification failed: ' + backend_error(exc)) from None
    play_sound()
    phone_notify(task)
