"""Menu v2 previews compose from the committed sources and reproduce the published SVGs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.sw.assets import validate_shades
from tools.sw.menu_v2 import IDEAS, SHIPPED_TILES, bank_from, generate, plated_bank, tiles_of
from tools.sw.program_art import load_module

ROOT = Path(__file__).resolve().parents[3]
PREVIEWS = ROOT / 'wiki/src/sw/menu/previews/v2'
# The costs the design note quotes: bank tiles, authored tiles, added tiles, review frames.
EXPECTED = {'1-boot-splash': (90, 8, 8, 6), '2-sprite-cursor': (84, 2, 2, 4),
            '3-info-footer': (86, 2, 4, 3), '4-moving-background': (86, 4, 4, 3),
            '5-grey-plates': (127, 6, 45, 3), '6-scroll-and-pulse': (86, 2, 4, 6)}


class MenuV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / 'workdir/builds/menu-v2-unit'
        parent.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=parent)
        cls.out = Path(cls.temp.name)
        cls.summary = generate(ROOT, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_authored_banks_are_strict_shade_rows(self):
        for name, (_, sources) in IDEAS.items():
            tiles = 0
            for source in sources:
                data = json.loads((ROOT / 'src/sw/menu/assets/design' / source).read_text())
                validate_shades(data)
                self.assertEqual(data['height'], 8, source)
                self.assertEqual(data['width'] % 8, 0, source)
                tiles += data['width'] // 8
            self.assertEqual(tiles, EXPECTED[name][1], name)

    def test_costs_match_the_design_note(self):
        for name, (tiles, art, added, frames) in EXPECTED.items():
            entry = self.summary[name]
            self.assertEqual((entry['tiles'], entry['authored_tiles'], entry['added_tiles'],
                              entry['frames']), (tiles, art, added, frames), name)
            self.assertEqual(entry['added_bytes'], 16 * added, name)
            self.assertEqual(entry['tiles'], SHIPPED_TILES + added, name)
            self.assertLess(entry['tiles'], 256, name)

    def test_every_idea_keeps_the_plated_list_bank(self):
        """A mockup only adds tiles: the first 82 are the plated list it was drawn over."""
        reference = load_module('menu_reference', ROOT / 'src/dv/menu/reference.py')
        shipped = bank_from(plated_bank(ROOT, reference))
        for name in IDEAS:
            bank = json.loads((self.out / name / 'tile-bank.json').read_text())
            self.assertEqual([row[:8 * SHIPPED_TILES] for row in bank['pixels']],
                             shipped['pixels'], name)

    def test_screens_are_full_game_boy_frames_of_four_shades(self):
        for name in IDEAS:
            frames = sorted(path for path in (self.out / name).glob('*.json')
                            if path.name != 'tile-bank.json')
            self.assertEqual(len(frames), EXPECTED[name][3], name)
            for path in frames:
                data = json.loads(path.read_text())
                self.assertEqual((data['width'], data['height']), (160, 144), path)
                self.assertLessEqual({v for row in data['pixels'] for v in row}, {0, 1, 2, 3})

    def test_every_frame_of_an_idea_differs(self):
        for name in IDEAS:
            frames = {path.read_text() for path in (self.out / name).glob('*.json')
                      if path.name != 'tile-bank.json'}
            self.assertEqual(len(frames), EXPECTED[name][3], name)

    def test_published_svgs_reproduce(self):
        published = sorted(path.name for path in PREVIEWS.glob('*.svg'))
        self.assertEqual(published, sorted(f'{name}-{view}.svg' for name in IDEAS
                                           for view in ('screens', 'new-art')))
        for name in IDEAS:
            for view in ('screens', 'new-art'):
                path = PREVIEWS / f'{name}-{view}.svg'
                self.assertEqual(path.read_text(), (self.out / name / f'{view}.svg').read_text(), path)


if __name__ == '__main__':
    unittest.main()
