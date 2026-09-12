"""The second composer stage must finish before the final image is consumed."""
import unittest
from motion_render_reference import Check


def write(dot, address, data):
    return f'W {(dot<<24)|(address<<8)|data:022x}'


class MotionRenderGuards(unittest.TestCase):
    def base(self):
        check = Check()
        for i, value in enumerate(check.base):
            check.line(write(100+i, 0xc100+i, value))
        return check

    def test_ordered_base_secondary_then_dma(self):
        check = self.base()
        for i, value in enumerate(check.extra):
            check.line(write(300+i, check.secondary_base+i, value))
        check.line(write(400, 0xff46, 0xc1))
        self.assertEqual(check.triggers, [400])
        self.assertEqual(check.shadow[112:128], check.extra)
        self.assertEqual(check.shadow[128:], bytes(32))

    def test_current_entities_remain_before_secondary(self):
        check=Check(source_lcd=216684)
        self.assertEqual(check.secondary_base,0xc170)
        self.assertEqual(list(check.base[18:32:4]),[149,150,151,152])
        self.assertEqual(list(check.base[74:88:4]),[160,161,162,163])
        self.assertEqual(len(check.shadow),160)
        with self.assertRaisesRegex(AssertionError,'MOTION_SOURCE_LCD'):
            check.line(write(216685,0xff40,0x99))

    def test_built_current_variants_preserve_sections_and_operands(self):
        import json
        import tempfile
        from pathlib import Path
        from startup_anchor import Model, build as game_build
        from motion_render_program import build
        from entities_render_check import expected_tiles
        from power_render_reference import Check as PowerCheck
        root=Path(__file__).resolve().parents[3]
        game,_=game_build()
        with tempfile.TemporaryDirectory(dir=root/'workdir',prefix='current-render-') as folder:
            for variant,cls in (('motion',Check),('power',PowerCheck)):
                destination=Path(folder)/variant
                rom=build(root,destination,variant)
                record=json.loads((destination/(variant+'-render.json')).read_text())
                for section in record['sections']:
                    start,size=section['address'],section['size']
                    self.assertEqual(rom[start:start+size],game[start:start+size],section['name'])
                model=Model(rom,lcdc_on=0x99)
                while model.lcd is None:
                    self.assertLess(model.mcycles,100000)
                    model.mcycles+=model.step()
                self.assertEqual(model.lcd,record['lcd'])
                self.assertEqual(model.memory[0xc100:0xc1a0],cls().shadow)
                self.assertEqual(model.memory[0x8000:0x8ae0],expected_tiles())
                self.assertLessEqual(len(cls().shadow),160)

    def test_missing_secondary_cannot_publish(self):
        with self.assertRaisesRegex(AssertionError, 'HUD_DMA_TRIGGER'):
            self.base().line(write(300, 0xff46, 0xc1))

    def test_wrong_secondary_and_omission_rejected(self):
        check = self.base()
        for i, value in enumerate(check.extra):
            if i == 15:
                with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_SHADOW'):
                    check.line(write(300+i, check.secondary_base+i, value ^ 1))
            else:
                check.line(write(300+i, check.secondary_base+i, value))
        with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_ORDER'):
            self.base().line(write(300, 0xc171, 0))

    def test_partial_secondary_cannot_complete(self):
        check = self.base()
        check.line(write(300, check.secondary_base, check.extra[0]))
        check.terminal = 350
        check.halted = True
        check.line(f'END {check.lines}')
        with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_COMPLETE'):
            check.finish(400, b'')
