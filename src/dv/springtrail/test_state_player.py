"""Entrypoint artifact, alignment and comparison checks.

No serial port or board is opened. Timing figures produced here measure a fake
endpoint in this process; they are not board latency and are never presented
as such.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m import generated_interfaces as abi  # noqa: E402
from n2m import springtrail_play as play_module  # noqa: E402
from n2m import springtrail_state as state  # noqa: E402
from n2m.host.client import Client  # noqa: E402
import state_support as support  # noqa: E402
from state_fake import Endpoint  # noqa: E402
import springtrail_player as entrypoint  # noqa: E402

BUDGET = {'wall_seconds': 240, 'frames': 1500, 'actions': 1500}


class EntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.binding = support.binding()

    def test_observe_takes_the_actual_frame_that_matches_the_observation(self):
        """`--snapshot` must return an aligned pair, not a frame one behind."""
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
            self.assertEqual(result['snapshot']['represents'], 'this observation')
            # Taken one frame later, which is where that frame completes.
            self.assertEqual(result['snapshot']['taken_at_dot'] - result['provenance']['dot'],
                             play_module.PERIOD)
            self.assertTrue(result['comparison']['match'])
            self.assertEqual(result['comparison']['differing'], 0)
            self.assertEqual(result['comparison']['shades'], 160 * 144)
            record = json.loads((out / 'observation-0000.json').read_text())
            self.assertTrue(record['image']['reconstructed'])
            self.assertEqual(record['image']['represents'], 'logical')
            for name in ('observation-0000.png', 'snapshot.2bpp', 'snapshot.png'):
                self.assertTrue((out / name).is_file(), name)

    def test_observe_reports_every_timing_figure_it_measured(self):
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        client.load(self.image)
        with tempfile.TemporaryDirectory() as folder:
            result = entrypoint.run(client, self.image, self.binding,
                                    Path(folder) / 'observe', mode='observe')
            timings = result['image']['timings']
            for name in ('boundary_seconds', 'read_seconds', 'decode_seconds',
                         'state_seconds', 'render_seconds', 'image_seconds'):
                self.assertIn(name, timings)
                self.assertGreaterEqual(timings[name], 0.0)
            self.assertGreaterEqual(timings['image_seconds'], timings['render_seconds'])
            # Both paths report what they cost in bytes and requests.
            self.assertEqual(result['frame_path']['bytes'], abi.FRAME_BYTES)
            self.assertEqual(result['binding']['bytes'], self.binding.bytes)
            self.assertLess(result['binding']['requests'], result['frame_path']['requests'])

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

    def test_compare_reaches_every_checkpoint_and_agrees_at_each(self):
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'compare'
            result = entrypoint.run(client, self.image, self.binding, out, mode='compare',
                                    images=False, budget=BUDGET)
            self.assertEqual(result['status'], 'PASS', result.get('reason'))
            self.assertEqual(result['final']['mode'], 'WON')
            self.assertEqual(result['checkpoints_missing'], [])
            names = [row['checkpoint'] for row in result['comparisons']]
            self.assertEqual(sorted(names), sorted(play_module.Checkpoints.NAMES))
            for row in result['comparisons']:
                with self.subTest(row['checkpoint']):
                    self.assertTrue(row['match'], row['first_difference'])
                    self.assertEqual(row['differing'], 0)
                    self.assertEqual(row['shades'], 160 * 144)
                    # The frame is taken one boundary after the state it shows.
                    self.assertEqual(row['snapshot_dot'] - row['dot'], play_module.PERIOD)
                    self.assertEqual(row['frame_path']['bytes'], abi.FRAME_BYTES)
                    self.assertLess(row['state_path']['bytes'], row['frame_path']['bytes'])
                    self.assertLess(row['state_path']['requests'],
                                    row['frame_path']['requests'])
            measurements = json.loads((out / 'measurements.json').read_text())
            for name in ('boundary_seconds', 'loop_seconds', 'snapshot_seconds',
                         'render_seconds', 'compare_seconds', 'state_read_seconds',
                         'state_decode_seconds'):
                self.assertIn(name, measurements, name)
                self.assertGreaterEqual(measurements[name]['samples'], 1)
                self.assertLessEqual(measurements[name]['min'], measurements[name]['median'])
                self.assertLessEqual(measurements[name]['median'], measurements[name]['max'])
            self.assertIn('not a contract', measurements['note'])

    def test_a_disagreement_at_a_checkpoint_fails_the_comparison(self):
        """A wrong actual frame must be reported, never tuned away."""
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        original = endpoint.game.pixels
        endpoint.game.pixels = lambda: bytes(23040)
        with tempfile.TemporaryDirectory() as folder:
            result = entrypoint.run(client, self.image, self.binding, Path(folder) / 'compare',
                                    mode='compare', images=False,
                                    budget=dict(BUDGET, frames=60, actions=60))
        endpoint.game.pixels = original
        self.assertEqual(result['status'], 'FAIL')
        self.assertTrue(result['comparisons'])
        first = result['comparisons'][0]
        self.assertFalse(first['match'])
        self.assertGreater(first['differing'], 0)
        self.assertIsNotNone(first['first_difference'])

    def test_bind_package_accepts_an_immutable_attempt(self):
        """The slower path: an attempt on disk, its ROM and its own symbols."""
        image, binding = state.bind_package(ROOT, support.package())
        self.assertEqual(binding.rom_sha256, support.ROM_SHA256)
        self.assertEqual(binding.ranges, self.binding.ranges)
        self.assertEqual(image, self.image)
        self.assertIsNotNone(binding.identity()['package'])


if __name__ == '__main__':
    unittest.main()
