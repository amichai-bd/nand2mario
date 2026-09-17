"""Menu design previews compose from the committed sources and reproduce the published SVGs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.sw.assets import validate_shades
from tools.sw.menu_art import DIRECTIONS, FONT_TILES, SAMPLE, STATES, generate

ROOT = Path(__file__).resolve().parents[3]
PREVIEWS = ROOT / 'wiki/src/sw/menu/previews'
# The costs the design note quotes; each direction pays for its own tiles only.
EXPECTED = {'a-plated-list': (82, 3, 43), 'b-cartridge-shelf': (60, 21, 21),
            'c-night-deck': (49, 10, 10)}


class MenuArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / 'workdir/builds/menu-art-unit'
        parent.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=parent)
        cls.out = Path(cls.temp.name)
        cls.summary = generate(ROOT, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_authored_banks_are_strict_shade_rows(self):
        for name, (_, source) in DIRECTIONS.items():
            data = json.loads((ROOT / 'src/sw/menu/assets/design' / source).read_text())
            validate_shades(data)
            self.assertEqual(data['height'], 8, name)
            self.assertEqual(data['width'] % 8, 0, name)
            self.assertEqual(data['width'] // 8, EXPECTED[name][1], name)

    def test_costs_match_the_design_note(self):
        for name, (tiles, authored, added) in EXPECTED.items():
            entry = self.summary[name]
            self.assertEqual((entry['tiles'], entry['authored_tiles'], entry['added_tiles']),
                             (tiles, authored, added), name)
            self.assertEqual(entry['added_bytes'], 16 * added, name)
            self.assertEqual(entry['tiles'], FONT_TILES + added, name)
            self.assertLess(entry['tiles'], 256, name)

    def test_screens_are_full_game_boy_frames_of_four_shades(self):
        self.assertEqual(len(SAMPLE), 16)
        for name in DIRECTIONS:
            for state, _ in STATES:
                data = json.loads((self.out / name / f'{state}.json').read_text())
                self.assertEqual((data['width'], data['height']), (160, 144), (name, state))
                self.assertLessEqual({v for row in data['pixels'] for v in row}, {0, 1, 2, 3})

    def test_an_animation_phase_changes_the_frame(self):
        for name in DIRECTIONS:
            first = (self.out / name / 'list.json').read_text()
            second = (self.out / name / 'phase.json').read_text()
            self.assertNotEqual(first, second, name)

    def test_published_svgs_reproduce(self):
        published = sorted(PREVIEWS.glob('*.svg'))
        self.assertEqual([path.name for path in published],
                         sorted(f'{name}-{view}.svg' for name in DIRECTIONS
                                for view in ('screens', 'new-art')))
        for name in DIRECTIONS:
            for view in ('screens', 'new-art'):
                path = PREVIEWS / f'{name}-{view}.svg'
                self.assertEqual(path.read_text(), (self.out / name / f'{view}.svg').read_text(), path)


if __name__ == '__main__':
    unittest.main()
