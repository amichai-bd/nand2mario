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
            for name in ('observation-0000.png', 'snapshot-0000.2bpp', 'snapshot-0000.png'):
                self.assertTrue((out / name).is_file(), name)

    def test_observe_reports_every_timing_figure_it_measured(self):
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        client.load(self.image)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'observe'
            result = entrypoint.run(client, self.image, self.binding, out, mode='observe')
            timings = result['image']['timings']
            for name in ('boundary_seconds', 'read_seconds', 'decode_seconds',
                         'state_seconds', 'render_seconds', 'image_seconds'):
                self.assertIn(name, timings)
                self.assertGreaterEqual(timings[name], 0.0)
            self.assertGreaterEqual(timings['image_seconds'], timings['render_seconds'])
            self.assertGreaterEqual(timings['state_seconds'], timings['boundary_seconds'])
            # observe summarises like every other mode, so repeats need no
            # aggregation by hand.
            measurements = json.loads((out / 'measurements.json').read_text())
            self.assertEqual(measurements, result['measurements'])
            for name in ('boundary_seconds', 'read_seconds', 'decode_seconds',
                         'state_seconds', 'render_seconds', 'image_seconds'):
                self.assertEqual(measurements[name]['samples'], 1, name)
            # Both paths report what they cost in bytes and requests.
            self.assertEqual(result['frame_path']['bytes'], abi.FRAME_BYTES)
            self.assertEqual(result['binding']['bytes'], self.binding.bytes)
            self.assertLess(result['binding']['requests'], result['frame_path']['requests'])

    def test_observe_repeats_give_one_summary_with_the_snapshot_fetch_timed(self):
        """The sample-count step of the board plan, proved end to end here."""
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        client.load(self.image)
        repeat = 6
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'observe'
            result = entrypoint.run(client, self.image, self.binding, out, mode='observe',
                                    snapshot=True, repeat=repeat, images=False)
            self.assertEqual(result['status'], 'PASS')
            self.assertEqual(result['repeat'], repeat)
            self.assertEqual(len(result['comparisons']), repeat)
            self.assertTrue(all(row['match'] for row in result['comparisons']))
            measurements = json.loads((out / 'measurements.json').read_text())
            for name in ('boundary_seconds', 'read_seconds', 'decode_seconds',
                         'state_seconds', 'render_seconds', 'image_seconds',
                         'snapshot_seconds', 'compare_seconds'):
                self.assertIn(name, measurements, name)
                self.assertEqual(measurements[name]['samples'], repeat, name)
                self.assertLessEqual(measurements[name]['min'], measurements[name]['median'])
                self.assertLessEqual(measurements[name]['median'], measurements[name]['max'])
            # The actual-pixel fetch is timed, not left at zero.
            self.assertGreater(measurements['snapshot_seconds']['median'], 0.0)
            # Each repeat is its own boundary, one frame further on.
            self.assertEqual(len(sorted(out.glob('observation-*.json'))), repeat)
            self.assertEqual(len(sorted(out.glob('snapshot-*.2bpp'))), repeat)

    def test_boundary_acquisition_is_summarised_as_itself(self):
        """`boundary_seconds` is the acquisition, not the whole state read."""
        actions = [{'boundary_seconds': 1.0, 'read_seconds': 2.0, 'decode_seconds': 4.0,
                    'state_seconds': 7.0, 'loop_seconds': 9.0, 'decide_seconds': 0.5}]
        images = [{'timings': {'render_seconds': 3.0, 'image_seconds': 10.0}}]
        measurements = entrypoint.summarize(actions=actions, images=images)
        self.assertEqual(measurements['boundary_seconds']['median'], 1.0)
        self.assertEqual(measurements['read_seconds']['median'], 2.0)
        self.assertEqual(measurements['decode_seconds']['median'], 4.0)
        self.assertEqual(measurements['state_seconds']['median'], 7.0)
        self.assertEqual(measurements['render_seconds']['median'], 3.0)
        self.assertEqual(measurements['image_seconds']['median'], 10.0)
        self.assertEqual(measurements['loop_seconds']['median'], 9.0)
        self.assertNotIn('snapshot_seconds', measurements)

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
            # Every figure the SPEC lists, each named for what it measures.
            for name in ('boundary_seconds', 'read_seconds', 'decode_seconds',
                         'state_seconds', 'render_seconds', 'image_seconds',
                         'loop_seconds', 'snapshot_seconds', 'compare_seconds'):
                self.assertIn(name, measurements, name)
                self.assertGreaterEqual(measurements[name]['samples'], 1)
                self.assertLessEqual(measurements[name]['min'], measurements[name]['median'])
                self.assertLessEqual(measurements[name]['median'], measurements[name]['max'])
            self.assertEqual(measurements['snapshot_seconds']['samples'],
                             len(result['comparisons']))
            self.assertEqual(measurements['image_seconds']['samples'],
                             result['observations_retained'])
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



class RehearsalEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.binding = support.binding()

    def test_delay_cli_defaults_and_rejects_invalid_modes_before_supervision(self):
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from unittest.mock import patch
        base = ['play', '--tag', 'delay', '--package', 'unused']
        with patch.object(entrypoint, 'supervise', return_value=(0, '')) as supervisor, redirect_stdout(io.StringIO()):
            self.assertEqual(entrypoint.main(base + ['--start-delay-frames', '37']), 0)
            self.assertIn('--start-delay-frames', supervisor.call_args.args[0])
        for options in (['--start-delay-frames', '-1'], ['--start-delay-frames', '1501']):
            with patch.object(entrypoint, 'supervise') as supervisor, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    entrypoint.main(base + options)
                supervisor.assert_not_called()
        with patch.object(entrypoint, 'worker', return_value=0) as worker:
            self.assertEqual(entrypoint.main(base + ['--worker']), 0)
            self.assertEqual(worker.call_args.args[0].start_delay_frames, 0)
        with patch.object(entrypoint, 'supervise') as supervisor, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                entrypoint.main(['observe', *base[1:], '--start-delay-frames', '37'])
            supervisor.assert_not_called()

    def test_observe_establishes_and_verifies_paused_neutral_origin_and_exit(self):
        endpoint = Endpoint(image=self.image)
        client = Client(endpoint)
        client.load(self.image)
        endpoint.state = abi.STATE_PAUSED ^ 1
        endpoint.mask = endpoint.game.mask = 3
        with tempfile.TemporaryDirectory() as folder:
            result = entrypoint.run(client, self.image, self.binding,
                                    Path(folder), mode='observe', images=False)
        self.assertEqual(result['status'], 'PASS', result.get('reason'))
        self.assertLess(endpoint.requests.index('HALT'), endpoint.requests.index('PEEK'))
        self.assertEqual(endpoint.mask, 0)
        self.assertEqual(endpoint.state, abi.STATE_PAUSED)
        self.assertTrue(result['cleanup']['verified'])
        self.assertFalse(result['uncertain'])

    def test_observe_cleanup_rejection_changes_success_to_fail(self):
        from n2m.interface_codec import decode_packet, encode_packet
        class RejectedExit(Endpoint):
            def write(self, packet):
                header, _ = decode_packet(packet)
                if header['command'] == abi.COMMAND_HALT and 'HALT' in self.requests:
                    self.requests.append('HALT')
                    self.pending.extend(encode_packet(header['seq'], header['command'], b'',
                        kind=abi.WIRE_RESPONSE, status=abi.STATUS_STEP_LIMIT))
                    return len(packet)
                return super().write(packet)
        endpoint = RejectedExit(image=self.image)
        client = Client(endpoint)
        client.load(self.image)
        with tempfile.TemporaryDirectory() as folder:
            result = entrypoint.run(client, self.image, self.binding,
                                    Path(folder), mode='observe', images=False)
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('rejected', result['release_error'])
        self.assertFalse(result['cleanup']['verified'])
        self.assertIn('observation', result)

if __name__ == '__main__':
    unittest.main()
