import unittest
from pathlib import Path
from reference import Game, cells
from screen import decode, image, tile


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
        source = (Path(__file__).resolve().parents[3]/'src/sw/stackdrop/tables.asm').read_text()
        shape_source, art_source = source.split('Shapes:\n')[1].split('Tiles:\n')
        actual = bytes(int(s.strip()[1:], 16) for line in shape_source.strip().splitlines() for s in line[3:].split(','))
        for piece in range(7):
            for rotation in range(4):
                offset = piece*16+rotation*4
                self.assertEqual(set(actual[offset:offset+4]), {16*y+x for x, y in cells(piece, rotation)})
        art_source = art_source.split('Map:\n')[0]
        art = bytes(int(s.strip()[1:], 16) for line in art_source.strip().splitlines() for s in line[3:].split(','))
        for number in range(20):
            decoded = bytes(((art[number*16+y*2] >> (7-x)) & 1) | (((art[number*16+y*2+1] >> (7-x)) & 1) << 1) for y in range(8) for x in range(8))
            self.assertEqual(decoded, tile(number))


if __name__ == '__main__':
    unittest.main()
