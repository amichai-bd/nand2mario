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
        grey = reference.TILE_GREY
        # The header is a grey plate: two caps, the 3-to-2 gradient and grey text.
        self.assertEqual((rows[0][0], rows[0][19]), (reference.TILE_CAP_LEFT, reference.TILE_CAP_RIGHT))
        self.assertEqual(rows[0][4:16], [grey + tile for tile in reference.text_tiles('GAME LIBRARY')])
        self.assertEqual(rows[0][1:4], [reference.TILE_FADE32] * 3)
        # Every slot row is plain: the cursor is an object, so no row is re-banked.
        self.assertEqual(rows[1][0], reference.TILE_BLANK)
        self.assertEqual(rows[1][1:3], reference.text_tiles('00'))
        self.assertEqual(rows[1][4:20], reference.text_tiles('SPRINGTRAIL     '))
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
        # A blank bottom plate is the gradient fill alone between the two caps.
        self.assertEqual(rows[17], [reference.TILE_CAP_LEFT] + [reference.TILE_FADE21] * 18
                         + [reference.TILE_CAP_RIGHT])
        # A message sits on the plate, biased left, with the fill either side of it.
        message = reference.tilemap(self.entries, result=reference.RESULT_INVALID_SLOT, index=3)[17]
        self.assertEqual(message[1], reference.TILE_FADE21)
        self.assertEqual(message[2:17], [grey + tile for tile in reference.text_tiles('SLOT 03 INVALID')])
        self.assertEqual(message[17:19], [reference.TILE_FADE21] * 2)
        # The menu entry itself is never listed.
        self.assertFalse(any(reference.text_tiles('GAME MENU') == row[4:13] for row in rows))
        # The cursor never reaches the map: every slot draws the same cells.
        self.assertEqual(reference.tilemap(self.entries, cursor=15), rows)
        with self.assertRaises(ValueError):
            reference.tilemap(self.entries, cursor=16)
        partial = reference.tilemap(self.entries, drawn_slots=1)
        self.assertEqual(partial[2][4:20], [reference.TILE_BLANK] * 16)

    def test_the_cursor_is_an_object_and_the_phase_is_its_tile(self):
        # Neither the slot nor the phase changes a map cell.
        for state in (dict(cursor=2), dict(cursor=2, phase=1), dict(phase=1)):
            self.assertEqual(reference.tilemap(self.entries, **state),
                             reference.tilemap(self.entries), state)
        self.assertEqual(reference.objects(), [(0, 8, reference.TILE_POINTER)])
        self.assertEqual(reference.objects(cursor=5, phase=1), [(0, 48, reference.TILE_POINTER + 1)])
        self.assertEqual(reference.objects(cursor=15), [(0, 128, reference.TILE_POINTER)])
        for bad in (dict(cursor=16), dict(phase=2)):
            with self.assertRaises(ValueError):
                reference.objects(**bad)
            with self.assertRaises(ValueError):
                reference.tilemap(self.entries, **bad)
        # The phase follows from the frame number alone: 16 frames a hold.
        self.assertEqual([reference.phase_of_frame(n) for n in (0, 15, 16, 31, 32, 47, 48)],
                         [0, 0, 1, 1, 0, 0, 1])
        with self.assertRaises(ValueError):
            reference.phase_of_frame(-1)
        bank = reference.bank_tiles()
        self.assertEqual(len(bank), reference.BANK_TILES)
        # The two pointer phases are the committed art, the same arrow one pixel apart.
        art = reference.atlas_tiles(reference.POINTER_ART, reference.POINTER_TILES)
        self.assertEqual(bank[reference.TILE_POINTER:reference.TILE_POINTER + reference.POINTER_TILES], art)
        self.assertEqual(art[1], [[0] + row[:7] for row in art[0]])
        self.assertTrue(all(row[0] == 0 for row in art[1]))
        # The grey bank is the font on a mid-grey page: shade 0 becomes 2, the ink stays.
        for tile in range(reference.FONT_TILES):
            self.assertEqual(bank[reference.TILE_GREY + tile], reference.greyed(bank[tile]), tile)
            self.assertLessEqual({shade for row in bank[tile] for shade in row}, {0, 3}, tile)
        self.assertEqual(bank[reference.TILE_GREY + reference.TILE_BLANK], [[2] * 8] * 8)
        # The splash badge is the committed art, four cells by two above the list's bank.
        self.assertEqual(bank[reference.TILE_BADGE:],
                         reference.atlas_tiles(reference.SPLASH_ART, reference.BADGE_TILES))

    def test_plates_match_the_published_grey_preview(self):
        """The header and bottom plates are the published mid-grey design, pixel for pixel."""
        sys.path.insert(0, str(ROOT))
        from tools.sw.menu_v2 import grey
        published = dict(grey(ROOT, reference)[2])
        plate_rows = list(range(8)) + list(range(136, 144))
        for label, state in (('GREY PLATES', {}),
                             ('REFUSED', dict(result=reference.RESULT_INVALID_SLOT, index=3))):
            pixels = published[label]['pixels']
            frame = reference.frame(self.entries, **state)
            for y in plate_rows:
                self.assertEqual(list(frame[y * 160:(y + 1) * 160]), pixels[y], (label, y))

    def test_the_boot_splash_layout_and_schedule(self):
        """The 32-row map, the fade through BGP and the slide, all from the frame number."""
        splash = reference.splash_rows()
        self.assertEqual(len(splash), reference.ROWS)
        badge = [reference.TILE_BADGE + cell for cell in range(reference.BADGE_TILES)]
        self.assertEqual(splash[reference.BADGE_ROW][reference.BADGE_COLUMN:
                                                     reference.BADGE_COLUMN + reference.BADGE_COLUMNS],
                         badge[:reference.BADGE_COLUMNS])
        self.assertEqual(splash[reference.BADGE_ROW + 1][reference.BADGE_COLUMN:
                                                         reference.BADGE_COLUMN + reference.BADGE_COLUMNS],
                         badge[reference.BADGE_COLUMNS:])
        for row, column, text in ((reference.SPLASH_TITLE_ROW, reference.SPLASH_TITLE_COLUMN, reference.SPLASH_TITLE),
                                  (reference.SPLASH_HINT_ROW, reference.SPLASH_HINT_COLUMN, reference.SPLASH_HINT)):
            self.assertEqual(splash[row][column:column + len(text)], reference.text_tiles(text))
        # The map is the splash above the list, with the list's last rows wrapped
        # over the splash's own top rows.
        listing = reference.list_rows(self.entries)
        drawn = reference.background_map(self.entries)
        undrawn = reference.background_map(self.entries, wrapped=0)
        self.assertEqual(len(drawn), reference.MAP_ROWS)
        self.assertEqual(undrawn[:reference.ROWS], splash)
        self.assertEqual(drawn[:reference.WRAPPED_ROWS], listing[reference.ROWS - reference.WRAPPED_ROWS:])
        self.assertEqual(drawn[reference.LIST_MAP_ROW:], listing[:reference.MAP_ROWS - reference.LIST_MAP_ROW])
        # The settled view is the list alone, so every menu frame is unchanged.
        self.assertEqual(reference.tilemap(self.entries), listing)
        with self.assertRaises(ValueError):
            reference.tilemap(self.entries, scy=4)
        with self.assertRaises(ValueError):
            reference.background_map(self.entries, wrapped=reference.WRAPPED_ROWS + 1)
        # The schedule: every fade step in order, then the slide, from the frame
        # number alone. No frame number is named here that the constants do not give.
        steps = [reference.splash_state(frame * reference.FADE_HOLD)[0] for frame in range(len(reference.FADE))]
        self.assertEqual(steps, list(reference.FADE))
        for number in range(reference.FADE_FRAMES):
            self.assertEqual(reference.splash_state(number), (reference.FADE[number // reference.FADE_HOLD], 0, 0))
        for step in range(1, reference.SLIDE_FRAMES + 1):
            palette, scy, wrapped = reference.splash_state(reference.FADE_FRAMES + step - 1)
            self.assertEqual((palette, scy), (reference.FADE[-1], reference.SLIDE_STEP * step))
            self.assertEqual(wrapped, min(step, reference.WRAPPED_ROWS))
        # Each wrapped row is drawn on the slide frame that first counts it, after
        # its splash row has left the top of the screen and before the list row it
        # carries reaches the bottom.
        for row in range(reference.WRAPPED_ROWS):
            drawing = next(number for number in range(reference.SETTLED_FRAME + 1)
                           if reference.splash_state(number)[2] == row + 1)
            top = reference.splash_state(drawing)[1] // 8
            self.assertGreater(top, row)
            self.assertLessEqual(top + reference.ROWS, reference.MAP_ROWS + row)
        self.assertEqual(reference.splash_state(reference.SETTLED_FRAME)[1], reference.SETTLED_SCY)
        # A press skips in at most two frames, each of them a frame of the
        # schedule, the last settled, and no frame draws more than SKIP_ROWS.
        for number in range(reference.SETTLED_FRAME + 1):
            shown = reference.skip_schedule(number)
            self.assertLessEqual(len(shown), 2, number)
            self.assertEqual(shown[-1], reference.SETTLED_FRAME, number)
            drawn = reference.splash_state(number)[2]
            for frame in shown:
                rows = reference.splash_state(frame)[2]
                self.assertLessEqual(rows - drawn, reference.SKIP_ROWS, number)
                drawn = rows
            self.assertEqual(drawn, reference.WRAPPED_ROWS, number)
        with self.assertRaises(ValueError):
            reference.splash_state(-1)
        # The splash is the cold boot's alone: the catalogue must list at boot
        # and no selection can have happened since reset.
        self.assertTrue(reference.splash_at_boot())
        self.assertFalse(reference.splash_at_boot(sdram_ready=False))
        for index in (0, 1, 3, reference.SLOTS, 16):
            self.assertFalse(reference.splash_at_boot(index), index)
        self.assertTrue(reference.splash_at_boot(reference.NO_INDEX))
        # The first frame is the page alone and the last is the menu itself.
        self.assertEqual(set(reference.expected('splash-0', self.entries)), {0})
        self.assertEqual(reference.expected(f'splash-{reference.SETTLED_FRAME}', self.entries),
                         reference.frame(self.entries))
        self.assertNotEqual(reference.expected(f'splash-{reference.SETTLED_FRAME - 1}', self.entries),
                            reference.frame(self.entries))
        # The fade is a palette, not a redraw: every shade maps through BGP.
        cells = reference.tilemap(self.entries, scy=0, wrapped=0)
        bank = reference.bank_tiles()
        for number in range(reference.FADE_FRAMES):
            palette, scy, wrapped = reference.splash_state(number)
            pixels = reference.frame(self.entries, bgp=palette, scy=scy, wrapped=wrapped)
            for y in (0, 37, 84, 143):
                for x in (0, 67, 159):
                    shade = bank[cells[y // 8][x // 8]][y % 8][x % 8]
                    self.assertEqual(pixels[y * reference.WIDTH + x], (palette >> (2 * shade)) & 3, (number, x, y))
        # The cursor object rides no scroll, so it waits for the settled view.
        self.assertEqual(reference.objects(scy=0), [])
        self.assertEqual(reference.objects(scy=reference.SETTLED_SCY), reference.objects())

    def test_the_pointer_draws_over_the_page_and_keeps_shade_0_clear(self):
        frame = reference.frame(self.entries, cursor=4)
        plain = reference.frame(self.entries, cursor=4, phase=1)
        bank = reference.bank_tiles()
        top = 8 * (reference.SLOT_ROW + 4)
        # Column 0 of a slot row is the blank page, so a transparent pointer pixel
        # leaves shade 0 there and an opaque one draws its own shade.
        for y in range(8):
            for x in range(8):
                self.assertEqual(frame[(top + y) * 160 + x], bank[reference.TILE_POINTER][y][x], (x, y))
        self.assertTrue(any(bank[reference.TILE_POINTER][y][x] == 0 for y in range(8) for x in range(8)))
        # A phase change moves nothing outside the pointer's own eight rows.
        differing = {position // 160 for position in range(23040) if frame[position] != plain[position]}
        self.assertTrue(differing)
        self.assertLessEqual(differing, set(range(top, top + 8)))

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
            self.assertLessEqual(set(pixels), {0, 1, 2, 3})
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
