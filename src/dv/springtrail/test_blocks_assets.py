"""Approved terrain sources, cartridge placement and composed block pixels."""
import json
from pathlib import Path
import sys
import unittest

from dataclasses import replace

import blocks_reference as B
from blocks_frames import DESIGNS, TERRAIN, TERRAIN_MAPS, atlas, background
from blocks_cases import under
from motion_frames import tiles
from power_reference import update

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'src/sw/springtrail'
VRAM_BASE = 0x86c0


def build():
    prior = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT / 'tools'))
        from sw.assembler import assemble
        from sw.assets import encode_shades, load_shades
        from sw.linker import link
    finally:
        sys.path[:] = prior
    assets = {name: encode_shades(load_shades(SOURCE / path, path), path)
              for name, path in (('Tiles', 'tiles.json'),
                                 ('Courier', 'assets/courier/unique-tiles.json'),
                                 ('Core', 'assets/core/core-tiles.json'),
                                 ('Terrain', 'assets/core/terrain-tiles.json'),
                                 ('Enemies', 'assets/core/enemies-tiles.json'))}
    obj = assemble(SOURCE / 'main.asm', SOURCE, ROOT / 'src/sw/generated/interfaces.inc', assets)
    return link([('main.asm', obj)], json.loads((SOURCE / 'layout.json').read_text()),
                dict(unit='main.asm', symbol='Start'))


def encoded(tile):
    """The 16 two-bit-plane bytes of one approved atlas tile."""
    out = bytearray()
    for y in range(8):
        low = high = 0
        for x in range(8):
            value = TERRAIN[y][tile * 8 + x]
            low |= (value & 1) << (7 - x)
            high |= (value >> 1) << (7 - x)
        out += bytes((low, high))
    return bytes(out)


class BlockAssets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.linked = build()
        cls.symbols = {row['symbol']: row['value'] for row in cls.linked['symbols']['symbols']}
        cls.image = cls.linked['image']

    def test_every_design_is_an_unflipped_four_tile_approved_map(self):
        for base, name in DESIGNS.items():
            spec = TERRAIN_MAPS[name]
            self.assertEqual((spec['width'], spec['height']), (16, 16), name)
            places = [(p['x'], p['y'], p.get('x_flip', False), p.get('y_flip', False))
                      for p in spec['pieces']]
            self.assertEqual(places, [(0, 0, False, False), (8, 0, False, False),
                                      (0, 8, False, False), (8, 8, False, False)], name)
            self.assertEqual(atlas(base), list(range(atlas(base)[0], atlas(base)[0] + 4)))

    def test_vram_ids_are_contiguous_and_follow_the_power_allocation(self):
        self.assertEqual(B.FIRST_TILE, 108)
        self.assertEqual(len(B.ATLAS_TILES), 32)
        self.assertEqual(sorted(DESIGNS), list(range(108, 140, 4)))

    def test_packaged_terrain_tiles_equal_the_approved_atlas(self):
        start = self.symbols['TerrainTiles']
        for index, tile in enumerate(B.ATLAS_TILES):
            offset = start + tile * 16
            self.assertEqual(self.image[offset:offset + 16], encoded(tile),
                             f'atlas tile {tile} at VRAM {108 + index}')

    def test_startup_copies_land_on_the_documented_vram_addresses(self):
        # Four eight-tile groups from atlas 10, 18, 26 and 38, in VRAM order.
        groups = [B.ATLAS_TILES[i:i + 8] for i in range(0, 32, 8)]
        self.assertEqual([group[0] for group in groups], [10, 18, 26, 38])
        for index, group in enumerate(groups):
            self.assertEqual(len(group), 8)
            self.assertEqual(VRAM_BASE + index * 128, 0x8000 + (108 + index * 8) * 16)

    def test_loaded_vram_pixels_equal_the_approved_atlas(self):
        loaded = tiles()
        # The progression row's nine approved tiles follow at 140..148.
        self.assertEqual(len(loaded), 149)
        for index, tile in enumerate(B.ATLAS_TILES):
            self.assertEqual(loaded[108 + index],
                             [list(TERRAIN[y][tile * 8:tile * 8 + 8]) for y in range(8)])

    def test_rendered_states_match_the_approved_designs(self):
        # Clear the live effect so the block's own pixels are the only layer.
        world = replace(update(under(38), 16), effect_tile=0, effect_timer=0)
        pixels = background(world)
        base = B.appearance(world.blocks, 0)
        self.assertEqual(base, B.USED_TILE)
        for piece, tile in enumerate(atlas(base)):
            ox = 304 + 8 * (piece & 1) - world.player.camera
            oy = 80 + 8 * (piece >> 1)
            for y in range(8):
                row = pixels[(oy + y) * 160 + ox:(oy + y) * 160 + ox + 8]
                self.assertEqual(list(row), list(TERRAIN[y][tile * 8:tile * 8 + 8]))

    def test_the_release_effect_uses_the_content_design(self):
        world = update(under(38), 16)
        self.assertEqual(DESIGNS[world.effect_tile], 'leaf')
        self.assertEqual(DESIGNS[B.SHARDS], 'shards')
        self.assertEqual(DESIGNS[B.COIN_TILE], 'coin1')
        self.assertEqual(DESIGNS[B.GEM], 'gem')


if __name__ == '__main__':
    unittest.main()
