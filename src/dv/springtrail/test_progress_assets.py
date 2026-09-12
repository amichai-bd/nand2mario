"""Approved progression glyphs and icons, their cartridge placement and pixels."""
import json
from pathlib import Path
import unittest

from hud_reference import CHARS, EXTRA, IDS, LIFE_TILE, CLOCK_TILE, WORDS, art, image
from hud_reference import PROGRESS_ROW, progress_tiles
from motion_frames import tiles
from progress_reference import World, glyph as digit_glyph
from test_power_assets import build

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'src/sw/springtrail'
ATLAS = json.loads((SOURCE / 'assets/core/core-tiles.json').read_text())['pixels']
# Approved atlas tiles behind VRAM 140..148, in startup-copy order; the block
# terrain copies merged first and hold 108..139.
PROGRESS_TILES = (87, 88, 89, 90, 91, 68, 77, 52, 53)


def decode(raw):
    return bytes(((raw[y * 2] >> (7 - x)) & 1) | (((raw[y * 2 + 1] >> (7 - x)) & 1) << 1)
                 for y in range(8) for x in range(8))


class ProgressAssets(unittest.TestCase):
    def test_startup_copies_the_approved_atlas_tiles(self):
        linked = build()
        rom = linked['image']
        symbols = {r['symbol']: r['value'] for r in linked['symbols']['symbols']}
        self.assertEqual(len(rom), 32768)
        core = symbols['CoreTiles']
        table = symbols['ProgressPointers']
        for index, tile in enumerate(PROGRESS_TILES):
            pointer = int.from_bytes(rom[table + 2 * index:table + 2 * index + 2], 'little')
            self.assertEqual(pointer, core + tile * 16, index)
            expected = bytes(ATLAS[y][tile * 8 + x] for y in range(8) for x in range(8))
            self.assertEqual(decode(rom[pointer:pointer + 16]), expected, tile)

    def test_vram_identifiers_follow_the_power_tiles(self):
        self.assertEqual(len(PROGRESS_TILES), len(EXTRA))
        self.assertEqual([IDS[str(d)] for d in range(10)],
                         [74, 75, 76, 77, 78, 140, 141, 142, 143, 144])
        self.assertEqual([digit_glyph(d) for d in range(10)],
                         [74, 75, 76, 77, 78, 140, 141, 142, 143, 144])
        self.assertEqual((IDS['M'], IDS['V'], LIFE_TILE, CLOCK_TILE), (145, 146, 147, 148))
        self.assertEqual(len(tiles()), 149)

    def test_new_mode_words_use_loaded_glyphs_only(self):
        loaded = set(CHARS) | {'5', '6', '7', '8', '9', 'M', 'V'}
        for mode in (5, 6):
            self.assertLessEqual(set(WORDS[mode]), loaded, WORDS[mode])
            self.assertLessEqual(len(WORDS[mode]), 6)
        self.assertEqual((WORDS[5], WORDS[6]), ('TIMEUP', 'OVER'))

    def test_rom_mode_table_matches_the_reference_words(self):
        linked = build()
        rom = linked['image']
        symbols = {r['symbol']: r['value'] for r in linked['symbols']['symbols']}
        table = symbols['ModePointers']
        for mode, word in enumerate(WORDS):
            pointer = int.from_bytes(rom[table + 2 * mode:table + 2 * mode + 2], 'little')
            expected = bytes(IDS[c] if c != ' ' else 0 for c in word.ljust(6))
            self.assertEqual(rom[pointer:pointer + 6], expected, word)

    def test_row_one_cells_read_the_lives_timer_and_stage(self):
        self.assertEqual(progress_tiles(World()),
                         bytes((LIFE_TILE, IDS['0'], IDS['2'], CLOCK_TILE,
                                IDS['4'], IDS['0'], IDS['0'], IDS['1'])))
        loaded = World(lives=0x57, timer_high=0x02, timer_low=0x68, stage=2)
        self.assertEqual(progress_tiles(loaded),
                         bytes((LIFE_TILE, IDS['5'], IDS['7'], CLOCK_TILE,
                                IDS['2'], IDS['6'], IDS['8'], IDS['3'])))

    def test_row_one_pixels_match_the_approved_maps(self):
        pixels = image(World(mode=1, lives=0x57, timer_high=0x02,
                             timer_low=0x68, stage=2))
        shown = progress_tiles(World(lives=0x57, timer_high=0x02,
                                     timer_low=0x68, stage=2))
        for (start, _, _), tile in zip(PROGRESS_ROW, shown):
            name = EXTRA[tile - 140] if tile >= 140 else 'glyph-' + CHARS[tile - 74]
            actual = bytes(pixels[(y + 8) * 160 + start * 8 + x]
                           for y in range(8) for x in range(8))
            self.assertEqual(actual, art(name), name)

    def test_every_other_row_one_cell_stays_blank(self):
        pixels = image(World(mode=1))
        used = {start for start, _, _ in PROGRESS_ROW}
        for column in range(20):
            if column in used:
                continue
            block = [pixels[(y + 8) * 160 + column * 8 + x] for y in range(8) for x in range(8)]
            self.assertEqual(set(block), {0}, column)


class ProgressPreviews(unittest.TestCase):
    def test_committed_svgs_reproduce_from_the_approved_sources(self):
        import sys
        sys.path.insert(0, str(ROOT))
        from tools.sw.preview import svg
        import progress_preview as preview
        published = ROOT / 'wiki/src/sw/springtrail/progress'
        # SVGs are Git text; compare complete UTF-8 content after checkout newline normalization.
        for name, world in preview.VIEWS:
            expected = svg(preview.canvas_of(image(world)), 4)
            self.assertEqual((published / f'{name}.svg').read_text(encoding='utf-8').encode('utf-8'), expected, name)
        self.assertEqual((published / 'tiles.svg').read_text(encoding='utf-8').encode('utf-8'),
                         svg(preview.tile_sheet(), 4))



class RenderProgressOperands(unittest.TestCase):
    def test_both_linked_fixtures_seed_reset_state_before_preparing_hud(self):
        import tempfile
        from motion_render_program import build, bounds
        for variant in ('motion', 'power'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp)
                image_bytes = build(ROOT, destination, variant)
                self.assertEqual(len(image_bytes), 32768)
                timing = bounds(image_bytes)
                # Second VBlank plus the declared 1112-dot terminal tail must fit.
                final_tail = timing['lcd'] + 70224 + 65664 + 1112
                self.assertLess(final_tail, timing['end_bound'])
                self.assertGreater(timing['lcd'] + 70224 + 65664, 320000)
                metadata = json.loads((destination / (variant+'-render.json')).read_text())
                self.assertEqual(metadata['end_bound'], timing['end_bound'])
                text = (destination / 'program.asm').read_text()
                prepare = text.index('CALL PrepareProgress')
                for offset, value in enumerate((2, 0, 40, 0, 4, 0, 0)):
                    store = f'LD A,${value:02X}\nLD [${0xc090+offset:04X}],A'
                    self.assertIn(store, text[:prepare])

if __name__ == '__main__':
    unittest.main()
