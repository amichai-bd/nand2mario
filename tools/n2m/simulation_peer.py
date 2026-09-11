"""One declared simulation peer, owned and reaped by the builder."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .records import atomic_text


class Peer:
    def __init__(self, root, attempt, script):
        self.root, self.attempt, self.script = root, attempt, script
        self.process = None
        self.stream = None
        self.record = {}

    def start(self):
        self.stream = (self.attempt / 'peer.log').open('w', encoding='utf-8')
        argv = [sys.executable, str(self.root / self.script),
                '--root', str(self.root), '--attempt', str(self.attempt)]
        self.record = {'argv': argv, 'cwd': str(self.attempt)}
        try:
            self.process = subprocess.Popen(argv, cwd=self.attempt,
                stdout=self.stream, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            deadline = time.monotonic() + 5
            ready = self.attempt / 'peer-ready.json'
            while not ready.exists():
                if self.process.poll() is not None:
                    raise RuntimeError('simulation peer exited before readiness')
                if time.monotonic() >= deadline:
                    raise RuntimeError('simulation peer readiness timeout')
                time.sleep(.01)
            data = json.loads(ready.read_text(encoding='utf-8'))
            if data.get('host') != '127.0.0.1' or type(data.get('port')) is not int or not 1 <= data['port'] <= 65535:
                raise RuntimeError('invalid simulation peer listener')
            self.record['listener'] = data
            return data['port']
        except Exception:
            self.close(False)
            raise

    def close(self, success):
        try:
            if self.process is not None:
                if success:
                    try:
                        code = self.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        raise RuntimeError('simulation peer did not complete')
                    if code:
                        raise RuntimeError(f'simulation peer failed with exit {code}')
                self.record['completed_normally'] = success
        finally:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)
            if self.process is not None:
                self.record['exit_code'] = self.process.returncode
            if self.stream is not None:
                self.stream.close()
            atomic_text(self.attempt / 'peer-result.json', json.dumps(self.record, indent=2) + '\n')
