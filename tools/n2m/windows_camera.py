"""Bounded, no-audio Windows DirectShow camera frames for the live viewer."""
import os
import queue
import re
import shutil
import subprocess
import threading


PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
MAX_PNG_CHUNK = 32 * 1024 * 1024


def _read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.read(size-len(data))
        if not part:
            raise EOFError
        data.extend(part)
    return bytes(data)


def read_png(stream):
    """Read one complete PNG from a concatenated image2pipe stream."""
    signature = _read_exact(stream,len(PNG_SIGNATURE))
    if signature != PNG_SIGNATURE:
        raise ValueError('camera stream is malformed')
    image = bytearray(signature)
    first = True
    while True:
        header = _read_exact(stream,8)
        length = int.from_bytes(header[:4],'big')
        kind = header[4:]
        if length > MAX_PNG_CHUNK or first and kind != b'IHDR':
            raise ValueError('camera stream is malformed')
        first = False
        image.extend(header)
        image.extend(_read_exact(stream,length+4))  # Chunk data and CRC.
        if kind == b'IEND':
            return bytes(image)


class DirectShowCamera:
    """One exact Windows camera, with private selection and deterministic cleanup."""
    def __init__(self, device, executable=None, *, run=subprocess.run,
                 popen=subprocess.Popen, frame_timeout=5):
        if not device or any(char in device for char in '\r\n\0'):
            raise ValueError('exact camera device required')
        self.device = device
        self.executable = executable or shutil.which('ffmpeg')
        if not self.executable:
            raise FileNotFoundError(2,'camera capture tool not found')
        self.run, self.popen = run, popen
        self.frame_timeout = frame_timeout
        self.process = self.thread = None
        self.frames = queue.Queue(maxsize=2)
        self.error = None
        self.sequence = 0
        self.validated = False

    @staticmethod
    def _flags():
        return getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name == 'nt' else 0

    def validate(self):
        """Refuse missing and duplicate friendly names without retaining the list."""
        try:
            found = self.run(
                [self.executable,'-hide_banner','-list_devices','true','-f','dshow','-i','dummy'],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,
                text=True,errors='replace',timeout=10,check=False,
                creationflags=self._flags())
        except subprocess.TimeoutExpired as error:
            raise TimeoutError('camera device discovery stalled') from error
        names = re.findall(r'"([^"]+)"\s+\(video\)',found.stderr or '')
        matches = sum(name == self.device for name in names)
        if matches == 0:
            raise ValueError('camera device not found')
        if matches != 1:
            raise ValueError('camera device name is ambiguous')
        self.validated = True

    def start(self):
        if not self.validated:
            raise RuntimeError('camera device was not validated')
        if self.process is not None:
            raise RuntimeError('camera process already started')
        command = [
            self.executable,'-nostdin','-hide_banner','-loglevel','error',
            '-f','dshow','-rtbufsize','256M','-i','video='+self.device,
            '-an','-vf','fps=5','-c:v','png','-f','image2pipe','pipe:1',
        ]
        self.process = self.popen(
            command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,bufsize=0,creationflags=self._flags())
        if self.process.stdout is None:
            raise RuntimeError('camera process has no image stream')
        self.thread = threading.Thread(target=self._reader,daemon=True)
        self.thread.start()

    def _offer(self, item):
        try:
            self.frames.put_nowait(item)
        except queue.Full:
            try:
                self.frames.get_nowait()
            except queue.Empty:
                pass
            self.frames.put_nowait(item)

    def _reader(self):
        try:
            while True:
                image = read_png(self.process.stdout)
                self.sequence += 1
                self._offer((self.sequence,image))
        except EOFError:
            self.error = RuntimeError('camera process exited')
        except Exception:
            self.error = ValueError('camera stream is malformed')
        finally:
            self._offer(None)

    def read(self):
        if self.process is None:
            raise RuntimeError('camera process not started')
        try:
            item = self.frames.get(timeout=self.frame_timeout)
        except queue.Empty as error:
            if self.process.poll() is not None:
                raise RuntimeError('camera process exited') from error
            raise TimeoutError('camera frame stalled') from error
        if item is None:
            raise self.error or RuntimeError('camera process exited')
        sequence,image = item
        return {'kind':'camera','seq':sequence},image

    def close(self):
        process, thread = self.process, self.thread
        if process is None:
            return
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        finally:
            if process.stdout is not None:
                process.stdout.close()
            alive = False
            if thread is not None:
                thread.join(timeout=2)
                alive = thread.is_alive()
            self.process = self.thread = None
            if alive:
                raise RuntimeError('camera reader did not stop')
