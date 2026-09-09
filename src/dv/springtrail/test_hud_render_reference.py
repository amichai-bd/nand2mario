import unittest
from hud_render_reference import Check
from test_hud_game_reference import write

class RendererGuards(unittest.TestCase):
    def test_literal_entering_pixel_and_hud(self):
        check=Check()
        self.assertEqual(check.images[1][80*160+159],1)
        self.assertEqual(check.images[1][:2560],__import__('hud_reference').image(__import__('interactions_reference').Game(mode=1))[:2560])

    def test_split_uses_published_camera_and_map(self):
        check=Check();check.lcd=120000
        dot=check.lcd+15*456+300
        check.line(write(dot,0xff43,95));check.line(write(dot+32,0xff40,0x9b))
        other=Check();other.lcd=120000
        with self.assertRaisesRegex(AssertionError,'HUD_SPLIT_ORDER'):
            other.line(write(dot,0xff43,97))
        with self.assertRaisesRegex(AssertionError,'HUD_RENDER_END'):
            Check().line('END 0')

    def test_wrong_entering_cache(self):
        check=Check();check.cache=[0]*512
        with self.assertRaisesRegex(AssertionError,'HUD_RENDER_CACHE'):
            check.line(write(100,0xc200,255))
