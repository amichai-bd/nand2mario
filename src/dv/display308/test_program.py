import json
from pathlib import Path
import tempfile
import unittest
from program import build
from scene import OBJECTS

ROOT=Path(__file__).resolve().parents[3]


class Program(unittest.TestCase):
    def test_real_assembly(self):
        (ROOT/'workdir').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'workdir') as folder:
            image=build(ROOT,Path(folder))
            record=json.loads((Path(folder)/'display308.json').read_text())
        self.assertEqual(len(image),32768)
        self.assertEqual(record['sha256'],'7c422ab075c7a7bde2874ea47b118dc2d250b25c6dd9d2c6982ad8c03473867c')
        self.assertEqual((record['lcd_commit'],record['short_end'],record['end']),(11640,12664,96456))
        self.assertEqual(record['expected_oam'],[v for y,x,t,f in OBJECTS for v in (y+16,x+8,t,f)]+[0]*140)
        self.assertEqual(image[0x300:0x30f],bytes.fromhex('f5f041e60320fa3e08e043e042f1d9'))

    def test_condition_projection(self):
        # Ordinary line increment, phase0 compare and next-dot condition.
        self.assertEqual(15*456-5+2+1,6838)
        self.assertEqual(144*456-5+2+1,65662)

    def test_poll_budget(self):
        # The selected readable HBlank interval and every possible poll offset.
        for transition in range(248,257):
            for miss in range(32):
                for tail in (36,48):
                    self.assertTrue(280<=transition+miss+tail<=352)
        self.assertLess(256+32+48,456)


if __name__=='__main__':
    unittest.main()
