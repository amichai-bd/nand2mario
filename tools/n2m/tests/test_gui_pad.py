"""Pad input, per-cycle order and exit against a fake endpoint; no board, no window."""
import io
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from contextlib import contextmanager
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.gui_pad import Controller, edge, explain_conflict, names, pad_loop, virtual_key
from n2m.host.keyboard import KEYS
import fpga_viewer

ROOT = Path(__file__).resolve().parents[3]
BUILD = 'ab' * 16
RIGHT, LEFT, UP, DOWN, A, B, SELECT, START = 0x27, 0x25, 0x26, 0x28, 0x5a, 0x58, 0xa1, 0x0d


class Fake:
    """The Client surface the pad uses, recording every request in order."""

    def __init__(self, *, state=abi.STATE_RUNNING, build=BUILD, valid=1,
                 source=abi.INPUT_SOURCE_UART, effective=0, fail_on=None):
        self.state, self.build, self.valid, self.source = state, build, valid, source
        self.effective = effective
        self.fail_on = fail_on
        self.uncertain = False
        self.sequence = 0
        self.events = []
        self.masks = []
        self.dot = 0

    def identify(self):
        self.events.append('identify')
        return {'abi': abi.WIRE_ABI, 'build_id': self.build}

    def read_host(self, address):
        self.events.append(('read', address))
        return {abi.HOST_REG_IMAGE_VALID: self.valid, abi.HOST_REG_INPUT_SOURCE: self.source,
                abi.HOST_REG_INPUT_EFFECTIVE: self.effective, abi.HOST_REG_STATE: self.state}[address]

    def control(self, action, value=None):
        self.events.append((action, value))
        self.sequence += 1
        if action == 'INPUT':
            if self.fail_on is not None and value == self.fail_on:
                raise RuntimeError('wire rejected INPUT')
            self.masks.append(value)
            self.effective = value
            self.dot += 100
            return {'dot': self.dot}
        if action == 'RUN':
            self.state = abi.STATE_RUNNING
        return {'dot': self.dot}


def script(*edges, polls=0):
    """A stand-in window that replays edges and returns, like a closed window."""
    def window(controller, seconds=None):
        for code, down in edges:
            controller.apply(code, down)
        for _ in range(polls):
            controller.client.read_host(abi.HOST_REG_STATE)
    return window


class MappingTests(unittest.TestCase):
    def test_pad_uses_the_host_keyboard_mapping_itself(self):
        self.assertEqual(KEYS, {0x27: abi.BUTTON_RIGHT, 0x25: abi.BUTTON_LEFT, 0x26: abi.BUTTON_UP,
                                0x28: abi.BUTTON_DOWN, 0x5a: abi.BUTTON_A, 0x58: abi.BUTTON_B,
                                0xa1: abi.BUTTON_SELECT, 0x0d: abi.BUTTON_START})
        for keysym, code in (('Right', RIGHT), ('Left', LEFT), ('Up', UP), ('Down', DOWN),
                             ('z', A), ('Z', A), ('x', B), ('X', B), ('Shift_R', SELECT),
                             ('Return', START)):
            self.assertEqual(virtual_key(keysym, 0), code, keysym)

    def test_unmapped_and_left_shift_are_ignored(self):
        self.assertIsNone(virtual_key('Shift_L', 0x10))
        self.assertIsNone(virtual_key('q', 0x51))
        self.assertIsNone(edge('q', 0x51, 0, True))

    def test_windows_keycode_reaches_the_same_mapping(self):
        self.assertEqual(edge('??', RIGHT, 0, True), (RIGHT, True))

    def test_control_modified_down_ignored_but_release_still_clears(self):
        self.assertIsNone(edge('z', A, 0x4, True))
        self.assertEqual(edge('z', A, 0x4, False), (A, False))

    def test_names_follow_the_generated_bits(self):
        self.assertEqual(names(abi.BUTTON_LEFT | abi.BUTTON_A), ['Left', 'A'])


