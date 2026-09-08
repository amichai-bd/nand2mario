"""Literal program/oracle consistency for the bounded startup witness."""
import json
from pathlib import Path
import tempfile
import unittest
from src.dv.ppu.startup202 import build

ROOT=Path(__file__).resolve().parents[3]


class Startup202Tests(unittest.TestCase):
    def test_original_images_and_independent_boundary(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'workdir') as folder:
            for case,count,halt,wanted in [('read',122,540,255),('write',125,564,129)]:
                destination=Path(folder)/case
                image=build(ROOT,destination,case)
                report=json.loads((destination/'startup202.json').read_text())
                self.assertEqual(len(image),32768)
                self.assertEqual((len(report['events']),report['halt_retirement']),(count,halt))
                self.assertEqual(report['access_commit']-report['enable_commit'],452)
                self.assertEqual(report['access_retirement'],536)
                self.assertEqual(report['events'][-2]['a'],wanted)
                self.assertEqual(report['events'][-1]['halted'],1)
                self.assertTrue(all(len(event)==26 for event in report['events']))
                self.assertEqual(image[0x100:0x104],bytes.fromhex('00c30002'))

    def test_unknown_case_rejected(self):
        with self.assertRaisesRegex(ValueError,'unknown startup202'):
            build(ROOT,ROOT/'workdir/unused','invalid')
