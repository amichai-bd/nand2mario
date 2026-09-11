"""Approved core sources, original cartridge placement and composed pixels."""
import json
from pathlib import Path
import sys
import unittest

from composition_reference import raster
from motion_frames import tiles, CORE_TILES
from power_frames import courier, pieces, scene, vram, CORE_POSES, SHOT_TILE
from power_reference import World, Shot, THROWER, LARGE, HURT
from motion_reference import Player

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT/'src/sw/springtrail'
MAPS = json.loads((SOURCE/'assets/core/core-maps.json').read_text())
ATLAS = json.loads((SOURCE/'assets/core/core-tiles.json').read_text())['pixels']


def build():
    prior = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT/'tools'))
        from sw.assembler import assemble
        from sw.assets import encode_shades, load_shades
        from sw.linker import link
    finally:
        sys.path[:] = prior
    assets = {name: encode_shades(load_shades(SOURCE/path, path), path)
              for name, path in (('Tiles', 'tiles.json'),
                                 ('Courier', 'assets/courier/unique-tiles.json'),
                                 ('Core', 'assets/core/core-tiles.json'))}
    obj = assemble(SOURCE/'main.asm', SOURCE, ROOT/'src/sw/generated/interfaces.inc', assets)
    return link([('main.asm', obj)], json.loads((SOURCE/'layout.json').read_text()),
                dict(unit='main.asm', symbol='Start'))


def approved_pixels(name, left=False):
    """Composite the approved map directly from the atlas, 16 wide."""
    height = MAPS[name]['height']
    rows = [[0]*16 for _ in range(height)]
    for part in MAPS[name]['pieces']:
        for y in range(8):
            for x in range(8):
                rows[part['y']+y][part['x']+x] = ATLAS[y][part['tile']*8+x]
    return bytes(v for row in rows for v in (row[::-1] if left else row))


class PowerAssets(unittest.TestCase):
    def test_rom_pose_tables_and_tile_copies(self):
        linked = build()
        image = linked['image']
        symbols = {r['symbol']: r['value'] for r in linked['symbols']['symbols']}
        self.assertEqual(len(image), 32768)
        table = symbols['CourierPointers']
        names = {13: 'large_SKID', 14: 'small_HURT', 15: 'large_HURT', 16: 'large_CROUCH', 17: 'large_THROW'}
        for pose, name in names.items():
            start = symbols['Courier_'+name]
            self.assertEqual(int.from_bytes(image[table+2*pose:table+2*pose+2], 'little'), start)
            parts = pieces(pose)
            expected = bytes([len(parts)]+[v for x, y, tile, flip in parts
                                          for v in (x, y+(8 if len(parts) == 6 else 0), tile-42, 32*flip)])
            self.assertEqual(image[start:start+len(expected)], expected, name)
        # The startup copies place these atlas tiles at VRAM 94..107 in this order.
        self.assertEqual(CORE_TILES, (16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 43, 44, 45, 54))
        for index, tile in enumerate(CORE_TILES):
            raw = image[0x6000+tile*16:0x6000+(tile+1)*16]
            decoded = bytes(((raw[y*2] >> (7-x)) & 1) | (((raw[y*2+1] >> (7-x)) & 1) << 1)
                            for y in range(8) for x in range(8))
            self.assertEqual(decoded, bytes(ATLAS[y][tile*8+x] for y in range(8) for x in range(8)))
            self.assertEqual(vram(tile), 94+index)
        self.assertEqual(vram(54), SHOT_TILE)

    def test_composed_pose_pixels_match_approved_maps(self):
        for pose, name in CORE_POSES.items():
            for left in (False, True):
                large = MAPS[name]['height'] == 24
                pixels = raster(courier(pose, left, 24, 40), tiles())
                top = 40-8 if large else 40
                actual = bytes(pixels[y*160+x] for y in range(top, 56) for x in range(24, 40))
                self.assertEqual(actual, approved_pixels(name, left), (pose, left))

    def test_scene_layout_with_dead_enemy_and_shot(self):
        world = World(mode=1, power=THROWER, alive=False,
                      player=Player(x=120*16, y=12*16, camera=97, pose=2),
                      shot=Shot(140*16, 40*16, 32, -32, 20))
        data = scene(world)
        self.assertEqual(len(data), 160)
        self.assertEqual(data[:24], courier(8, False, 19, 12))
        self.assertEqual(data[24:32], bytes((0, (256-97+8) & 255, 16, 0, 0, (256-97+8) & 255, 17, 0)))
        self.assertEqual(data[72:76], bytes((56, 51, SHOT_TILE, 0)))
        self.assertEqual(data[76:], bytes(84))
        hurt = World(mode=1, phase=HURT, phase_timer=32, player=Player(x=24*16, y=112*16))
        self.assertEqual(scene(hurt)[:24], courier(15, False, 20, 112))
        self.assertEqual(scene(World(mode=1, player=Player(x=24*16, y=112*16)))[16:64],
                         scene(hurt)[24:72])


if __name__ == '__main__':
    unittest.main()
