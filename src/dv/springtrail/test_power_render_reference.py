"""The power renderer variant keeps the ordered two-stage shadow contract."""
import unittest
from power_render_reference import Check, SECONDARY


def write(dot, address, data):
    return f'W {(dot<<24)|(address<<8)|data:022x}'


class PowerRenderGuards(unittest.TestCase):
    def base(self):
        check = Check()
        for i, value in enumerate(check.base):
            check.line(write(100+i, 0xc100+i, value))
        return check

    def test_secondary_is_large_hurt_after_base(self):
        check = self.base()
        self.assertEqual(len(check.extra), 24)
        for i, value in enumerate(check.extra):
            check.line(write(300+i, SECONDARY+i, value))
        check.line(write(400, 0xff46, 0xc1))
        self.assertEqual(check.shadow[124:148], check.extra)
        self.assertEqual(check.shadow[148:], bytes(12))
        self.assertEqual(check.base[80:84], bytes((56, 51, 107, 0)))

    def test_wrong_secondary_address_rejected(self):
        with self.assertRaisesRegex(AssertionError, 'MOTION_SECONDARY_ORDER'):
            self.base().line(write(300, 0xc140, 0))
