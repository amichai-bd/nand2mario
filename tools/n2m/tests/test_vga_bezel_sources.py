"""Generated bezel sources: drift, encoding facts and the independent model."""
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src/dv/python/vga'))
from n2m import vga_bezel_sources as sources

import bezel_reference

ROOT = Path(__file__).resolve().parents[3]


def decoded(palette_text, array_text):
    """Palette, border map and tile ROM read back out of the generated includes."""
    palette = [int(value, 16) for value in
               re.findall(r"12'h([0-9a-f]{3})", palette_text.split('BEZEL_PALETTE')[1])]
    cells = [int(value) for value in
             re.findall(r"6'd(\d+)", array_text.split('BEZEL_MAP')[1].split('};')[0])]
    pixels = [int(value) for value in
              re.findall(r"4'd(\d+)", array_text.split('BEZEL_TILE_ROM')[1].split('};')[0])]
    return palette, cells, pixels


def mif_values(text):
    """One generated memory initialization file as its address-ordered values."""
    depth = int(re.search(r'DEPTH = (\d+);', text)[1])
    width = int(re.search(r'WIDTH = (\d+);', text)[1])
    entries = {int(address): int(value) for address, value in
               re.findall(r'(\d+) : (\d+);', text.split('CONTENT BEGIN')[1])}
    assert sorted(entries) == list(range(depth)), 'MIF addresses are not dense'
    assert all(value < 2 ** width for value in entries.values()), 'MIF value exceeds its width'
    return [entries[address] for address in range(depth)]


class BezelSourceTests(unittest.TestCase):
    def setUp(self):
        self.files = {path: (ROOT / path).read_text(encoding='utf-8') for path in sources.OUTPUTS}
        self.palette, self.cells, self.pixels = decoded(
            self.files[sources.PALETTE_OUTPUT], self.files[sources.ARRAY_OUTPUT])

    def test_generated_include_has_no_drift(self):
        sources.generate(ROOT, check=True)
        base = ROOT / 'workdir/builds/vga-bezel-unit'
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=base, prefix='path with spaces ') as temporary:
            root = Path(temporary)
            for path in sources.SOURCES:
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, root / path)
            (root / sources.ARRAY_OUTPUT).parent.mkdir(parents=True, exist_ok=True)
            sources.generate(root)
            sources.generate(root, check=True)
            for path, text in self.files.items():
                self.assertEqual((root / path).read_text(encoding='utf-8'), text)
                (root / path).write_text(text + '\n')
                with self.assertRaisesRegex(ValueError, 'generation drift'):
                    sources.generate(root, check=True)
                (root / path).write_text(text)
            (root / sources.MAP_OUTPUT).unlink()
            with self.assertRaisesRegex(ValueError, 'generation drift'):
                sources.generate(root, check=True)

    def test_encoding_matches_the_published_cost_figures(self):
        self.assertEqual(len(self.palette), 16)
        self.assertEqual(len(self.cells), 1560)
        self.assertEqual(len(self.pixels), 3904)
        self.assertEqual(max(self.cells) + 1, 61)
        self.assertEqual(len(set(self.palette[:12])), 12)
        self.assertEqual(self.palette[12:], [0] * 4)
        palette_text = self.files[sources.PALETTE_OUTPUT]
        for name, value in (('BEZEL_TILES', 61), ('BEZEL_CELLS', 1560), ('BEZEL_TILE_PIXELS', 3904)):
            self.assertIn(f'{name} = {value};', palette_text)
        # No memory template: the simulation form is constant, and the fitted
        # design reads the MIFs through the explicit vendor ROM.
        self.assertNotIn('initial', self.files[sources.ARRAY_OUTPUT])
        self.assertNotIn('romstyle', self.files[sources.ARRAY_OUTPUT])

    def test_initialization_files_carry_the_simulated_contents(self):
        self.assertEqual(mif_values(self.files[sources.MAP_OUTPUT]), self.cells)
        self.assertEqual(mif_values(self.files[sources.TILE_OUTPUT]), self.pixels)
        scan = (ROOT / 'src/rtl/vga/n2m_vga_scan.sv').read_text(encoding='utf-8')
        for path in (sources.MAP_OUTPUT, sources.TILE_OUTPUT):
            self.assertIn(f'.init_file("{path.as_posix()}")', scan)

    def test_generated_rom_draws_the_independent_border_model(self):
        palette, cells, pixels = self.palette, self.cells, self.pixels
        shell = bezel_reference.Shell()
        for y in range(bezel_reference.HEIGHT):
            for x in range(bezel_reference.WIDTH):
                if shell.image(x, y):
                    continue
                cell = sources.map_index(x // 8, y // 8)
                colour = palette[pixels[64 * cells[cell] + 8 * (y % 8) + x % 8]]
                if colour != shell.pixel(x, y):
                    self.fail(f'generated ROM differs at {x},{y}: '
                              f'{colour:03x} against {shell.pixel(x, y):03x}')

    def test_model_matches_the_published_preview_renderer(self):
        from tools.sw import vga_bezel
        spec = json.loads((ROOT / sources.SOURCES[0]).read_text(encoding='utf-8'))
        draw = vga_bezel.shell(spec['shell'])
        shell = bezel_reference.Shell()
        for y in range(bezel_reference.HEIGHT):
            for x in range(bezel_reference.WIDTH):
                if shell.image(x, y):
                    continue
                red, green, blue = draw(x, y, vga_bezel.distance(x, y))
                expected = (red // 17 << 8) | (green // 17 << 4) | blue // 17
                if expected != shell.pixel(x, y):
                    self.fail(f'border model differs from the preview at {x},{y}')

    def test_map_index_covers_every_border_cell_once(self):
        indices = [sources.map_index(column, row) for row in range(60) for column in range(80)
                   if sources.border_cell(column, row)]
        self.assertEqual(sorted(indices), list(range(1560)))
        with self.assertRaises(ValueError):
            sources.map_index(10, 3)


if __name__ == '__main__':
    unittest.main()
