import unittest,zlib
from flow_reference import Check,LCD,CRC,require_baseline_rom,BASELINE_ROM_SHA256


class GameFrames(unittest.TestCase):
    def test_historical_image_guard(self):
        self.assertEqual(BASELINE_ROM_SHA256,'97f5d9da3c9d77d2da927fde77889c36fbb54d6ac2f5f79e6edb76e2a593b513')
        with self.assertRaisesRegex(AssertionError,'HISTORICAL_SPRINGTRAIL_ROM'):
            require_baseline_rom(bytes(32768))

    def test_complete_coordinates_and_literal_crc(self):
        check=Check()
        for number,frame in enumerate(check.expected):
            self.assertEqual(zlib.crc32(frame),CRC[number])
            for index,shade in enumerate(frame):
                y,x=divmod(index,160)
                dot=LCD+number*70224+y*456+93+x
                check.pixel((dot<<53)|(2<<21)|(x<<13)|(y<<5)|(shade<<3)|(int(index==0)<<2)|int(number!=0))
        self.assertEqual(check.pixels,69120)
        with self.assertRaisesRegex(AssertionError,'EXTRA_PIXEL'):check.pixel(0)

    def test_wrong_shade_line_coordinate_and_missing(self):
        value=((LCD+93)<<53)|(2<<21)|4
        for wrong in (value+8,value+(1<<13),value+(456<<53)):
            with self.assertRaises(AssertionError):Check().pixel(wrong)
        with self.assertRaisesRegex(AssertionError,'MISSING'):Check().finish(255000)


if __name__=='__main__':unittest.main()