class ControllerTests(unittest.TestCase):
    def test_one_write_per_changed_union_and_repeats_ignored(self):
        client = Fake()
        pad = Controller(client)
        self.assertTrue(pad.press(RIGHT))
        self.assertFalse(pad.press(RIGHT))  # Auto-repeat changes nothing.
        self.assertTrue(pad.press(A))
        self.assertTrue(pad.release(RIGHT))
        self.assertFalse(pad.release(RIGHT))
        self.assertEqual(client.masks, [abi.BUTTON_RIGHT, abi.BUTTON_RIGHT | abi.BUTTON_A, abi.BUTTON_A])
        self.assertEqual(pad.changes, 3)

    def test_chords_and_opposite_directions_are_preserved(self):
        client = Fake()
        pad = Controller(client)
        pad.press(LEFT)
        pad.press(RIGHT)
        pad.press(B)
        self.assertEqual(client.masks[-1], abi.BUTTON_LEFT | abi.BUTTON_RIGHT | abi.BUTTON_B)
        self.assertEqual(pad.held_names(), ['Right', 'Left', 'B'])

    def test_a_held_key_stays_held_until_its_release(self):
        client = Fake()
        pad = Controller(client)
        pad.press(RIGHT)
        for _ in range(5):
            pad.press(RIGHT)
        self.assertEqual(client.masks, [abi.BUTTON_RIGHT])
        self.assertEqual(client.effective, abi.BUTTON_RIGHT)

    def test_mouse_and_keyboard_produce_the_same_writes(self):
        keyed, clicked = Fake(), Fake()
        pad = Controller(keyed)
        for keysym, down in (('Right', True), ('z', True), ('Right', False), ('z', False)):
            found = edge(keysym, 0, 0, down)
            pad.apply(*found)
        mouse = Controller(clicked)
        mouse.press(RIGHT)
        mouse.press(A)
        mouse.release(RIGHT)
        mouse.release(A)
        self.assertEqual(keyed.masks, clicked.masks)
        self.assertEqual(keyed.events, clicked.events)

    def test_records_every_mask_with_its_acknowledged_dot(self):
        rows = []
        pad = Controller(Fake(), rows.append)
        pad.press(START)
        pad.release(START)
        self.assertEqual([row['mask'] for row in rows], [abi.BUTTON_START, 0])
        self.assertTrue(all(row['dot'] for row in rows))


