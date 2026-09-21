import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import wave
from array import array
from unittest.mock import patch
from omatask import notifications as n


class NotificationTests(unittest.TestCase):
    def test_desktop_backend_error_does_not_expose_task(self):
        task = SimpleNamespace(title='Private appointment', id='private-id', due_at=None)
        for timeout in (False, True):
            def fail(command, **kwargs):
                if timeout:
                    raise subprocess.TimeoutExpired(command, 5, stderr='private backend output')
                raise subprocess.CalledProcessError(1, command, stderr='private backend output')
            with self.subTest(timeout=timeout), patch.object(n.subprocess, 'run', side_effect=fail), patch.object(n, 'play_sound') as sound, patch.object(n, 'phone_notify') as phone:
                with self.assertRaises(OSError) as error:
                    n.desktop_notify(task)
                self.assertIn('Desktop notification failed', str(error.exception))
                for private in (task.title, task.id, 'private backend output'):
                    self.assertNotIn(private, str(error.exception))
                sound.assert_not_called()
                phone.assert_not_called()

    def test_default_sound_has_identical_audible_left_and_right_channels(self):
        with wave.open(str(n.DEFAULT_SOUND), 'rb') as sound:
            self.assertEqual(sound.getnchannels(), 2)
            self.assertEqual(sound.getsampwidth(), 2)
            self.assertLess(sound.getnframes() / sound.getframerate(), 3)
            pcm = array('h', sound.readframes(sound.getnframes()))
        self.assertEqual(pcm[0::2], pcm[1::2])
        self.assertGreater(max(abs(s) for s in pcm), 1000)

    def test_sound_after_toast_without_double_sound(self):
        task=SimpleNamespace(title='Reminder',id='12345678',due_at=None)
        with patch.object(n.subprocess,'run') as run, patch.object(n,'play_sound') as sound, patch.object(n,'phone_notify') as phone:
            n.desktop_notify(task)
            sound.assert_called_once_with()
            phone.assert_called_once_with(task)
            self.assertIn('--hint=boolean:suppress-sound:true',run.call_args.args[0])
        with patch.object(n.subprocess,'run',side_effect=OSError('D-Bus gone')), patch.object(n,'play_sound') as sound, patch.object(n,'phone_notify') as phone:
            with self.assertRaises(OSError):n.desktop_notify(task)
            sound.assert_not_called()
            phone.assert_not_called()

    def test_sound_settings_and_mute(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'XDG_CONFIG_HOME':tmp}):
            folder=Path(tmp)/'omatask';folder.mkdir()
            config=folder/'config.json'
            config.write_text(json.dumps({'notification_sound':False}))
            with patch.object(n.subprocess,'run') as run:
                self.assertFalse(n.play_sound());run.assert_not_called()
            config.write_text(json.dumps({'notification_sound_volume':0.25,'notification_sound_file':'/tmp/custom.wav'}))
            self.assertEqual(n.sound_settings(),(True,0.25,Path('/tmp/custom.wav')))
            config.write_text('{invalid')
            with self.assertLogs(n.log,level='WARNING'):
                self.assertEqual(n.sound_settings(),(True,0.6,n.DEFAULT_SOUND))

    def test_pipewire_arguments_and_failed_audio_is_nonfatal(self):
        with tempfile.NamedTemporaryFile(suffix='.wav') as sound:
            with patch.object(n,'sound_settings',return_value=(True,0.6,Path(sound.name))), patch.object(n,'do_not_disturb',return_value=False), patch.object(n.shutil,'which',return_value='/usr/bin/pw-play'), patch.object(n.subprocess,'run') as run:
                self.assertTrue(n.play_sound())
                self.assertEqual(run.call_args.args[0],['/usr/bin/pw-play','--media-role=Notification','--volume=0.6','--',sound.name])
                run.side_effect=subprocess.TimeoutExpired('pw-play',3)
                with self.assertLogs(n.log,level='WARNING'):
                    self.assertFalse(n.play_sound())

    def test_dnd_suppresses_playback(self):
        with patch.object(n,'sound_settings',return_value=(True,0.6,n.DEFAULT_SOUND)), patch.object(n,'do_not_disturb',return_value=True), patch.object(n.subprocess,'run') as run:
            self.assertFalse(n.play_sound());run.assert_not_called()
        with patch.object(n.shutil,'which',return_value='/usr/bin/omarchy-shell'), patch.object(n.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='on\n')):
            self.assertTrue(n.do_not_disturb())
