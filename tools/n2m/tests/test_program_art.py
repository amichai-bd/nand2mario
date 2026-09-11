"""Program previews come from the built ROMs and reproduce the committed SVGs exactly."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.sw.assets import encode_shades
from tools.sw.program_art import PLAY_SCRIPT, build, decode_tiles, generate, stackdrop_prepare
from stackdrop_support import Game, cases, image, reference, screen

ROOT = Path(__file__).resolve().parents[3]
PREVIEWS = {'stackdrop': ROOT / 'wiki/src/sw/stackdrop/previews', 'v05': ROOT / 'wiki/src/dv/v05/previews'}


class ProgramArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / 'workdir/builds/program-art-unit'
        parent.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=parent)
        cls.out = Path(cls.temp.name)
        generate(ROOT, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def frame(self, program, name):
        data = json.loads((self.out / program / f'{name}.json').read_text())
        self.assertEqual((data['width'], data['height']), (160, 144))
        return bytes(v for row in data['pixels'] for v in row)

    def test_stackdrop_bank_is_the_rom_tile_table(self):
        rom, symbols, _ = build(ROOT, 'stackdrop')
        bank = json.loads((self.out / 'stackdrop/tile-bank.json').read_text())
        self.assertEqual(encode_shades(bank), rom[symbols['Tiles']:symbols['Tiles'] + 320])
        self.assertEqual(decode_tiles(encode_shades(bank)), bank)

    def test_stackdrop_frames_match_the_independent_oracle(self):
        rom, symbols, _ = build(ROOT, 'stackdrop')
        shapes = rom[symbols['Shapes']:symbols['Shapes'] + 112]
        play = Game()
        for buttons in PLAY_SCRIPT:
            play.update(buttons)
        for name, game in (('title', Game()), ('play', play)):
            with patch.dict(sys.modules, {'cases': cases, 'reference': reference}):
                self.assertEqual(bytes(stackdrop_prepare(shapes, game)), cases.buffer(game), name)
            self.assertEqual(self.frame('stackdrop', name), image(game), name)
        self.assertEqual(screen.decode(self.frame('stackdrop', 'title'))['status'], 0)
        self.assertEqual(screen.decode(self.frame('stackdrop', 'play'))['status'], 1)

    def test_v05_frames_match_the_literal_image(self):
        for name, mask in (('idle', 0), ('right-a', 0x11), ('all-buttons', 0xFF)):
            pixels = self.frame('v05', name)
            for y in range(144):
                for x in range(160):
                    expected = int(x < 8 and y < 8 or 64 <= y < 72 and x < 64 and mask >> (x // 8) & 1)
                    self.assertEqual(pixels[y * 160 + x], expected, (name, x, y))

    def test_committed_svgs_reproduce(self):
        for program, folder in PREVIEWS.items():
            references = sorted(folder.glob('*.svg'))
            self.assertEqual(len(references), 4, program)
            for reference in references:
                self.assertEqual(reference.read_text(), (self.out / program / reference.name).read_text(), reference)


if __name__ == '__main__':
    unittest.main()
