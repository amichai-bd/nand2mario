"""Host-only checks of the menu frame reference and the fixture library."""
import json
from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture  # noqa: E402
import reference  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
CORE_TILES = ROOT / 'src/sw/springtrail/assets/core/core-tiles.json'
CORE_MAPS = ROOT / 'src/sw/springtrail/assets/core/core-maps.json'
MENU_IMAGE = fixture.game_image(16, 'GAME MENU')


class Font(unittest.TestCase):
    def test_glyphs_are_the_approved_core_font(self):
        core = json.loads(CORE_TILES.read_text(encoding='utf-8'))['pixels']
        maps = json.loads(CORE_MAPS.read_text(encoding='utf-8'))
        names = [f'glyph-{c}' for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'] + ['glyph-dash']
        tiles = reference.font_tiles()
        self.assertEqual(len(tiles), 39)
        for index, name in enumerate(names):
            source = maps[name]['pieces'][0]['tile']
            expected = [core[y][source * 8:source * 8 + 8] for y in range(8)]
            self.assertEqual(tiles[index], expected, name)
        self.assertEqual(tiles[reference.TILE_BLANK], [[0] * 8] * 8)
        self.assertTrue(any(shade == 3 for row in tiles[reference.TILE_ARROW] for shade in row))
        self.assertTrue(all(shade in (0, 3) for row in tiles[reference.TILE_ARROW] for shade in row))

    def test_glyph_mapping(self):
        self.assertEqual([reference.glyph_tile(ord(c)) for c in 'AZ09'], [0, 25, 26, 35])
        self.assertEqual(reference.glyph_tile(ord('-')), reference.TILE_DASH)
        for byte in (0, 0x20):
            self.assertEqual(reference.glyph_tile(byte), reference.TILE_BLANK)
        for byte in (0x21, 0x2F, 0x3A, 0x40, 0x5B, 0x61, 0x7F, 0x80, 0xC0, 0xFF):
            self.assertEqual(reference.glyph_tile(byte), reference.TILE_DASH, byte)

    def test_title_cgb_flag_is_blank_only_in_the_last_cell(self):
        R = reference
        for flag in (0x80, 0xC0):
            tiles = R.title_tiles(b'CGB FLAGGED ROW' + bytes([flag]))
            self.assertEqual(tiles, R.text_tiles('CGB FLAGGED ROW') + [R.TILE_BLANK], flag)
            # The same byte anywhere before the flag position still draws the dash.
            self.assertEqual(R.title_tiles(bytes([flag]) + b'A' * 14 + bytes([flag]))[0], R.TILE_DASH)
            self.assertEqual(R.title_tiles(b'A' * 14 + bytes([flag, flag]))[14], R.TILE_DASH)
        self.assertEqual(R.title_tiles(b'SIXTEEN CHAR ROW'), R.text_tiles('SIXTEEN CHAR ROW'))
        self.assertEqual(R.title_tiles(b'A' * 15 + b'\x81')[15], R.TILE_DASH)
        self.assertEqual(R.title_tiles(b'A' * 15 + b'\x00')[15], R.TILE_BLANK)
        self.assertEqual(R.title_tiles(b'SHORT'), R.text_tiles('SHORT'.ljust(16)))


class Layout(unittest.TestCase):
    def setUp(self):
        self.entries = fixture.entries(MENU_IMAGE)

    def test_fixture_library(self):
        self.assertEqual([row['valid'] for row in self.entries], [1, 1, 1, 0, 1, 1, 1, 1, 1] + [0] * 6 + [1, 1])
        self.assertGreaterEqual(sum(row['valid'] for row in self.entries[:16]), 6)
        self.assertEqual(self.entries[0]['title'], b'SPRINGTRAIL'.ljust(16, b'\0'))
        self.assertEqual(self.entries[6]['title'], b'CGB FLAGGED ROW\x80')
        self.assertEqual(self.entries[7]['title'], b'SIXTEEN CHAR ROW')
        self.assertEqual(self.entries[8]['title'], b'CGB ONLY TITLE\x00\xC0')
        self.assertEqual(self.entries[15]['title'], b'LAST SLOT'.ljust(16, b'\0'))
        self.assertEqual(len(set(row['title'] for row in self.entries if row['valid'])), 10)
        # The stub image carries the flag at header 0x143, as a CGB-flagged homebrew does.
        self.assertEqual(fixture.game_image(6, fixture.GAMES[6])[0x143], 0x80)
        self.assertEqual(self.entries[fixture.SHORT_SLOT]['length'], 16384)
        self.assertEqual(self.entries[16]['profile'], fixture.PROFILE_LOADER)
        library = fixture.library_bytes(MENU_IMAGE)
        self.assertEqual(len(library), fixture.LIBRARY_BYTES)
        self.assertEqual(library[16 * 32768:17 * 32768], MENU_IMAGE)
        entry = library[fixture.CATALOGUE_ADDRESS:fixture.CATALOGUE_ADDRESS + 32]
        valid, profile, length, crc32, title = struct.Struct('<BBHI16s8x').unpack(entry)
        self.assertEqual((valid, profile, length, crc32), (1, 1, 32768, zlib.crc32(fixture.game_image(0, 'SPRINGTRAIL'))))
        self.assertEqual(title, self.entries[0]['title'])
        with self.assertRaises(ValueError):
            fixture.library_bytes(b'short')

    def test_tilemap_rows(self):
        rows = reference.tilemap(self.entries)
        self.assertEqual(rows[0][4:16], reference.text_tiles('GAME LIBRARY'))
        self.assertEqual(rows[1][0], reference.TILE_ARROW)
        self.assertEqual(rows[1][1:3], reference.text_tiles('00'))
        self.assertEqual(rows[1][4:20], reference.text_tiles('SPRINGTRAIL     '))
        self.assertEqual(rows[4][4:20], [reference.TILE_BLANK] * 16)
        self.assertEqual(rows[5][4:20], reference.text_tiles('SHORT IMAGE     '))
        self.assertEqual(rows[7][4:20], reference.text_tiles('CGB FLAGGED ROW '))
        self.assertEqual(rows[8][4:20], reference.text_tiles('SIXTEEN CHAR ROW'))
        self.assertEqual(rows[9][4:20], reference.text_tiles('CGB ONLY TITLE  '))
        self.assertEqual(rows[10][4:20], [reference.TILE_BLANK] * 16)
        self.assertEqual(rows[16][1:3], reference.text_tiles('15'))
        self.assertEqual(rows[16][4:20], reference.text_tiles('LAST SLOT       '))
        self.assertEqual(rows[17], [reference.TILE_BLANK] * 20)
        # The menu entry itself is never listed.
        self.assertFalse(any(reference.text_tiles('GAME MENU') == row[4:13] for row in rows))
        moved = reference.tilemap(self.entries, cursor=15)
        self.assertEqual(moved[1][0], reference.TILE_BLANK)
        self.assertEqual(moved[16][0], reference.TILE_ARROW)
        with self.assertRaises(ValueError):
            reference.tilemap(self.entries, cursor=16)
        partial = reference.tilemap(self.entries, drawn_slots=1)
        self.assertEqual(partial[2][4:20], [reference.TILE_BLANK] * 16)

    def test_status_row(self):
        R = reference
        self.assertEqual(R.status_text(), ' ' * 20)
        self.assertEqual(R.status_text(R.RESULT_OK, 2), ' ' * 20)
        self.assertEqual(R.status_text(R.RESULT_INVALID_SLOT, 3), 'SLOT 03 INVALID     ')
        self.assertEqual(R.status_text(R.RESULT_CRC_MISMATCH, 9), 'SLOT 09 BAD CRC     ')
        self.assertEqual(R.status_text(R.RESULT_NOT_READY, 0), 'SLOT 00 NOT READY   ')
        self.assertEqual(R.status_text(7, 16), 'SLOT 16 ERROR       ')
        self.assertEqual(R.status_text(R.RESULT_INVALID_SLOT, 255), 'SLOT -- INVALID     ')
        self.assertEqual(R.status_text(sdram_ready=False), 'NOT READY           ')

    def test_frames_and_snapshot_check(self):
        frames = fixture.scenario_frames(MENU_IMAGE)
        self.assertEqual(len(frames), len(fixture.SCENARIO))
        self.assertEqual(len(set(frames)), len(frames))
        for pixels in frames:
            self.assertEqual(len(pixels), 23040)
            self.assertTrue(set(pixels) <= {0, 3})
        packed = bytes(sum(frames[0][i + k] << (2 * k) for k in range(4)) for i in range(0, 23040, 4))
        self.assertEqual(reference.check_pixels(packed, self.entries), 23040)
        self.assertEqual(reference.unpack(packed), reference.expected('menu', self.entries))
        self.assertEqual(reference.expected('cursor-2', self.entries), frames[2])
        broken = bytearray(packed)
        broken[(9 * 160 + 40) // 4] ^= 3
        with self.assertRaisesRegex(AssertionError, 'MENU_PIXEL x=40 y=9'):
            reference.check_pixels(bytes(broken), self.entries)
        with self.assertRaises(ValueError):
            reference.check_pixels(packed[:-1], self.entries)
        with self.assertRaises(ValueError):
            reference.expected('title', self.entries)

    def test_hex_lines(self):
        self.assertEqual(fixture.hex_lines(b'\x00\xff\x10'), '00\nff\n10\n')


if __name__ == '__main__':
    unittest.main()
