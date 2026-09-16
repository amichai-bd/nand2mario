import json
import unittest
from pathlib import Path
from reference import Game, cells
import zlib
from screen import TILES, TITLE_IMAGE, TITLE_SCROLL, background, decode, image, pack, page, tile, title, unpack

FIXTURES = Path(__file__).resolve().parent/'fixtures'


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

    def test_title_is_one_static_frozen_image(self):
        self.assertEqual(image(Game()), TITLE_IMAGE)
        self.assertEqual(decode(TITLE_IMAGE), dict(status=0, rotation=0, board=[0]*96, active=[], next_piece=0, score=0))
        packed = bytes.fromhex((FIXTURES/'title-frame.txt').read_text().replace('\n', ''))
        metadata = json.loads((FIXTURES/'title.json').read_text())
        self.assertEqual((len(packed), unpack(packed), pack(TITLE_IMAGE)), (5760, TITLE_IMAGE, packed))
        self.assertEqual(metadata['crc32'], f'{zlib.crc32(TITLE_IMAGE):08x}')
        self.assertEqual(metadata['sha256'], __import__('hashlib').sha256(packed).hexdigest())
        self.assertEqual((metadata['scx'], metadata['scy']), TITLE_SCROLL)
        # A play-page frame carrying the retired T status tile is neither state.
        pixels = bytearray(image(Game(status=1)))
        pixels[120*160+120:120*160+128] = tile(4)[:8]
        for line in range(1, 8):
            pixels[(120+line)*160+120:(120+line)*160+128] = tile(4)[8*line:8*line+8]
        with self.assertRaisesRegex(ValueError, 'STACKDROP_TILE x=120 y=120'):
            decode(pixels)
        changed = bytearray(TITLE_IMAGE)
        changed[40*160+20] ^= 1
        with self.assertRaisesRegex(ValueError, 'STACKDROP_TILE'):
            decode(changed)

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
        self.assertEqual(rows, page())
        self.assertEqual([row[:20] for row in rows[:18]], background())
        scx, scy = TITLE_SCROLL
        self.assertEqual([[rows[(scy//8+r) % 32][(scx//8+c) % 32] for c in range(20)] for r in range(18)], title())
        # Every other cell is blank, so the two pages never show each other.
        shown = {((scy//8+r) % 32, (scx//8+c) % 32) for r in range(18) for c in range(20)}
        shown |= {(r, c) for r in range(18) for c in range(20)}
        self.assertEqual({rows[r][c] for r in range(32) for c in range(32) if (r, c) not in shown}, {0})


if __name__ == '__main__':
    unittest.main()
