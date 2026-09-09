import unittest
from game_check import Check, LCD, END, INPUT_WINDOW, FRAMES, ADDRESSES, TITLE, PLAY
from cases import buffer


class GameCheck(unittest.TestCase):
    def complete(self):
        check = Check()
        check.write((52 << 24) | (0xff40 << 8))
        check.write((LCD << 24) | (0xff40 << 8) | 145)
        check.input((2 << 72) | (INPUT_WINDOW[0] << 8) | 128)
        for frame, pixels in enumerate(FRAMES):
            for index, shade in enumerate(pixels):
                y, x = divmod(index, 160)
                dot = LCD+frame*70224+y*456+100+x
                packed = (dot << 53) | (2 << 21) | (x << 13) | (y << 5) | (shade << 3) | (int(index == 0) << 2) | int(frame != 0)
                check.pixel(packed)
        for frame, game in enumerate((TITLE, PLAY)):
            start = LCD+65664+frame*70224
            for index, (address, value) in enumerate(zip(ADDRESSES, buffer(game))):
                check.write(((start+100+index*30) << 24) | (address << 8) | value)
            check.write(((start+15000) << 24) | (0xc275 << 8) | 10)
        return check

    def test_complete_pipeline(self):
        self.assertEqual(self.complete().finish(END)['pixels'], 69120)

    def test_vblank_and_prepare_deadlines(self):
        with self.assertRaisesRegex(AssertionError, 'STACKDROP_VBLANK_WRITE'):
            Check().write(((LCD+70224) << 24) | (0x9866 << 8))
        check = self.complete()
        check.prepared[0] = LCD+65664+70224
        with self.assertRaisesRegex(AssertionError, 'STACKDROP_PREPARATION_BUDGET'):
            check.finish(END)

    def test_wrong_pixel_and_input(self):
        with self.assertRaisesRegex(AssertionError, 'STACKDROP_PIXEL'):
            Check().pixel(((LCD+100) << 53) | (2 << 21) | 12)
        with self.assertRaisesRegex(AssertionError, 'STACKDROP_INPUT'):
            Check().input((2 << 72) | ((INPUT_WINDOW[1]+1) << 8) | 128)


if __name__ == '__main__':
    unittest.main()
