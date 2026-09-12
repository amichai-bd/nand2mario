"""Fixture source timing and shared-section identity, without RTL execution."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from entities_render_program import build
from startup_anchor import build as game_build

ROOT=Path(__file__).resolve().parents[3]


class EntityRenderProgram(unittest.TestCase):
    def test_both_source_images_and_shared_sections(self):
        game,_=game_build()
        parent=ROOT/'workdir';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='entity-render-',dir=parent) as folder:
            records=[]
            for variant in ('normal','changed'):
                destination=Path(folder)/variant
                rom=build(ROOT,destination,variant)
                record=json.loads((destination/'entities-render.json').read_text())
                self.assertEqual(len(rom),32768)
                self.assertEqual(record['end_bound'],record['lcd']+140448)
                self.assertLess(record['lcd'],200000)
                for section in record['sections']:
                    start,size=section['address'],section['size']
                    self.assertEqual(rom[start:start+size],game[start:start+size],section['name'])
                    self.assertEqual(hashlib.sha256(game[start:start+size]).hexdigest(),record['shared_sections'][section['name']])
                records.append(record)
            self.assertNotEqual(records[0]['sha256'],records[1]['sha256'])
