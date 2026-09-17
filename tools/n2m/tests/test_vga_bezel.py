"""VGA bezel previews keep the scaled image exact, stay inside the 4-bit DAC and reproduce."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from tools.sw.vga_bezel import (BOTTOM, DIRECTIONS, HEIGHT, LEFT, RIGHT, SCALE, SHADE_CODE,
                                SOURCE_WIDTH, TOP, WIDTH, distance, generate, menu_frame,
                                plate_caps)

ROOT = Path(__file__).resolve().parents[3]
PREVIEWS = ROOT / 'wiki/src/rtl/vga/previews'
# The costs the design note quotes: border colours, unique 8x8 border cells and mirrored cells.
EXPECTED = {'shell': (12, 61, 36), 'plate': (3, 23, 11), 'vignette': (6, 19, 9)}


class VgaBezelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / 'workdir/builds/vga-bezel-unit'
        parent.mkdir(parents=True, exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=parent)
        cls.out = Path(cls.temp.name)
        cls.summary, cls.frames = generate(ROOT, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_the_frame_is_one_whole_active_raster(self):
        for name, rows in self.frames.items():
            self.assertEqual((len(rows[0]), len(rows)), (WIDTH, HEIGHT), name)

    def test_the_scaled_image_is_untouched(self):
        """Every image pixel is the menu reference shade at the geometry the scanout uses."""
        frame = menu_frame(ROOT)
        for name, rows in self.frames.items():
            for y in range(TOP, BOTTOM):
                for x in range(LEFT, RIGHT):
                    shade = frame[(y - TOP) // SCALE * SOURCE_WIDTH + (x - LEFT) // SCALE]
                    want = 17 * SHADE_CODE[shade]
                    self.assertEqual(rows[y][x], (want, want, want), (name, x, y))

    def test_every_colour_is_a_four_bit_dac_code(self):
        for name, rows in self.frames.items():
            self.assertLessEqual({v for row in rows for colour in row for v in colour},
                                 {17 * code for code in range(16)}, name)

    def test_each_direction_draws_a_visible_bezel(self):
        for name in DIRECTIONS:
            entry = self.summary[name]
            self.assertEqual(entry['border_pixels'], WIDTH * HEIGHT - (RIGHT - LEFT) * (BOTTOM - TOP))
            self.assertGreater(entry['lit_pixels'], entry['border_pixels'] // 5, name)

    def test_only_the_shell_uses_colour(self):
        self.assertFalse(self.summary['shell']['gray_only'])
        self.assertTrue(self.summary['plate']['gray_only'])
        self.assertTrue(self.summary['vignette']['gray_only'])

    def test_costs_match_the_design_note(self):
        for name, (colours, cells, folded) in EXPECTED.items():
            entry = self.summary[name]
            self.assertEqual((entry['border_colours'], entry['unique_cells'],
                              entry['folded_cells']), (colours, cells, folded), name)
            # The border is a whole number of 8x8 screen cells, so a tile bezel has no partial cell.
            self.assertEqual(entry['border_cells'], 1560, name)
            self.assertEqual(entry['tile_rom_bits'], 64 * entry['index_bits'] * folded, name)

    def test_the_plate_corners_reuse_the_committed_menu_art(self):
        caps = plate_caps(ROOT)
        self.assertEqual([len(tile) for tile in caps], [8, 8])
        rows = self.frames['plate']
        for dy in range(8):
            for dx in range(8):
                want = 17 * SHADE_CODE[caps[0][dy][dx]]
                self.assertEqual(rows[TOP - 8 * SCALE + SCALE * dy][LEFT - 8 * SCALE + SCALE * dx],
                                 (want, want, want), (dx, dy))

    def test_no_bezel_pixel_lands_inside_the_image(self):
        self.assertEqual(distance(LEFT, TOP), 0)
        self.assertEqual(distance(RIGHT - 1, BOTTOM - 1), 0)
        self.assertEqual((distance(LEFT - 1, TOP), distance(RIGHT, BOTTOM - 1)), (1, 1))

    def test_published_svgs_reproduce(self):
        published = sorted(path.name for path in PREVIEWS.glob('*.svg'))
        self.assertEqual(published, sorted(f'{name}.svg' for name in DIRECTIONS))
        for name in DIRECTIONS:
            self.assertEqual((PREVIEWS / f'{name}.svg').read_text(),
                             (self.out / name / 'frame.svg').read_text(), name)


if __name__ == '__main__':
    unittest.main()
