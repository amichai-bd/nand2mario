"""Host control-flow checks of the board menu proof; the fake menu is not DUT evidence.

The fake endpoint follows the menu contract's frame rules (boot with the LCD
off, the splash schedule, one sampled joypad edge a frame, the two-frame
footer, the scroll ramp, the refused select, the swap) so that the driver's
scripted session and the compare helper are proven together before the board.
"""
import hashlib
import json
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.host import library  # noqa: E402
from n2m.host.client import RejectedCommand  # noqa: E402
import board_compare  # noqa: E402
import board_menu  # noqa: E402
import reference  # noqa: E402

# The eleven-game registry's shape: slots 0..10 valid, taglines on every game,
# a 64 KiB MBC1 entry at slot 10 and its second half empty, the menu at 16.
GAMES = {0: (b'SPRINGTRAIL', b'RUN THE TRAIL'), 1: (b'STACKDROP', b'FILL ROWS TO CLEAR'),
         2: (b'V05 BUTTONS', b'BUTTON TEST'), 3: (b'LIBBET', b'ROLL ON THE FLOOR'),
         4: (b'AIRAKI', b'MATCH AND BATTLE'), 5: (b'GB WORDYL', b'GUESS THE WORD'),
         6: (b'MAX PIRATE', b'A PIRATE ADVENTURE'), 7: (b'ALIEN INVASION', b'SHOOT THE INVADERS'),
         8: (b'SQUARE FALL', b'CHAIN THE SQUARES'), 9: (b'KNIGHT', b'DODGE THE HAZARDS'),
         10: (b'POSTBOT', b'MBC1 TEST GAME')}
