"""Original v0.5 recipe checks against literal timing and image checkpoints."""
import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('v05_reference', ROOT / 'src/dv/v05/reference.py')
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class V05ReferenceTests(unittest.TestCase):
    def test_initialization_and_first_wake(self):
        model = reference.Reference()
        rows = list(model.records(108156))
        self.assertEqual(model.lcd_commit, 41984)
        self.assertEqual(len(rows), 6357)
        self.assertEqual(rows[6280]['dot'], 42008)
        self.assertEqual(rows[6280]['halted'], 1)
        self.assertEqual(rows[6281]['dot'], 107656)
        self.assertEqual(rows[6281]['iflags'], 1)
        self.assertEqual(rows[-1]['dot'], 108156)
        self.assertEqual(rows[-1]['iflags'], 0)
        self.assertEqual(rows[-1]['halted'], 1)
        map_clear = [w for w in model.writes if 0x9800 <= w[1] < 0x9c00][:1024]
        self.assertEqual([(a, v) for _, a, v in map_clear], [(a, 0) for a in range(0x9800, 0x9c00)])
        tiles = [(a, v) for _, a, v in model.writes if 0x8000 <= a < 0x8020]
        self.assertEqual(tiles, [(0x8000+i, 0 if i < 16 or i % 2 else 255) for i in range(32)])

    def test_all_buttons_and_pair_have_literal_frame_effects(self):
        events = [(reference.input_window(j)[0], mask) for j, mask in enumerate(reference.INPUT_MASKS, 1)]
        model = reference.Reference(events)
        samples = {}
        count = 0
        for row in model.records(reference.WINDOW_END):
            count += 1
            if row['pc_before'] == 0x244:
                samples[row['dot']] = row
        self.assertEqual(count, 51957)
        for j, mask in enumerate((1,0,2,0,4,0,8,0,16,0,32,0,64,0,128,0,17,0), 1):
            # First effected image20*j+3 follows VBlank index20*j+2.
            halt_dot = 108156 + (20*j+2)*70224
            self.assertEqual(samples[halt_dot]['c'], mask)
            self.assertEqual(samples[halt_dot]['buttons'], mask)
            self.assertEqual(samples[halt_dot]['iflags'], 0)
            for bit in range(8):
                self.assertEqual(reference.pixel_shade(20*j+3, 8*bit, 64), (mask >> bit) & 1)
            self.assertEqual(reference.pixel_shade(20*j+3, 64, 64), 0)
        self.assertEqual(reference.pixel_shade(0, 0, 0), 0)
        self.assertEqual(reference.pixel_shade(1, 0, 0), 1)
        self.assertEqual(reference.pixel_shade(601, 0, 64), 0)

    def test_full_record_field_error_and_known_abi(self):
        model = reference.Reference()
        expected = next(model.records(8))
        literal = '0000000000000000fffe0000000000000000010000000101010000000000000000080000000000000000000000020001'
        self.assertEqual(reference.unpack_retirement(literal), expected)
        for field in expected:
            changed = dict(expected)
            changed[field] ^= 1
            with self.assertRaisesRegex(ValueError, 'field=' + field):
                reference.compare_record(expected, changed)


if __name__ == '__main__':
    unittest.main()
