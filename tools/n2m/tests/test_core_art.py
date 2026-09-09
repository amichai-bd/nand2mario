"""Asset references, 2bpp decoding and approved SVG reproduction."""
import copy
from pathlib import Path
import tempfile
import unittest
from tools.sw.assets import encode_shades
from tools.sw.core_art import generate, load_assets, reconstruct

ROOT = Path(__file__).resolve().parents[3]


class CoreArtTests(unittest.TestCase):
    def test_sources_decode_and_approved_views_reproduce(self):
        packs, _, _ = load_assets(ROOT)
        for frames in packs.values():
            for name, data in frames.items():
                raw = encode_shades(data)
                decoded = [[0]*data['width'] for _ in range(data['height'])]
                n = 0
                for y in range(0,data['height'],8):
                    for x in range(0,data['width'],8):
                        for dy in range(8):
                            lo, hi = raw[n:n+2]; n += 2
                            for dx in range(8):
                                decoded[y+dy][x+dx] = ((lo>>(7-dx))&1) | (((hi>>(7-dx))&1)<<1)
                self.assertEqual(decoded,data['pixels'],name)
        parent = ROOT/'workdir/builds/core-art-unit'
        parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temp:
            generate(ROOT,Path(temp))
            references = list((ROOT/'wiki/src/sw/springtrail/core-art').glob('*.svg'))
            expected = {'scene-preview.svg','player-actions.svg','terrain-items-review.svg',
                        'enemies-platforms-review.svg','effects-icons.svg','progression-screens.svg','font-tiles.svg'}
            self.assertEqual({p.name for p in references},expected)
            for reference in references:
                self.assertEqual(reference.read_text(),(Path(temp)/reference.name).read_text(),reference.name)

    def test_bad_tile_placement_and_missing_coverage_rejected(self):
        bank = dict(schema_version=1,width=8,height=8,pixels=[[0]*8 for _ in range(8)])
        good = dict(width=8,height=8,pieces=[dict(x=0,y=0,tile=0)])
        for field,value in [('tile',1),('tile',-1),('x',1),('y',8),('x_flip',1)]:
            bad = copy.deepcopy(good); bad['pieces'][0][field] = value
            with self.assertRaises(ValueError):reconstruct(bank,bad)
        with self.assertRaises(ValueError):reconstruct(bank,dict(width=8,height=8,pieces=[]))
        with self.assertRaises(ValueError):reconstruct(bank,dict(width=8,height=8,pieces=good['pieces']*2))

    def test_tile_flip_coordinates(self):
        rows = [[0]*8 for _ in range(8)]; rows[0][0] = 3; rows[1][2] = 1
        bank = dict(schema_version=1,width=8,height=8,pixels=rows)
        data = reconstruct(bank,dict(width=8,height=8,pieces=[dict(x=0,y=0,tile=0,x_flip=True,y_flip=True)]))
        self.assertEqual(data['pixels'][7][7],3)
        self.assertEqual(data['pixels'][6][5],1)


if __name__ == '__main__':
    unittest.main()
