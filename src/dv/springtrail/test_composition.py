import json
from pathlib import Path
import sys
import unittest
from composition_reference import approved, courier, raster, POSES, NAMES, BANK

ROOT=Path(__file__).resolve().parents[3]


class Composition(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior=sys.path[:]
        try:
            sys.path.insert(0,str(ROOT/'tools'))
            from sw.assembler import assemble
            from sw.linker import link
            from sw.assets import encode_shades, load_shades
            source=ROOT/'src/sw/springtrail'
            assets={name:encode_shades(load_shades(source/path,path),path) for name,path in
                    (('Tiles','tiles.json'),('Courier','assets/courier/unique-tiles.json'))}
            obj=assemble(source/'main.asm',source,ROOT/'src/sw/generated/interfaces.inc',assets)
            linked=link([('main.asm',obj)],json.loads((source/'layout.json').read_text()),
                        dict(unit='main.asm',symbol='Start'))
            cls.image=linked['image']
            cls.symbols={r['symbol']:r['value'] for r in linked['symbols']['symbols']}
            cls.asset=assets['Courier']
            cls.tiles=[]
            for base in range(0,len(assets['Tiles']+assets['Courier']),16):
                raw=(assets['Tiles']+assets['Courier'])[base:base+16]
                cls.tiles.append([[((raw[2*y]>>(7-x))&1)+2*((raw[2*y+1]>>(7-x))&1)
                                   for x in range(8)] for y in range(8)])
        finally:
            sys.path[:]=prior

    def test_asset_planes_and_layout(self):
        expected=bytes(v for tile in range(32) for y in range(8) for v in
                       (sum((BANK[y][tile*8+x]&1)<<(7-x) for x in range(8)),
                        sum(((BANK[y][tile*8+x]>>1)&1)<<(7-x) for x in range(8))))
        self.assertEqual(self.asset,expected)
        self.assertEqual(len(expected),512)
        self.assertEqual(self.symbols['CourierTiles']-self.symbols['Tiles'],672)
        self.assertEqual(self.symbols['TitleMap']-self.symbols['Tiles'],1184)
        self.assertGreaterEqual(self.symbols['SelectCourier'],0x5200)

    def test_all_pose_records_and_both_facing_pixels(self):
        for pose in range(12):
            size='large' if pose>=6 else 'small'
            address=self.symbols['Courier_'+size+'_'+NAMES[pose%6]]
            pieces=POSES[size][NAMES[pose%6]]
            expected=bytes([len(pieces)]+[v for p in pieces for v in
                (p['x'],p['y'],p['tile'],32*p['x_flip']+64*p['y_flip'])])
            self.assertEqual(self.image[address:address+len(expected)],expected)
            for left in (False,True):
                # Reflect the whole approved canvas independently of OAM composition.
                actual=raster(courier(pose,left,x=24,y=32),self.tiles)
                top=24 if pose>=6 else 32
                cropped=bytes(actual[y*160+x] for y in range(top,48) for x in range(24,40))
                self.assertEqual(cropped,approved(pose,left))

    def test_partial_edges_and_hidden(self):
        self.assertEqual(courier(0,x=-8)[:4],bytes((0,0,42,0)))
        self.assertEqual(courier(0,x=-7)[:4],bytes((16,1,42,0)))
        self.assertEqual(courier(0,x=159)[:4],bytes((16,167,42,0)))
        self.assertEqual(courier(0,x=160)[:4],bytes((0,168,42,0)))
        self.assertEqual(courier(0,y=-7)[:4],bytes((9,8,42,0)))
        self.assertEqual(courier(0,y=-8)[:4],bytes((0,8,42,0)))
        self.assertEqual(courier(0,y=143)[:4],bytes((159,8,42,0)))
        self.assertEqual(courier(0,y=144)[:4],bytes((0,8,42,0)))
        self.assertEqual(courier(11,True,hidden=True)[::4],bytes(6))

    def test_scanline_selection_limit_and_priority(self):
        tiles=[[[1]*8 for _ in range(8)],[[2]*8 for _ in range(8)]]
        # Ten selected offscreen-X entries still suppress an eleventh on-screen one.
        first=bytes((16,0,0,0))*10
        self.assertEqual(raster(first+bytes((16,8,1,0)),tiles)[:8],bytes(8))
        self.assertEqual(raster(first[:36]+bytes((16,8,1,0)),tiles)[:8],bytes([2])*8)
        self.assertEqual(raster(bytes((16,8,0,0,16,8,1,0)),tiles)[:8],bytes([1])*8)
