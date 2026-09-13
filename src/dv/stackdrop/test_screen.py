import json
import unittest
from pathlib import Path
from reference import Game, cells
from screen import TILES, background, decode, image, tile


class Screen(unittest.TestCase):
    def test_all_pieces_and_digits(self):
        for piece in range(7):
            for rotation in range(4):
                game = Game(status=1, piece=piece, rotation=rotation, x=1, y=3, score=9876)
                result = decode(image(game))
                self.assertEqual(result['active'], sorted([(1+x, 3+y) for x, y in cells(piece, rotation)], key=lambda p: (p[1], p[0])))
                self.assertEqual((result['rotation'], result['next_piece'], result['score']), (rotation, (piece+1) % 7, 9876))
        for status in (0, 2):
            self.assertEqual(decode(image(Game(status=status)))['status'], status)

    def test_reject_changed_tile(self):
        pixels = bytearray(image(Game(status=1)))
        pixels[26*160+50] = 1
        with self.assertRaisesRegex(ValueError, 'STACKDROP_TILE'):
            decode(pixels)
        with self.assertRaisesRegex(ValueError, 'STACKDROP_SCREEN_SIZE'):
            decode(pixels[:-1])

    def test_literal_rom_tables(self):
        root = Path(__file__).resolve().parents[3]
        source = (root/'src/sw/stackdrop/tables.asm').read_text()
        shape_source = source.split('Shapes:\n')[1].split('Tiles:\n')[0]
        actual = bytes(int(s.strip()[1:], 16) for line in shape_source.strip().splitlines() for s in line[3:].split(','))
        for piece in range(7):
            for rotation in range(4):
                offset = piece*16+rotation*4
                self.assertEqual(set(actual[offset:offset+4]), {16*y+x for x, y in cells(piece, rotation)})
        art = json.loads((root/'src/sw/stackdrop/assets/tiles.json').read_text())
        self.assertEqual((art['width'], art['height']), (8*TILES, 8))
        for number in range(TILES):
            drawn = bytes(v for row in art['pixels'] for v in row[number*8:number*8+8])
            self.assertEqual(drawn, tile(number))

    def test_literal_rom_map(self):
        source = (Path(__file__).resolve().parents[3]/'src/sw/stackdrop/tables.asm').read_text()
        rows = [[int(v) for v in line[3:].split(',')]
                for line in source.split('Map:\n')[1].strip().splitlines()]
        self.assertEqual((len(rows), {len(row) for row in rows}), (32, {32}))
        self.assertEqual([row[:20] for row in rows[:18]], background())
        self.assertEqual({v for row in rows for v in row[20:]} | {v for row in rows[18:] for v in row}, {0})


if __name__ == '__main__':
    unittest.main()
