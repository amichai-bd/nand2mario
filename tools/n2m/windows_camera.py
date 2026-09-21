"""Bounded, no-audio Windows DirectShow MJPEG frames for the live viewer.

This capture drives `ffmpeg -f dshow`, and DirectShow is a Windows API, so the
viewer's `--camera-source windows-directshow` is the only value there is: the
gate is the capture interface itself, not a policy about hosts.
"""
import os
import queue
import re
import shutil
import subprocess
import threading


JPEG_SIGNATURE = b'\xff\xd8'
MJPEG_BOUNDARY = b'--n2m-source-frame'
MAX_JPEG_FRAME = 32 * 1024 * 1024
MAX_HEADER_LINE = 1024


def _read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        part = stream.read(size-len(data))
        if not part:
            raise EOFError
        data.extend(part)
    return bytes(data)


def _header_line(stream):
    line = stream.readline(MAX_HEADER_LINE+1)
    if not line:
        raise EOFError
    if len(line) > MAX_HEADER_LINE or not line.endswith(b'\r\n'):
        raise ValueError('camera stream is malformed')
    return line[:-2]


def read_mjpeg_frame(stream):
    """Read one length-delimited JPEG part from FFmpeg's MJPEG muxer."""
    if _header_line(stream) != MJPEG_BOUNDARY:
        raise ValueError('camera stream is malformed')
    headers = {}
    while True:
        line = _header_line(stream)
        if not line:
            break
        if b':' not in line:
            raise ValueError('camera stream is malformed')
        name,value = line.split(b':',1)
        name = name.strip().lower()
        if not name or name in headers:
            raise ValueError('camera stream is malformed')
        headers[name] = value.strip().lower()
    raw_length = headers.get(b'content-length',b'')
    if headers.get(b'content-type') != b'image/jpeg' or not raw_length.isdigit():
        raise ValueError('camera stream is malformed')
    length = int(raw_length)
    if not 4 <= length <= MAX_JPEG_FRAME:
        raise ValueError('camera stream is malformed')
    try:
        image = _read_exact(stream,length)
        trailer = _read_exact(stream,2)
    except EOFError as error:
        raise ValueError('camera stream is malformed') from error
    if (not image.startswith(JPEG_SIGNATURE) or not image.endswith(b'\xff\xd9')
            or trailer != b'\r\n'):
        raise ValueError('camera stream is malformed')
    return image


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
        # One retained frame makes a slow consumer see the newest complete
        # image instead of accumulating camera latency.
        self.frames = queue.Queue(maxsize=1)
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
            '-an','-vf',('scale=640:360:force_original_aspect_ratio=decrease,'
                         'pad=640:360:(ow-iw)/2:(oh-ih)/2,fps=10'),
            '-c:v','mjpeg','-q:v','7',
            '-f','mpjpeg','-boundary_tag','n2m-source-frame','pipe:1',
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
                image = read_mjpeg_frame(self.process.stdout)
                self.sequence += 1
                self._offer((self.sequence,image))
        except EOFError:
            self.error = RuntimeError('camera process exited')
        except Exception:
            self.error = ValueError('camera stream is malformed')
        finally:
            # Preserve an already completed latest frame. A reader that drains
            # it observes the stored error on its next call.
            if self.frames.empty():
                self._offer(None)

    def read(self):
        if self.process is None:
            raise RuntimeError('camera process not started')
        if self.error is not None and self.frames.empty():
            raise self.error
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
