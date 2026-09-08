"""Original late-write images retain their pre-observation identities."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from src.dv.ppu.late208 import build, HASHES

ROOT=Path(__file__).resolve().parents[3]


class Late208Tests(unittest.TestCase):
    def test_original_cases(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'workdir') as folder:
            for case in HASHES:
                destination=Path(folder)/case
                image=build(ROOT,destination,case)
                report=json.loads((destination/'late208.json').read_text())
                self.assertEqual(hashlib.sha256(image).hexdigest(),HASHES[case])
                self.assertEqual(len(image),32768)
                self.assertEqual(len(report['events']),624)
                self.assertEqual(report['enable_commit'],3924)
                self.assertEqual(report['access_commit'],4456)
                self.assertEqual(report['access_retirement'],4460)
                self.assertEqual(report['events'][-1]['dot'],4480)
                self.assertTrue(all(len(event)==26 for event in report['events']))
                self.assertEqual(len(report['oam']),160)
                self.assertEqual(report['oam'][int(case,16)-0xfe00],129)
                if case=='fe20':
                    self.assertEqual(report['oam'][32:40],[129,144,77,114,151,188,225,6])
                    self.assertEqual(report['oam'][152:160],[3,40,77,114,151,188,225,6])

    def test_unknown_case(self):
        with self.assertRaisesRegex(ValueError,'unknown late208'):
            build(ROOT,ROOT/'workdir/unused','invalid')
