import unittest
from composition_game_reference import Check
from composition_reference import approved


class GameChecker(unittest.TestCase):
    def test_complete_end_and_tail(self):
        c=Check(True)
        c.line('W 0000000000000000')
        c.line('END 1')
        self.assertTrue(c.ended)
        with self.assertRaisesRegex(AssertionError,'AFTER_END'):c.line('W 0')
        for tail in ('END 0','END 2'):
            c=Check(True);c.line('W 0')
            with self.assertRaisesRegex(AssertionError,'END'):c.line(tail)
        c=Check(True);c.partial=[0]
        with self.assertRaisesRegex(AssertionError,'END'):c.line('END 0')
        with self.assertRaisesRegex(AssertionError,'INCOMPLETE'):Check(True).finish(0,b'')

    def test_input_record(self):
        raw=(2<<72)|(180100<<8)|129
        c=Check();c.lcd=120000;c.line('I '+format(raw,'x'))
        self.assertEqual(c.inputs,[180100])
        with self.assertRaisesRegex(AssertionError,'INPUT'):c.line('I '+format(raw,'x'))
        for value in (raw^1,raw^(1<<72),(2<<72)|(179000<<8)|129):
            c=Check();c.lcd=120000
            with self.assertRaisesRegex(AssertionError,'INPUT'):c.line('I '+format(value,'x'))
        with self.assertRaisesRegex(AssertionError,'INPUT'):Check(True).line('I '+format(raw,'x'))

    def test_visible_oam_and_phase(self):
        c=Check();c.lcd=120000
        for address in (0xfe00,0xfe9f,0x8000,0xff43):
            with self.assertRaises(AssertionError):
                c.line('W '+format(((120010)<<24)|(address<<8),'x'))
        c.line('W '+format((185670<<24)|(0xfe00<<8),'x'))

    def test_literal_title_and_pixel_failure(self):
        c=Check();c.lcd=120000
        self.assertEqual(len(c.images[1]),23040)
        self.assertEqual(c.images[1][0],0)
        self.assertEqual(c.images[1][112*160+20:112*160+36],approved(0)[:16])
        value=(120300<<53)|(2<<21)|4
        c.pixel(value)
        self.assertEqual(c.pixels,1)
        with self.assertRaisesRegex(AssertionError,'PIXEL'):c.pixel(value)


if __name__=='__main__':unittest.main()

