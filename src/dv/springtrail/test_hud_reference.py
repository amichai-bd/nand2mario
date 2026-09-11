import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from composition_reference import approved
from hud_reference import CHARS, IDS, column, entering, glyph, hud_tiles, image
from interactions_reference import Game, Player
from tools.sw.columns import decode, validate
from tools.sw.expressions import AssemblyError

ROOT = Path(__file__).resolve().parents[3]

# Fixed terrain anchors name world rows, not decoder/run-length structure.
COLUMNS = {
    0: bytes([0]*14+[11, 11]),
    10: bytes([0]*10+[11, 0, 0, 0, 11, 11]),
    22: bytes(16),
    31: bytes([0]*8+[11, 0, 0, 0, 0, 0, 11, 11]),
    95: bytes([0]*14+[11, 11]),
}
CAMERAS = ((0, 0, None), (0, 7, None), (7, 8, 21), (8, 7, 0),
           (80, 88, 31), (88, 96, 32), (96, 88, 11),
           (255, 256, 52), (256, 255, 31), (607, 608, None),
           (608, 607, 75), (608, 608, None))


class HudReference(unittest.TestCase):
    def test_literal_columns_and_all_encoded_cells(self):
        for index, expected in COLUMNS.items():
            self.assertEqual(column(index), expected)
        actual = validate(ROOT)
        # The world now holds three stages in one256-column page; this file owns
        # stage0's columns, and the progression tests own the other two.
        self.assertEqual(len(actual), 256)
        self.assertEqual(bytes(v for col in actual[:96] for v in col),
                         b''.join(column(i) for i in range(96)))
        self.assertEqual(decode([16, 0, 0]), [0]*16)
        self.assertEqual(decode([14, 0, 2, 11, 0]), list(COLUMNS[0]))
        self.assertEqual(decode([1, 11]*16+[0]), [11]*16)

    def test_ring_boundaries_and_invalid_indices(self):
        for old, new, expected in CAMERAS:
            self.assertEqual(entering(old, new), expected)
        self.assertEqual([entering(a, b) & 31 for a, b in ((80, 88), (88, 96))], [31, 0])
        for index in (-1, 96, True, 0.5):
            with self.assertRaises(ValueError): column(index)
        for cameras in ((-1, 0), (0, 609), (False, 0)):
            with self.assertRaises(ValueError): entering(*cameras)

    def test_malformed_encoded_data(self):
        bad = ([], [0], [16], [16, 0], [16, 0, 0, 0], [17, 0, 0],
               [15, 0, 2, 11, 0], [16, 94, 0], [16, -1, 0],
               [16, True, 0], [1, 0]*17+[0])
        for data in bad:
            with self.subTest(data=data), self.assertRaises(AssemblyError): decode(data)
        original = (ROOT/'src/sw/springtrail/columns.asm').read_text()
        mutations = (original.replace('DW DisplayColumn95', 'DW DisplayColumn96'),
                     original.replace('DisplayColumn0:', 'DisplayColumn1:'),
                     original.replace('DW DisplayColumn95\n', ''))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tree = root/'src/sw/springtrail'
            tree.mkdir(parents=True)
            (tree/'world.asm').write_bytes((ROOT/'src/sw/springtrail/world.asm').read_bytes())
            for text in mutations:
                (tree/'columns.asm').write_text(text)
                with self.assertRaises(AssemblyError): validate(root)

    def test_approved_glyphs_and_hud_tile_layout(self):
        self.assertEqual(''.join(CHARS), '01234ACDEILNOPRSTUWY')
        for mode, word in enumerate(('TITLE', 'PLAY', 'RETRY', 'PAUSED', 'WON')):
            for score in range(5):
                game = replace(Game(), mode=mode, score=score)
                self.assertEqual(hud_tiles(game), bytes(
                    [IDS[c] if c != ' ' else 0 for c in word.ljust(6)]+[74+score]))
        # Glyphs are reconstructed from the source map, including flips; the
        # independent row extraction below also anchors their entire64 pixels.
        source = ROOT/'src/sw/springtrail/assets/core'
        maps = json.loads((source/'core-maps.json').read_text())
        atlas = json.loads((source/'core-tiles.json').read_text())['pixels']
        for char in CHARS:
            pieces = maps['glyph-'+char]['pieces']
            self.assertEqual(len(pieces), 1)
            part = pieces[0]
            self.assertFalse(part.get('x_flip', False) or part.get('y_flip', False))
            self.assertEqual(glyph(char), bytes(atlas[y][part['tile']*8+x]
                                               for y in range(8) for x in range(8)))

    def test_stationary_hud_and_partial_object_clip(self):
        for mode in range(5):
            game = replace(Game(), mode=mode, score=4)
            first = image(game)
            for camera in (0, 248, 256, 608):
                moved = replace(game, player=replace(game.player, camera=camera))
                self.assertEqual(image(moved)[:2560], first[:2560])
            # Row1 is the progression row; only its eight cells carry pixels.
            used = {1, 2, 3, 12, 13, 14, 15, 18}
            for col in range(20):
                cell = b''.join(first[1280+row*160+col*8:1288+row*160+col*8]
                                for row in range(8))
                if col in used:
                    self.assertNotEqual(cell, bytes(64), col)
                else:
                    self.assertEqual(cell, bytes(64), col)
            self.assertEqual(first[:8], bytes(8))
            self.assertEqual(first[18*8:19*8], glyph('4')[:8])
        # A courier starting at y12 crosses both HUD rows. Lower pixels survive
        # at y16; dropping the entire piece would fail this literal pose slice.
        game = replace(Game(), mode=1, player=Player(y=12*16))
        # Row1 now carries the progression cells, so line15 is compared against
        # the same HUD with the courier well clear of it.
        clear = image(replace(Game(), mode=1, player=Player(y=112*16)))
        for facing in (False, True):
            pixels = image(game, facing)
            self.assertEqual(pixels[15*160:16*160], clear[15*160:16*160])
            self.assertEqual(pixels[16*160+20:16*160+36], approved(0, facing)[4*16:5*16])
            self.assertTrue(any(pixels[16*160+20:16*160+36]))


if __name__ == '__main__': unittest.main()