GAME_FRAME = bytes((x // 8 + y // 8) % 4 for y in range(144) for x in range(160))


def image(title, size=32768):
    data = bytearray(size)
    data[0x134:0x134 + len(title)] = title
    return bytes(data)


def catalogue_bytes():
    entries = {}
    for index, (title, tagline) in GAMES.items():
        profile = abi.PROFILE_MBC1_ID if index == 10 else abi.PROFILE_DIRECT_ID
        entries[index] = library.image_entry(image(title, library.profile_bytes(profile)), profile, tagline=tagline)
    entries[16] = library.image_entry(image(b'GAME MENU'), abi.PROFILE_LOADER_ID)
    return library.build_catalogue(entries)


CATALOGUE = catalogue_bytes()
ENTRIES = library.parse_catalogue(CATALOGUE)


def pack(pixels):
    return bytes(sum(pixels[n + i] << (2 * i) for i in range(4)) for n in range(0, 23040, 4))


class FakeMenu:
    """The menu image's frame rules on a host-paused core, one VBlank per RUN_DOTS frame."""

    def __init__(self, *, build_id='expected', index=reference.NO_INDEX, boot_frames=3, offset=0, lead=0):
        self.build_id, self.boot, self.offset, self.lead = build_id, boot_frames, offset, lead
        self.epoch, self.dot, self.state, self.profile = 1, 0, abi.STATE_PAUSED, abi.PROFILE_LOADER_ID
        self.buttons = self.sampled = 0
        self.index, self.result = index, reference.RESULT_NONE
        self.uncertain = False
        self.inputs = []
        self.reboot()

    def reboot(self):
        self.seq, self.published = 0, None
        self.boot_left = self.boot
        # The board's observer publishes `lead` complete frames ending at the
        # VBlank of the first loop iteration, before displayed frame 0.
        self.lead_left = self.lead
        self.splash = 0 if self.index == reference.NO_INDEX else None
        self.frame_number, self.cursor, self.footer = 0, 0, None
        self.scy = reference.SETTLED_SCY
        # `offset` pending frames model a pause point after the VBlank: the
        # first completed frame after a change still shows the state before it.
        self.pending = []

    def identify(self):
        return dict(build_id=self.build_id, abi=1)

    def read_host(self, address):
        if address == abi.HOST_REG_STATE:
            return self.state
        if address == abi.HOST_REG_PROFILE:
            return self.profile
        if address == abi.HOST_REG_IMAGE_VALID:
            return 1
        if address == abi.HOST_REG_LIBRARY_STATUS:
            a000 = abi.LIBRARY_STATUS_SDRAM_READY | abi.LIBRARY_STATUS_WINDOW_READY | abi.LIBRARY_STATUS_FLASH_BOOT
            return a000 | (self.result << 8) | (self.index << 16) | (34 << 24)
        raise AssertionError(address)

    def write_host(self, address, value):
        assert (address, value) == (abi.HOST_REG_LIBRARY_CONTROL, abi.LIBRARY_CONTROL_RETURN)
        self.profile, self.epoch, self.state = abi.PROFILE_LOADER_ID, self.epoch + 1, abi.STATE_RUNNING
        self.result = reference.RESULT_OK
        self.reboot()
        return dict(dot=self.dot)

    def sdram_read(self, address, lines=1):
        start = address - abi.LIBRARY_CATALOGUE_ADDRESS
        return CATALOGUE[start:start + lines * 16]

    def control(self, action, value=None):
        if action == 'INPUT':
            self.buttons = value
            self.inputs.append(value)
            return dict(dot=self.dot)
        if action == 'RESET':
            self.epoch, self.state, self.dot = self.epoch + 1, abi.STATE_PAUSED, 0
            self.reboot()
            return None
        if action == 'RUN':
            self.state = abi.STATE_RUNNING
            return None
        if action == 'HALT':
            self.state = abi.STATE_PAUSED
            return dict(dot=self.dot)
        raise AssertionError(action)

    def run_dots(self, count):
        assert self.state == abi.STATE_PAUSED and count == board_menu.FRAME_DOTS
        self.dot += count
        stopped = self.frame()
        executed = count // 2 if stopped else count
        return dict(dot=self.dot, executed=executed,
                    reason=abi.WIRE_RUN_DOTS_STOPPED if stopped else abi.WIRE_RUN_DOTS_COUNT)

    def snapshot(self):
        if self.state == abi.STATE_RUNNING:
            self.frame()
            while self.published is None:
                self.frame()
        if self.published is None:
            raise RejectedCommand('SNAPSHOT', abi.STATUS_NO_FRAME)
        return dict(epoch=self.epoch, seq=self.seq, dot=self.dot, size=5760), self.published

    def publish(self, pixels):
        self.pending.append(pack(pixels))
        if len(self.pending) > self.offset:
            self.published = self.pending.pop(0)
            self.seq += 1

    def draw(self):
        if self.splash is not None and self.splash < reference.SETTLED_FRAME:
            bgp, scy, wrapped = reference.splash_state(self.splash)
            return reference.frame(ENTRIES, bgp=bgp, scy=scy, wrapped=wrapped)
        return reference.frame(ENTRIES, cursor=self.cursor, footer=self.footer, scy=self.scy,
                               phase=reference.phase_of_frame(self.frame_number), result=self.result, index=self.index)

    def frame(self):
        """One displayed frame: publish what the last VBlank left, then run this frame's VBlank."""
        if self.profile != abi.PROFILE_LOADER_ID:
            self.publish(GAME_FRAME)
            return False
        if self.boot_left:
            self.boot_left -= 1
            return False
        if self.lead_left and self.splash is not None:
            self.lead_left -= 1
            self.publish(self.draw())
            return False
        self.publish(self.draw())
        edges = self.buttons & ~self.sampled
        self.sampled = self.buttons
        if self.splash is not None and self.splash < reference.SETTLED_FRAME:
            self.splash += 1
            return False
        self.splash = None
        before = self.cursor
        if edges & abi.BUTTON_DOWN and self.cursor < reference.SLOTS - 1:
            self.cursor += 1
        elif edges & abi.BUTTON_UP and self.cursor > 0:
            self.cursor -= 1
        stopped = False
        if edges & abi.BUTTON_A:
            entry = ENTRIES[self.cursor]
            self.index = self.cursor
            if entry['valid'] == library.VALID:
                self.result, self.profile, self.epoch = reference.RESULT_OK, entry['profile'], self.epoch + 1
                self.reboot()
                stopped = True
            else:
                self.result = reference.RESULT_INVALID_SLOT
        if self.cursor != before:
            self.footer = (self.cursor, before)
        elif self.footer is not None:
            self.footer = None
        target = reference.scroll_target(self.cursor)
        if self.scy != target:
            self.scy += reference.SCROLL_STEP if target > self.scy else -reference.SCROLL_STEP
        self.frame_number += 1
        return stopped


def run(endpoint, folder, **options):
    log = []
    result = board_menu.run(endpoint, folder, log.append, 'expected', **options)
    return result, log


class BoardMenuTests(unittest.TestCase):
    def test_complete_session_passes_on_the_menu_rules(self):
        endpoint = FakeMenu()
        with tempfile.TemporaryDirectory() as folder:
            result, log = run(endpoint, folder, packed_catalogue_sha256=hashlib.sha256(CATALOGUE).hexdigest(),
                              game_frame_sha256=hashlib.sha256(pack(GAME_FRAME)).hexdigest())
            self.assertEqual(result['status'], 'PASS')
            names = [capture['name'] for capture in result['captures']]
            for name in ('splash-first', 'splash-16', 'idle-phase-1', 'idle-phase-0', 'footer-1-0', 'cursor-2',
                         'scroll-1', 'scroll-4', 'back-1', 'cursor-14', 'cursor-11', 'refused', 'footer-10-11',
                         'cursor-10', 'game', 'menu-after-return'):
                self.assertIn(name, names)
            self.assertEqual(result['splash'], dict(boot_frames=4, first=0, lead=0, frames=17))
            self.assertEqual(result['idle']['phases'], [0, 1, 0])
            self.assertEqual(result['refused']['result'], 'INVALID_SLOT')
            self.assertEqual(result['select']['library_status']['a003'], 2)
            self.assertEqual(result['return']['endpoint']['PROFILE'], abi.PROFILE_LOADER_ID)
            self.assertFalse(any(entry['kind'] == 'wait' for entry in log))
            # Every capture is retained with its comparison and its pictures.
            folders = sorted(path for path in Path(folder).iterdir() if path.is_dir())
            self.assertEqual(len(folders), len(result['captures']))
            for path in folders:
                self.assertTrue((path / 'frame.2bpp').is_file(), path)
                if path.name.endswith('-game'):
                    continue
                record = json.loads((path / 'compare.json').read_text())
                self.assertTrue(record['matches'], path)
                self.assertTrue((path / 'diff.png').is_file() and (path / 'reference.png').is_file())
            self.assertEqual(json.loads((Path(folder) / 'result.json').read_text())['status'], 'PASS')
        self.assertEqual(endpoint.inputs[-1], 0)
        self.assertEqual(endpoint.state, abi.STATE_RUNNING)

    def test_a_pause_point_after_the_vblank_costs_one_wait_frame_each(self):
        endpoint = FakeMenu(offset=1)
        with tempfile.TemporaryDirectory() as folder:
            result, log = run(endpoint, folder)
        self.assertEqual(result['status'], 'PASS')
        self.assertTrue(any(entry['kind'] == 'wait' for entry in log))

    def test_the_boards_leading_blank_frame_is_accepted_once(self):
        # Session 10 first attempt: seq 0, 1 and 2 were all the BGP $00 frame
        # before the fade advanced, one frame more than the schedule's hold.
        endpoint = FakeMenu(lead=1)
        with tempfile.TemporaryDirectory() as folder:
            result, log = run(endpoint, folder, steps=('splash', 'idle'))
            names = [capture['name'] for capture in result['captures']]
            seqs = [capture['seq'] for capture in result['captures'][:18]]
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['splash'], dict(boot_frames=4, first=0, lead=1, frames=17))
        self.assertEqual(names[:4], ['splash-first', 'splash-1', 'splash-2', 'splash-2'])
        self.assertEqual(seqs, list(range(1, 19)))
        self.assertIn(dict(kind='splash-lead', seq=3), log)
        self.assertEqual(result['idle']['phases'], [0, 1, 0])

    def test_two_leading_blank_frames_fail_the_order_check(self):
        endpoint = FakeMenu(lead=2)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, r'MENU_BOARD_SPLASH_ORDER after 1: \[0, 1\]'):
                run(endpoint, folder, steps=('splash',))

    def test_build_id_mismatch_stops_before_the_board_moves(self):
        endpoint = FakeMenu(build_id='other')
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, 'MENU_BOARD_BUILD_ID'):
                run(endpoint, folder)
        self.assertEqual(endpoint.inputs, [0])

    def test_a_selected_index_disarms_the_splash(self):
        endpoint = FakeMenu(index=2)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, 'MENU_BOARD_SPLASH_ARMED'):
                run(endpoint, folder, steps=('splash',))
            record = json.loads((Path(folder) / 'result.json').read_text())
        self.assertEqual(record['status'], 'FAIL')

    def test_a_wrong_frame_fails_and_keeps_the_capture(self):
        endpoint = FakeMenu()
        endpoint.draw = lambda: bytes([1]) * 23040
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(AssertionError, 'MENU_BOARD_PIXEL splash-first'):
                run(endpoint, folder, steps=('splash',))
            record = json.loads(next(Path(folder).glob('00-splash-first/compare.json')).read_text())
        self.assertFalse(record['matches'])
        self.assertEqual(endpoint.inputs[-1], 0)

    def test_steps_without_the_splash_pause_a_running_menu(self):
        endpoint = FakeMenu(index=2)
        endpoint.state = abi.STATE_RUNNING
        for _ in range(5):
            endpoint.frame()
        with tempfile.TemporaryDirectory() as folder:
            result, log = run(endpoint, folder, steps=('idle', 'cursor'))
        self.assertEqual(result['status'], 'PASS')
        self.assertIn(dict(kind='halt'), log)


