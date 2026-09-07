"""Actual original software preparation and required input closure; no simulator."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT / 'tools'))
from n2m import python_tb, preload
from n2m.simulation import load_target


class V05PreloadTests(unittest.TestCase):
    def test_original_build_and_input_closure(self):
        target,_ = load_target(ROOT,'python-v05-short')
        with tempfile.TemporaryDirectory(dir=ROOT / 'workdir') as directory:
            destination = Path(directory)
            python_tb.prepare(target,destination,ROOT)
            record = preload.verify(destination)
            self.assertEqual(record['image_sha256'],'5163c78c7dff472d4a4366400cb4cc3ae88c5e30d3c3bad6b938822ff1e5cfb7')
            self.assertEqual(record['image_bytes'],32768)
            (destination / 'program.gb').write_bytes(bytes(32768))
            with self.assertRaisesRegex(ValueError,'image changed'):
                preload.verify(destination)
        target['python']['inputs'].remove('src/sw/v05/layout.json')
        with self.assertRaisesRegex(ValueError,'all software image inputs'):
            python_tb.validate(ROOT,target)


if __name__ == '__main__':
    unittest.main()
