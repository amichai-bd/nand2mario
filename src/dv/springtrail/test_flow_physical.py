"""Synthetic host scheduling/failure checks, not physical frame evidence."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from n2m import generated_interfaces as abi
from interactions_reference import TITLE, PLAYING, PAUSED, WON
from flow_physical_reference import (PERIOD, VISIBLE, SUCCESS_FLOW, plan,
                                     schedule, predict, expected_snapshot)
from flow_physical_driver import run, DOT_HZ

LCD = 131072  # Synthetic test timing only; no production LCD constant claimed.


def render(game):
    return bytes([game.mode % 4])*23040


class Endpoint:
    def __init__(self, *, fault=False, stall=False, uncertain=False):
        self.sequence = 7
        self.dots, self.mask = 1000000, 0
        self.running = self.loaded = False
        self.events, self.calls = [], []
        self.uncertain = False
        self.fault, self.stall, self.lose = fault, stall, uncertain

    def identify(self):
        return dict(build_id='original')

    def load(self, rom):
        assert len(rom) == 32768
        self.loaded = True
        self.dots = 0
        return dict(verified_bytes=len(rom))

    def control(self, name, value=None):
        self.calls.append((name, value))
        if self.running:
            self.dots += 1000
        if name == 'RUN':
            self.running = True
        elif name == 'HALT':
            self.running = False
        else:
            assert name == 'INPUT'
            self.mask = value
            self.events.append((self.dots, value))
        return dict(dot=self.dots)

    def read_host(self, address):
        return {abi.HOST_REG_STATE: abi.STATE_RUNNING if self.running else abi.STATE_PAUSED,
                abi.HOST_REG_INPUT_SOURCE: abi.INPUT_SOURCE_UART,
                abi.HOST_REG_INPUT: self.mask, abi.HOST_REG_INPUT_EFFECTIVE: self.mask,
                abi.HOST_REG_IMAGE_VALID: 1, abi.HOST_REG_DOT_HI: self.dots >> 32,
                abi.HOST_REG_DOT_LO: self.dots & 0xffffffff}[address]

    def sleep(self, seconds):
        assert self.running
        self.dots += round(seconds*DOT_HZ)+(2*PERIOD if self.stall else 0)

    def snapshot(self):
        if not self.loaded:
            return dict(epoch=4, seq=7, dot=999000), bytes(5760)
        if self.lose:
            self.uncertain = True
            raise RuntimeError('lost reply')
        frame = (self.dots-LCD-65459)//PERIOD
        metadata = dict(epoch=6, seq=frame, dot=LCD+frame*PERIOD+65459, size=5760)
        pixels = render(predict(frame, self.events, LCD))
        packed = bytearray(sum(pixels[n+i] << (2*i) for i in range(4))
                           for n in range(0, 23040, 4))
        if self.fault:
            packed[0] ^= 1
        return metadata, bytes(packed)


class FlowPhysical(unittest.TestCase):
    def prior(self):
        return dict(sequence=7, build_id='original', halt_dot=1000000,
                    frame=dict(epoch=4, sequence=7, dot=999000))

    def test_one_frame_lag_and_literal_pause_flow(self):
        changes, count = schedule(SUCCESS_FLOW)
        events = [(LCD+frame*PERIOD+8192, buttons) for frame, buttons in changes]
        self.assertEqual(count, 394)
        self.assertEqual(predict(1, events, LCD).mode, TITLE)
        self.assertEqual(predict(2, events, LCD).player.x, 26*16)
        self.assertEqual((predict(361, events, LCD).mode, predict(361, events, LCD).score), (WON, 2))
        for update, mode, timer, x in ((361, PLAYING, 0, 24), (364, PAUSED, 2, 24),
                (366, PAUSED, 2, 24), (368, PLAYING, 2, 24), (369, PLAYING, 3, 24),
                (371, PLAYING, 0, 24), (373, PLAYING, 2, 24), (376, PLAYING, 0, 24),
                (392, PLAYING, 16, 52), (394, PLAYING, 18, 56)):
            state = predict(update+1, events, LCD)
            self.assertEqual((state.mode, state.timer, state.player.x), (mode, timer, x*16))
            self.assertEqual(state.player.y, 112*16)
            self.assertEqual(state.player.camera, 0)

    def test_metadata_confirms_planned_frame_and_window(self):
        metadata = dict(epoch=6, seq=2, dot=LCD+2*PERIOD+65459)
        expected_snapshot(metadata, 2, [(LCD+8192, 161)], 6, LCD, render)
        with self.assertRaisesRegex(AssertionError, 'IDENTITY'):
            expected_snapshot(metadata, 3, [], 6, LCD, render)
        with self.assertRaisesRegex(AssertionError, 'INPUT_WINDOW'):
            predict(2, [(LCD+VISIBLE, 161)], LCD)

    def test_both_complete_synthetic_routes(self):
        for mode in ('feasibility', 'success', 'death-retry'):
            endpoint = Endpoint()
            with tempfile.TemporaryDirectory() as folder:
                result = run(endpoint, bytes(32768), folder, lambda entry: None,
                             'original', self.prior(), LCD, mode, renderer=render, sleep=endpoint.sleep)
            self.assertEqual(len(result['checkpoints']), len(plan(mode)[1]))
            self.assertFalse(endpoint.running)
            self.assertEqual(endpoint.mask, 0)
            if mode == 'feasibility':
                self.assertEqual(len(result['events']), 9)  # Eight probes plus finalINPUT0.
                self.assertTrue(all(mask == 0 for _, mask in result['events']))

    def test_missed_window_and_bad_frame_fail_closed(self):
        for kwargs, message in ((dict(stall=True), 'MISSED_WINDOW'), (dict(fault=True), 'FLOW_PIXELS')):
            endpoint = Endpoint(**kwargs)
            with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(AssertionError, message):
                run(endpoint, bytes(32768), folder, lambda entry: None,
                    'original', self.prior(), LCD, 'success', renderer=render, sleep=endpoint.sleep)
            self.assertFalse(endpoint.running)
            self.assertEqual(endpoint.mask, 0)

    def test_uncertain_reply_has_no_cleanup_commands(self):
        endpoint = Endpoint(uncertain=True)
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(RuntimeError, 'lost reply'):
            run(endpoint, bytes(32768), folder, lambda entry: None,
                'original', self.prior(), LCD, 'success', renderer=render, sleep=endpoint.sleep)
        self.assertTrue(endpoint.uncertain)
        self.assertNotEqual(endpoint.calls[-1], ('INPUT', 0))

    def test_bad_prior_does_not_load_or_arm_cleanup(self):
        endpoint = Endpoint()
        prior = self.prior()
        prior['frame']['epoch'] = 2
        with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(AssertionError, 'PRIOR_FRAME'):
            run(endpoint, bytes(32768), folder, lambda entry: None,
                'original', prior, LCD, 'feasibility', renderer=render, sleep=endpoint.sleep)
        self.assertFalse(endpoint.loaded)
        self.assertEqual(endpoint.calls, [])


if __name__ == '__main__':
    unittest.main()
