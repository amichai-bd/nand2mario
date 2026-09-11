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
            check.line(write(300+i, 0xc140+i, value))
        check.line(write(400, 0xff46, 0xc1))
        self.assertEqual(check.triggers, [400])
        self.assertEqual(check.shadow[64:80], check.extra)
        self.assertEqual(check.shadow[80:], bytes(80))

    def test_missing_secondary_cannot_publish(self):
        with self.assertRaisesRegex(AssertionError, 'HUD_DMA_TRIGGER'):
            self.base().line(write(300, 0xff46, 0xc1))

    def test_wrong_secondary_and_omission_rejected(self):
        check = self.base()
        for i, value in enumerate(check.extra):
            if i == 15:
                with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_SHADOW'):
                    check.line(write(300+i, 0xc140+i, value ^ 1))
            else:
                check.line(write(300+i, 0xc140+i, value))
        with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_ORDER'):
            self.base().line(write(300, 0xc141, 0))

    def test_partial_secondary_cannot_complete(self):
        check = self.base()
        check.line(write(300, 0xc140, check.extra[0]))
        check.terminal = 350
        check.halted = True
        check.line(f'END {check.lines}')
        with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_COMPLETE'):
            check.finish(400, b'')
