"""DirectShow camera process boundaries; no physical camera is opened."""
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from n2m.windows_camera import DirectShowCamera, PNG_SIGNATURE, read_png


def chunk(kind, data=b''):
    return len(data).to_bytes(4,'big')+kind+data+b'\0\0\0\0'


PNG = PNG_SIGNATURE+chunk(b'IHDR',b'0'*13)+chunk(b'IDAT',b'x')+chunk(b'IEND')


class Process:
    def __init__(self, data=b'', running=True):
        self.stdout = BytesIO(data)
        self.running = running
        self.terminated = self.killed = False

    def poll(self):
        return None if self.running else 1

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True
        self.running = False


class CameraTests(unittest.TestCase):
    def camera(self, listing='"Chosen camera" (video)', **options):
        calls = []
        def run(command, **kwargs):
            calls.append(('run',command,kwargs))
            return SimpleNamespace(stderr=listing)
        camera = DirectShowCamera('Chosen camera','ffmpeg-test',run=run,**options)
        return camera,calls

    def test_png_parser_reads_one_frame_without_consuming_the_next(self):
        stream=BytesIO(PNG+PNG)
        self.assertEqual(read_png(stream),PNG)
        self.assertEqual(read_png(stream),PNG)
        with self.assertRaises(EOFError):read_png(stream)
        for broken in (b'not png!',PNG_SIGNATURE+chunk(b'IDAT')):
            with self.assertRaises(ValueError):read_png(BytesIO(broken))

    def test_exact_device_is_required_and_missing_or_duplicate_is_refused(self):
        for invalid in ('','bad\nname','bad\0name'):
            with self.assertRaises(ValueError):DirectShowCamera(invalid,'ffmpeg-test')
        for listing,message in (
                ('"Other" (video)','camera device not found'),
                ('"Chosen camera" (video)\n"Chosen camera" (video)','camera device name is ambiguous')):
            camera,_=self.camera(listing)
            with self.assertRaisesRegex(ValueError,message):camera.validate()

    def test_capture_command_is_no_audio_and_cleanup_terminates(self):
        process=Process(PNG)
        camera,calls=self.camera(popen=lambda command,**kwargs:(
            calls.append(('popen',command,kwargs)) or process))
        camera.validate();camera.start()
        meta,image=camera.read()
        self.assertEqual((meta,image),({'kind':'camera','seq':1},PNG))
        command=[row for kind,*row in calls if kind=='popen'][0][0]
        self.assertIn('-an',command)
        self.assertNotIn('audio=Chosen camera',' '.join(command))
        self.assertIn('video=Chosen camera',command)
        self.assertIs(subprocess.DEVNULL,[row for kind,*row in calls if kind=='popen'][0][1]['stderr'])
        camera.close()
        self.assertTrue(process.terminated)
        self.assertIsNone(camera.process)

    def test_malformed_exit_and_stall_are_truthful(self):
        malformed=Process(b'bad data')
        camera,_=self.camera(popen=lambda *_args,**_kwargs:malformed)
        camera.validate();camera.start()
        with self.assertRaisesRegex(ValueError,'camera stream is malformed'):camera.read()
        camera.close()

        camera,_=self.camera(frame_timeout=.01)
        camera.process=Process(b'',running=True)
        with self.assertRaisesRegex(TimeoutError,'camera frame stalled'):camera.read()
        camera.close()

        exited=Process(b'',running=False)
        camera,_=self.camera(frame_timeout=.01)
        camera.process=exited
        with self.assertRaisesRegex(RuntimeError,'camera process exited'):camera.read()
        camera.close()

    def test_private_selector_never_appears_in_failures(self):
        private='PRIVATE_CAMERA_SELECTOR'
        camera=DirectShowCamera(private,'ffmpeg-test',run=lambda *_a,**_k:SimpleNamespace(stderr=''))
        with self.assertRaises(ValueError) as caught:camera.validate()
        self.assertNotIn(private,str(caught.exception))


if __name__=='__main__':unittest.main()
