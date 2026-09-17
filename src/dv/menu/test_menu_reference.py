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
        self.assertEqual([row['valid'] for row in self.entries], [1, 1, 1, 0, 1, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1])
        self.assertGreaterEqual(sum(row['valid'] for row in self.entries[:16]), 6)
        # The 64 KiB MBC1 stub: one entry at slot 5 with its profile and length, slot 6 empty, its
        # two halves at slots 5 and 6, MBC1 header bytes and the bank-2 exit code.
        banked = fixture.mbc1_image()
        self.assertEqual(len(banked), 65536)
        self.assertEqual((self.entries[5]['profile'], self.entries[5]['length'], self.entries[5]['crc32']),
                         (fixture.PROFILE_MBC1, 65536, zlib.crc32(banked)))
        self.assertEqual(self.entries[5]['title'], b'BANKED GAME'.ljust(16, b'\0'))
        self.assertEqual(self.entries[6]['valid'], 0)
        self.assertEqual(fixture.image_bytes(5, MENU_IMAGE) + fixture.image_bytes(6, MENU_IMAGE), banked)
        self.assertEqual((banked[0x147], banked[0x148]), (1, 1))
        self.assertEqual(banked[0x8000:0x8002], bytes([0x3E, fixture.GAME_EXIT_VALUE]))
        self.assertEqual(self.entries[0]['title'], b'SPRINGTRAIL'.ljust(16, b'\0'))
        # Slot 1 is the exit demo: the stub stands in for the built image with the same title.
        self.assertEqual(self.entries[1]['title'], b'EXIT DEMO'.ljust(16, b'\0'))
        self.assertEqual(self.entries[1]['crc32'], zlib.crc32(fixture.exit_stub()))
        real = bytearray(fixture.exit_stub())
        real[0x150] ^= 0xFF
        self.assertEqual(fixture.entries(MENU_IMAGE, bytes(real))[1]['crc32'], zlib.crc32(real))
        self.assertEqual(fixture.library_bytes(MENU_IMAGE, bytes(real))[32768:65536], real)
        with self.assertRaises(ValueError):
            fixture.library_bytes(MENU_IMAGE, fixture.game_image(1, 'OTHER TITLE'))
        self.assertEqual(self.entries[10]['title'], b'CGB FLAGGED ROW\x80')
        self.assertEqual(self.entries[7]['title'], b'SIXTEEN CHAR ROW')
        self.assertEqual(self.entries[8]['title'], b'CGB ONLY TITLE\x00\xC0')
        self.assertEqual(self.entries[15]['title'], b'LAST SLOT'.ljust(16, b'\0'))
        self.assertEqual(len(set(row['title'] for row in self.entries if row['valid'])), 11)
        # The stub image carries the flag at header 0x143, as a CGB-flagged homebrew does.
        self.assertEqual(fixture.game_image(10, fixture.GAMES[10])[0x143], 0x80)
        self.assertEqual(self.entries[fixture.SHORT_SLOT]['length'], 16384)
        self.assertEqual(self.entries[16]['profile'], fixture.PROFILE_LOADER)
        library = fixture.library_bytes(MENU_IMAGE)
        self.assertEqual(len(library), fixture.LIBRARY_BYTES)
        self.assertEqual(library[16 * 32768:17 * 32768], MENU_IMAGE)
        entry = library[fixture.CATALOGUE_ADDRESS:fixture.CATALOGUE_ADDRESS + 32]
        valid, profile, length, crc32, title = struct.Struct('<BBHI16s8x').unpack(entry)
        self.assertEqual((valid, profile, length, crc32), (1, 1, 32768, zlib.crc32(fixture.game_image(0, 'SPRINGTRAIL'))))
        self.assertEqual(title, self.entries[0]['title'])
        # The 64 KiB entry keeps the 16-bit length word at 0 and carries bit 16 in byte 24; slot 6's entry is empty.
        entry = library[fixture.CATALOGUE_ADDRESS + 5 * 32:fixture.CATALOGUE_ADDRESS + 6 * 32]
        self.assertEqual((entry[0], entry[1], entry[2:4], entry[24], entry[25:]), (1, 3, bytes(2), 1, bytes(7)))
        self.assertEqual(library[fixture.CATALOGUE_ADDRESS + 6 * 32:fixture.CATALOGUE_ADDRESS + 7 * 32], bytes(32))
        self.assertEqual(library[5 * 32768:7 * 32768], banked)
        with self.assertRaises(ValueError):
            fixture.library_bytes(b'short')

    def test_tilemap_rows(self):
        rows = reference.tilemap(self.entries)
        inverse = reference.TILE_INVERSE
        # The header is an inverse plate between the two caps.
        self.assertEqual((rows[0][0], rows[0][19]), (reference.TILE_PLATE_LEFT, reference.TILE_PLATE_RIGHT))
        self.assertEqual(rows[0][4:16], [inverse + tile for tile in reference.text_tiles('GAME LIBRARY')])
        self.assertEqual(rows[0][1:4], [inverse + reference.TILE_BLANK] * 3)
        # The selected slot is a full-width inverse bar carrying the arrow.
        self.assertEqual(rows[1][0], inverse + reference.TILE_ARROW)
        self.assertEqual(rows[1][1:3], [inverse + tile for tile in reference.text_tiles('00')])
        self.assertEqual(rows[1][4:20], [inverse + tile for tile in reference.text_tiles('SPRINGTRAIL     ')])
        self.assertEqual(rows[4][4:20], [reference.TILE_BLANK] * 16)
        self.assertEqual(rows[5][4:20], reference.text_tiles('SHORT IMAGE     '))
        # The 64 KiB entry is listed once: slot 5 carries its title, slot 6 (its upper half) is blank.
        self.assertEqual(rows[6][4:20], reference.text_tiles('BANKED GAME     '))
        self.assertEqual(rows[7][1:3], reference.text_tiles('06'))
        self.assertEqual(rows[7][4:20], [reference.TILE_BLANK] * 16)
        self.assertEqual(rows[8][4:20], reference.text_tiles('SIXTEEN CHAR ROW'))
        self.assertEqual(rows[9][4:20], reference.text_tiles('CGB ONLY TITLE  '))
        self.assertEqual(rows[10][4:20], reference.text_tiles('ABC-123 XYZ 789 '))
        self.assertEqual(rows[11][4:20], reference.text_tiles('CGB FLAGGED ROW '))
        self.assertEqual(rows[12][4:20], [reference.TILE_BLANK] * 16)
        self.assertEqual(rows[16][1:3], reference.text_tiles('15'))
        self.assertEqual(rows[16][4:20], reference.text_tiles('LAST SLOT       '))
        # A blank status row is still a plate: two caps and 18 inverse blanks.
        self.assertEqual(rows[17], [reference.TILE_PLATE_LEFT]
                         + [reference.TILE_INVERSE + reference.TILE_BLANK] * 18
                         + [reference.TILE_PLATE_RIGHT])
        # The menu entry itself is never listed.
        self.assertFalse(any(reference.text_tiles('GAME MENU') == row[4:13] for row in rows))
        moved = reference.tilemap(self.entries, cursor=15)
        self.assertEqual(moved[1][0], reference.TILE_BLANK)
        self.assertEqual(moved[1][1:3], reference.text_tiles('00'))
        self.assertEqual(moved[16][0], reference.TILE_INVERSE + reference.TILE_ARROW)
        with self.assertRaises(ValueError):
            reference.tilemap(self.entries, cursor=16)
        partial = reference.tilemap(self.entries, drawn_slots=1)
        self.assertEqual(partial[2][4:20], [reference.TILE_BLANK] * 16)

    def test_nudge_phase_moves_only_the_arrow_cell(self):
        plain = reference.tilemap(self.entries, cursor=2)
        nudged = reference.tilemap(self.entries, cursor=2, phase=1)
        self.assertEqual(plain[3][0], reference.TILE_INVERSE + reference.TILE_ARROW)
        self.assertEqual(nudged[3][0], reference.TILE_NUDGE_INVERSE)
        for row, (before, after) in enumerate(zip(plain, nudged)):
            self.assertEqual(before[1:], after[1:], row)
            if row != 3:
                self.assertEqual(before, after, row)
        with self.assertRaises(ValueError):
            reference.tilemap(self.entries, phase=2)
        # The phase follows from the frame number alone: 16 frames a hold.
        self.assertEqual([reference.phase_of_frame(n) for n in (0, 15, 16, 31, 32, 47, 48)],
                         [0, 0, 1, 1, 0, 0, 1])
        with self.assertRaises(ValueError):
            reference.phase_of_frame(-1)
        # The nudged arrow is the authored tile shifted one pixel, not a new shape.
        bank = reference.bank_tiles()
        self.assertEqual(bank[reference.TILE_NUDGE_INVERSE], reference.invert(bank[reference.TILE_NUDGE]))
        self.assertEqual(len(bank), reference.BANK_TILES)
        for tile in range(reference.FONT_TILES):
            self.assertEqual(bank[reference.TILE_INVERSE + tile], reference.invert(bank[tile]), tile)

    def test_reference_frames_match_the_chosen_design_preview(self):
        """The implemented layout is direction A as published, cell for cell."""
        sys.path.insert(0, str(ROOT))
        from tools.sw.menu_art import direction_a, entries as sample, STATES
        _bank, _names, cells, bgp = direction_a(ROOT, reference)
        self.assertEqual(bgp, 0xE4)
        for state, options in STATES:
            self.assertEqual(reference.tilemap(sample(), **options), cells(**options), state)

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
        self.assertEqual(len(frames), len(fixture.SCENARIO) + 2)
        self.assertEqual(len(set(frames)), len(frames))
        for pixels in frames:
            self.assertEqual(len(pixels), 23040)
            self.assertTrue(set(pixels) <= {0, 3})
        # The exit-demo game frame: shade 3 exactly on pixel rows 64..71.
        game = frames[fixture.GAME_FRAME]
        self.assertEqual(game, fixture.exit_frame())
        self.assertEqual({y for y in range(144) if game[y * 160]}, set(range(64, 72)))
        self.assertEqual(game.count(3), 8 * 160)
        self.assertEqual(reference.unpack(fixture.pack(game)), game)
        packed = fixture.pack(frames[0])
        self.assertEqual(reference.check_pixels(packed, self.entries), 23040)
        self.assertEqual(reference.unpack(packed), reference.expected('menu', self.entries))
        self.assertEqual(reference.expected('cursor-2', self.entries), frames[2])
        self.assertEqual(reference.expected('phase-1', self.entries), frames[fixture.PHASE_FRAME])
        self.assertEqual(reference.expected('phase-0', self.entries), frames[0])
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
