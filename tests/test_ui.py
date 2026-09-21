"""Real curses smoke test in a PTY, isolated from the user's terminal/database."""
import fcntl
import json
import os
import pty
import select
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path
from omatask.persistence import Store


class TUISmokeTests(unittest.TestCase):
    def test_quick_unicode_then_list_and_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'tasks.db'
            master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,130,0,0))
            env=dict(os.environ,TERM='xterm-256color',LANG='C.UTF-8')
            process=subprocess.Popen([sys.executable,'-m','omatask','--db',str(path),'quick'],stdin=slave,stdout=slave,stderr=slave,env=env)
            os.close(slave)
            def wait_for(needle):
                buffer=b''; deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if select.select([master],[],[],0.1)[0]:
                        try:buffer+=os.read(master,65536)
                        except OSError:break
                    if needle in buffer:return
                self.fail(f'Missing {needle!r} in terminal output {buffer!r}')
            try:
                wait_for(b'New task:')
                os.write(master,'Купить молоко tomorrow 18:00 #home !high\n'.encode())
                self.assertEqual(process.wait(timeout=5),0)
            finally:
                if process.poll() is None:process.kill();process.wait()
                os.close(master)
            store=Store(path)
            try:
                task=store.all()[0]
                self.assertEqual(task.title,'Купить молоко')
                self.assertEqual(task.tags,['home'])
            finally:store.close()
            master,slave=pty.openpty()
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,130,0,0))
            process=subprocess.Popen([sys.executable,'-m','omatask','--db',str(path),'ui','all'],stdin=slave,stdout=slave,stderr=slave,env=env)
            os.close(slave)
            try:
                wait_for(b'OMATASK')
                os.write(master,b'd')
                wait_for(b'completed')
                os.write(master,b'q')
                self.assertEqual(process.wait(timeout=5),0)
            finally:
                if process.poll() is None:process.kill();process.wait()
                os.close(master)
            store=Store(path)
            try:self.assertEqual(store.all()[0].status,'completed')
            finally:store.close()

if __name__=='__main__':unittest.main()
