"""Host-only frozen-art and malformed-observation checks."""
import unittest,zlib
from reference import Check, LCD, image, FRAME_CRC


class FoundationReference(unittest.TestCase):
    def test_original_frames(self):
        self.assertEqual(zlib.crc32(b'123456789'),0xcbf43926)
        for frame in (1,2):
            data=image(frame)
            self.assertEqual(len(data),23040)
            self.assertEqual(zlib.crc32(data),FRAME_CRC[frame])
        self.assertNotEqual(image(1),image(2))

    def test_complete_pixel_order(self):
        check=Check()
        for frame in range(3):
            for index,shade in enumerate(image(frame)):
                y,x=divmod(index,160)
                dot=LCD+(93 if y==0 else 92+y*456)+x if frame==0 else LCD+70316+(frame-1)*70224+y*456+x
                value=(dot<<53)|(2<<21)|(x<<13)|(y<<5)|(shade<<3)|(int(index==0)<<2)|int(frame!=0)
                check.pixel(value)
        self.assertEqual(check.pixels,69120)
        with self.assertRaisesRegex(AssertionError,'EXTRA_FRAME'):check.pixel(0)

    def test_pixel_fault(self):
        value=((LCD+93)<<53)|(2<<21)|4
        for wrong in (value+8,value+(1<<13),value+(1<<53)):
            with self.assertRaisesRegex(AssertionError,'SPRINGTRAIL_PIXEL'):Check().pixel(wrong)

    def test_empty_unknown_and_truncated(self):
        with self.assertRaisesRegex(AssertionError,'MISSING'):Check().finish(249500)
        for line in ('P '+'x'*30+'\n','P 0000\n','END 1\n'):
            with self.assertRaises(AssertionError):Check().line(line)

    def test_input_and_end(self):
        check=Check();check.line('I '+f'{(2<<72)|(174000<<8)|128:026x}'+'\n')
        with self.assertRaisesRegex(AssertionError,'START'):check.line('I '+f'{(2<<72)|(174000<<8)|128:026x}'+'\n')
        check=Check();check.line('END 0\n')
        with self.assertRaisesRegex(AssertionError,'AFTER_END'):check.line('END 0\n')


if __name__=='__main__':unittest.main()