class SessionTests(unittest.TestCase):
    def test_cycle_order_preflight_then_inputs_then_verified_release(self):
        client = Fake(state=abi.STATE_PAUSED)
        result = pad_loop(client, expected_build=BUILD, window=script((RIGHT, True), (RIGHT, False)))
        self.assertEqual(client.events, [
            'identify',
            ('read', abi.HOST_REG_IMAGE_VALID), ('read', abi.HOST_REG_INPUT_SOURCE),
            ('read', abi.HOST_REG_INPUT_EFFECTIVE), ('read', abi.HOST_REG_STATE),
            ('RUN', None), ('read', abi.HOST_REG_STATE),
            ('INPUT', abi.BUTTON_RIGHT), ('INPUT', 0),
            ('INPUT', 0), ('read', abi.HOST_REG_INPUT_EFFECTIVE)])
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(result['released'])
        self.assertEqual(result['cleanup'], {'verified': True, 'input_effective': 0, 'dot': client.dot})
        self.assertEqual(result['changes'], 2)

    def test_running_core_is_left_running_and_never_halted(self):
        client = Fake()
        pad_loop(client, expected_build=BUILD, window=script((A, True), (A, False)))
        self.assertNotIn(('HALT', None), client.events)
        self.assertEqual(client.state, abi.STATE_RUNNING)

    def test_exit_releases_a_still_held_button(self):
        client = Fake()
        result = pad_loop(client, expected_build=BUILD, window=script((LEFT, True), (A, True)))
        self.assertEqual(client.masks[-1], 0)
        self.assertEqual(client.effective, 0)
        self.assertTrue(result['released'])
        self.assertEqual(result['status'], 'PASS')

    def test_uncertain_session_sends_no_further_traffic(self):
        client = Fake()

        def window(controller, seconds=None):
            controller.press(A)
            controller.client.uncertain = True
        result = pad_loop(client, expected_build=BUILD, window=window)
        self.assertEqual(client.masks, [abi.BUTTON_A])
        self.assertEqual(result['status'], 'FAIL')
        self.assertFalse(result['released'])
        self.assertEqual(result['cleanup'], {'verified': False, 'reason': 'uncertain; no further traffic'})

    def test_failed_release_is_reported_not_claimed(self):
        client = Fake(fail_on=0)
        result = pad_loop(client, expected_build=BUILD, window=script((A, True)))
        self.assertFalse(result['released'])
        self.assertEqual(result['status'], 'FAIL')
        self.assertIn('wire rejected INPUT', result['cleanup']['reason'])

    def test_window_failure_still_releases_and_fails(self):
        client = Fake()

        def window(controller, seconds=None):
            controller.press(UP)
            raise RuntimeError('window died')
        result = pad_loop(client, expected_build=BUILD, window=window)
        self.assertEqual(result['reason'], 'RuntimeError')
        self.assertEqual(client.masks[-1], 0)
        self.assertTrue(result['released'])
        self.assertEqual(result['status'], 'FAIL')

    def test_preconditions_send_no_control_traffic(self):
        for client, reason in ((Fake(build='cd' * 16), 'build mismatch'),
                               (Fake(valid=0), 'no valid existing image'),
                               (Fake(source=abi.INPUT_SOURCE_PHYSICAL), 'UART input authority required'),
                               (Fake(effective=abi.BUTTON_A), 'neutral effective input required'),
                               (Fake(state=abi.STATE_LOADING),
                                'existing image must be paused or running')):
            result = pad_loop(client, expected_build=BUILD, window=script((A, True)))
            self.assertEqual(result['status'], 'FAIL')
            self.assertEqual(result['error'], reason)
            self.assertFalse(result['released'])
            self.assertEqual(result['cleanup']['reason'], 'preconditions failed; no control sent')
            self.assertEqual(client.masks, [])


class ConflictTests(unittest.TestCase):
    def test_busy_board_names_the_actual_cause(self):
        self.assertIn('Another trusted controller already holds this machine',
                      explain_conflict(ValueError('trusted controller already running')))
        self.assertIn('device lock', explain_conflict(FileExistsError('lock')))
        self.assertIn('uncertain', explain_conflict(RuntimeError(
            'previous completion is uncertain; recover the endpoint session explicitly before opening')))
        self.assertIsNone(explain_conflict(ValueError('something else')))


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        # argparse and the tool both write to the real streams; keep test output clean.
        for name in ('stdout', 'stderr'):
            patcher = patch.object(sys, name, io.StringIO())
            self.streams = getattr(self, 'streams', {})
            self.streams[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def tag(self):
        name = 'guipad' + uuid.uuid4().hex
        self.addCleanup(shutil.rmtree, ROOT / 'workdir/builds' / name, ignore_errors=True)
        return name

    def test_gui_refuses_viewer_only_options(self):
        with self.assertRaises(SystemExit):
            fpga_viewer.main(['--gui', '--expected-build-id', BUILD, '--credentials', 'x'])
        with self.assertRaises(SystemExit):
            fpga_viewer.main(['--gui'])

    def test_viewer_without_the_flag_still_requires_credentials(self):
        with self.assertRaises(SystemExit):
            fpga_viewer.main(['--expected-build-id', BUILD])

    def test_held_board_is_refused_with_the_cause(self):
        tag = self.tag()

        @contextmanager
        def busy(_identifier):
            raise ValueError('trusted controller already running')
            yield
        with patch.object(fpga_viewer, 'machine_lock', busy):
            code = fpga_viewer.main(['--gui', '--tag', tag, '--expected-build-id', BUILD])
        self.assertEqual(code, 1)
        self.assertIn('Another trusted controller already holds this machine',
                      self.streams['stderr'].getvalue())
        result = json.loads((ROOT / 'workdir/builds' / tag / 'gui-pad/result.json').read_text())
        self.assertIn('Another trusted controller', result['conflict'])
        self.assertFalse(result['released'])


if __name__ == '__main__':
    unittest.main()
