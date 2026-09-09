import hashlib
import json
from pathlib import Path
import unittest
from scene_art import PAIRS


class OriginalSceneArt(unittest.TestCase):
    def test_original_prefix_and_dimensions(self):
        path = Path(__file__).resolve().parents[2]/'sw/springtrail/tiles.json'
        data = json.loads(path.read_text())
        self.assertEqual((data['width'], data['height']), (336, 8))
        original = bytes(p for row in data['pixels'] for p in row[:128])
        self.assertEqual(hashlib.sha256(original).hexdigest(), '1c885699db19fc342e336830e349b2bc17798e8485f756758b004f4b10fe6e64')

    def test_all_original_scene_pairs(self):
        path = Path(__file__).resolve().parents[2]/'sw/springtrail/tiles.json'
        data = json.loads(path.read_text())['pixels']
        for tile, rows in PAIRS.items():
            actual = tuple(''.join(map(str, data[y%8][(tile+y//8)*8:(tile+y//8+1)*8])) for y in range(16))
            self.assertEqual(actual, rows)
            if tile != 20:
                self.assertEqual(rows[8:], ('00000000',)*8)


if __name__ == '__main__':
    unittest.main()