class BoardCompareTests(unittest.TestCase):
    def test_every_named_class_matches_its_own_packed_frame_only(self):
        samples = ['menu', 'phase-1', 'cursor-2', 'footer-1-0', 'scroll-3', 'back-1', 'back-2', 'splash-5',
                   'splash-16', 'cursor-15']
        frames = {sample: pack(reference.frame(ENTRIES, **board_compare.state_of(sample))) for sample in samples}
        for sample, packed in frames.items():
            record = board_compare.compare(packed, ENTRIES, board_compare.candidates(sample))
            self.assertTrue(record['match'], sample)
            self.assertEqual(record['frame_crc32'], f'{zlib.crc32(reference.unpack(packed)):08x}')
        self.assertEqual(board_compare.compare(frames['scroll-3'], ENTRIES, board_compare.candidates('ramp'))['matches'],
                         ['scroll-3/phase-0'])
        self.assertEqual(board_compare.compare(frames['splash-5'], ENTRIES, board_compare.candidates('splash'))['matches'],
                         ['splash-4', 'splash-5'])
        self.assertEqual(board_compare.compare(frames['splash-16'], ENTRIES, board_compare.candidates('splash'))['matches'],
                         ['splash-16'])
        self.assertEqual(board_compare.compare(frames['menu'], ENTRIES, board_compare.candidates('phase'))['matches'],
                         ['phase-0'])
        self.assertEqual(frames['cursor-15'], pack(reference.expected('scroll-4', ENTRIES)))
        self.assertFalse(board_compare.compare(frames['cursor-2'], ENTRIES, board_compare.candidates('cursor-1'))['match'])

    def test_the_status_bytes_reach_every_candidate(self):
        refused = pack(reference.frame(ENTRIES, cursor=11, result=reference.RESULT_INVALID_SLOT, index=11))
        plain = board_compare.compare(refused, ENTRIES, board_compare.candidates('cursor-11'))
        self.assertFalse(plain['match'])
        self.assertEqual(plain['candidates'][0]['first_mismatch']['y'] // 8, reference.STATUS_ROW)
        marked = board_compare.compare(refused, ENTRIES, board_compare.candidates(
            'cursor-11', result=reference.RESULT_INVALID_SLOT, index=11))
        self.assertEqual(marked['matches'], ['cursor-11/phase-0'])

    def test_the_command_line_writes_the_record_and_pictures(self):
        with tempfile.TemporaryDirectory() as folder:
            frame = Path(folder) / 'frame.2bpp'
            frame.write_bytes(pack(reference.frame(ENTRIES, phase=1)))
            catalogue = Path(folder) / 'catalogue.bin'
            catalogue.write_bytes(CATALOGUE)
            out = Path(folder) / 'out'
            self.assertEqual(board_compare.main([str(frame), str(catalogue), str(out), 'phase']), 0)
            record = json.loads((out / 'compare.json').read_text())
            self.assertEqual(record['matches'], ['phase-1'])
            self.assertEqual(record['rendered'], 'phase-1')
            self.assertEqual(record['entries'][2]['tagline'], 'BUTTON TEST')
            for name in ('frame.png', 'reference.png', 'diff.png'):
                self.assertEqual((out / name).read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
            self.assertEqual(board_compare.main([str(frame), str(catalogue), str(out), 'phase-0']), 1)
            with self.assertRaises(ValueError):
                board_compare.state_of('nothing-1')


if __name__ == '__main__':
    unittest.main()
