"""Small independent-oracle sanity cases with explicit source bitplanes."""
import unittest
from src.dv.ppu.scene import Registers, shade, selected_objects


class PpuSceneTests(unittest.TestCase):
    def setUp(self):
        self.vram = bytearray(8192)
        self.oam = bytearray(160)
        self.vram[0x1800] = 1
        self.vram[16:18] = bytes((0x80, 0x40))  # BG x0=1, x1=2, others0.
        self.vram[32:34] = bytes((0xFF, 0xFF))  # OBJ raw3.

    def test_raw_background_priority_survives_palette_remapping(self):
        self.oam[:4] = bytes((16, 8, 2, 0x80))
        regs = Registers(bgp=0x03, obp0=0x40)  # BG0 black, BG1 white, OBJ3 light.
        self.assertEqual(shade(self.vram, self.oam, regs, 0, 0), 0)
        self.assertEqual(shade(self.vram, self.oam, regs, 2, 0), 1)

    def test_winning_object_is_not_replaced_after_background_priority(self):
        self.oam[:8] = bytes((16, 8, 2, 0x80, 16, 8, 2, 0))
        self.assertEqual(shade(self.vram, self.oam, Registers(), 0, 0), 1)
        self.oam[:8] = bytes((16, 9, 2, 0, 16, 8, 2, 0x80))
        self.assertEqual(shade(self.vram, self.oam, Registers(), 1, 0), 2)

    def test_hidden_x_entries_still_consume_selection_slots(self):
        for index in range(11):
            self.oam[index * 4:index * 4 + 4] = bytes((16, 0 if index < 10 else 8, 2, 0))
        self.assertEqual(len(selected_objects(self.oam, 0, 8)), 10)
        self.assertEqual(shade(self.vram, self.oam, Registers(), 0, 0), 1)

    def test_disabled_background_uses_bgp_color_zero(self):
        self.assertEqual(shade(self.vram, self.oam, Registers(lcdc=0x80, bgp=3), 0, 0), 3)
        self.oam[:4] = bytes((16, 8, 2, 0x80))
        self.assertEqual(shade(self.vram, self.oam, Registers(lcdc=0x82, bgp=3, obp0=0x40), 0, 0), 1)

    def test_signed_tile_and_object_transparency(self):
        self.vram[0x1800] = 0xFF
        self.vram[0xFF0:0xFF2] = bytes((0, 0x80))
        self.oam[:4] = bytes((16, 8, 0, 0))  # Transparent even if OBP color0 is black.
        self.assertEqual(shade(self.vram, self.oam, Registers(lcdc=0x83, obp0=3), 0, 0), 2)


if __name__ == '__main__':
    unittest.main()
