"""Approved skid source pixels and original cartridge placement."""
import json
from pathlib import Path
import unittest
import sys


ROOT = Path(__file__).resolve().parents[3]


class MotionAssets(unittest.TestCase):
    def test_approved_skid_and_unchanged_courier_records(self):
        prior = sys.path[:]
        try:
            sys.path.insert(0, str(ROOT/'tools'))
            from sw.assembler import assemble
            from sw.assets import encode_shades, load_shades
            from sw.linker import link
        finally:
            sys.path[:] = prior
        source = ROOT/'src/sw/springtrail'
        assets = {name: encode_shades(load_shades(source/path, path), path)
                  for name, path in (('Tiles', 'tiles.json'),
                    ('Courier', 'assets/courier/unique-tiles.json'),
                    ('Core', 'assets/core/core-tiles.json'))}
        obj = assemble(source/'main.asm', source,
                       ROOT/'src/sw/generated/interfaces.inc', assets)
        linked = link([('main.asm', obj)], json.loads((source/'layout.json').read_text()),
                      dict(unit='main.asm', symbol='Start'))
        image = linked['image']
        symbols = {r['symbol']: r['value'] for r in linked['symbols']['symbols']}
        self.assertEqual(len(image), 32768)
        maps = json.loads((source/'assets/core/core-maps.json').read_text())
        pixels = json.loads((source/'assets/core/core-tiles.json').read_text())['pixels']
        pieces = maps['small-skid']['pieces']
        self.assertEqual([(p['x'], p['y'], p['tile']) for p in pieces],
                         [(0, 0, 16), (8, 0, 17), (0, 8, 18), (8, 8, 19)])
        start = symbols['Courier_small_SKID']
        expected = bytes([4]+[v for p in pieces for v in
                         (p['x'], p['y'], 94+p['tile']-16-42,
                          32*p['x_flip']+64*p['y_flip'])])
        self.assertEqual(image[start:start+17], expected)
        table = symbols['CourierPointers']
        self.assertEqual(int.from_bytes(image[table+24:table+26], 'little'), start)
        self.assertEqual(symbols['CoreTiles'], 0x6000)
        for tile in range(16, 20):
            raw = image[0x6000+tile*16:0x6000+(tile+1)*16]
            decoded = bytes(((raw[y*2] >> (7-x)) & 1) |
                            (((raw[y*2+1] >> (7-x)) & 1) << 1)
                            for y in range(8) for x in range(8))
            self.assertEqual(decoded, bytes(pixels[y][tile*8+x]
                                           for y in range(8) for x in range(8)))
        poses = json.loads((source/'assets/courier/poses.json').read_text())
        for form in ('small', 'large'):
            for name, parts in poses[form].items():
                address = symbols['Courier_'+form+'_'+name]
                expected = bytes([len(parts)]+[v for p in parts for v in
                    (p['x'], p['y'], p['tile'], 32*p['x_flip']+64*p['y_flip'])])
                self.assertEqual(image[address:address+len(expected)], expected)

    def test_all_motion_pose_pixels_and_facing(self):
        from composition_reference import approved, raster
        from motion_frames import courier, tiles
        atlas = json.loads((ROOT/'src/sw/springtrail/assets/core/core-tiles.json').read_text())['pixels']
        pieces = json.loads((ROOT/'src/sw/springtrail/assets/core/core-maps.json').read_text())['small-skid']['pieces']
        rows = [[0]*16 for _ in range(16)]
        for part in pieces:
            for y in range(8):
                for x in range(8):
                    rows[part['y']+y][part['x']+x] = atlas[y][part['tile']*8+x]
        for pose in (0, 1, 2, 3, 4, 12):
            for left in (False, True):
                pixels = raster(courier(pose, left, 24, 32), tiles())
                expected = (approved(pose, left) if pose != 12 else
                            bytes(v for row in rows for v in (row[::-1] if left else row)))
                actual = bytes(pixels[y*160+x] for y in range(32, 48) for x in range(24, 40))
                self.assertEqual(actual, expected)
