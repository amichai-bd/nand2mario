"""Entrypoint artifact and record checks. No serial port or board is opened."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m.host.client import Client  # noqa: E402
import state_support as support  # noqa: E402
from state_fake import Endpoint  # noqa: E402
import springtrail_player as entrypoint  # noqa: E402


class EntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.binding = support.binding()

    def test_observe_writes_state_provenance_and_a_labelled_image(self):
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        client.load(self.image)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'observe'
            result = entrypoint.run(client, self.image, self.binding, out,
                                    mode='observe', snapshot=True)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['binding']['rom_sha256'], support.ROM_SHA256)
            self.assertEqual(result['provenance']['boundary'], 'vblank-complete')
            record = json.loads((out / 'observation-0000.json').read_text())
            self.assertTrue(record['image']['reconstructed'])
            self.assertEqual(record['image']['represents'], 'logical')
            self.assertEqual(record['observation']['mode_name'], 'TITLE')
            self.assertTrue((out / 'observation-0000.png').is_file())
            # An actual PPU frame is kept separately and labelled for what it is.
            self.assertEqual(result['snapshot']['represents'], 'previous-boundary')
            self.assertTrue((out / 'snapshot.2bpp').is_file())

    def test_play_retains_every_observation_and_images_at_its_stride(self):
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'play'
            result = entrypoint.run(client, self.image, self.binding, out, mode='play',
                                    image_stride=5,
                                    budget={'wall_seconds': 60, 'frames': 20, 'actions': 20})
            # A bounded budget stops the run; the failure is recorded, not hidden.
            self.assertEqual(result['status'], 'FAIL')
            self.assertIn('BUDGET', result['reason'])
            self.assertEqual(result['image_stride'], 5)
            self.assertEqual(result['observations_retained'], len(result['actions']) + 1)
            actions = json.loads((out / 'actions.json').read_text())
            self.assertEqual(actions, result['actions'])
            images = sorted(out.glob('observation-*.png'))
            states = sorted(out.glob('observation-*.json'))
            self.assertEqual(len(states), result['observations_retained'])
            self.assertEqual(len(images), (result['observations_retained'] + 4) // 5)
            self.assertTrue(result['released'])


if __name__ == '__main__':
    unittest.main()
