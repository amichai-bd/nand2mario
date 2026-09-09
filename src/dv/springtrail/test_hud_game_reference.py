import unittest
from hud_game_reference import Check,PERIOD


def write(dot,address,data):
    return f'W {(dot<<24)|(address<<8)|data:022x}'


class HudGameGuards(unittest.TestCase):
    def checker(self):
        check=Check();check.lcd=140000
        return check

    def test_split_order_and_final_enable_deadline(self):
        check=self.checker();dot=check.lcd+15*456+300
        check.line(write(dot,0xff43,0));check.line(write(dot+32,0xff40,0x93))
        self.assertEqual(len(check.split),2)
        for address,offset,data in ((0xff40,300,0x93),(0xff43,400,0),(0xff43,250,0)):
            with self.subTest(address=address,offset=offset),self.assertRaisesRegex(AssertionError,'HUD_SPLIT'):
                self.checker().line(write(140000+15*456+offset,address,data))

    def test_pending_irq_and_spurious_sample(self):
        for address,data in ((0xff0f,0),(0xc019,129)):
            with self.assertRaises(AssertionError):
                self.checker().line(write(140000+7000,address,data))

    def test_actual_bus_dma_stack_rejected(self):
        check=self.checker();check.bus((100<<25)|(0xff46<<9)|(1<<8)|0xc1)
        check.bus((108<<25)|(0xff82<<9))
        self.assertEqual(check.bus_count,1)
        with self.assertRaisesRegex(AssertionError,'HUD_DMA_BUS'):
            check.bus((112<<25)|(0xdffe<<9)|(1<<8))

    def test_late_publication_and_incomplete_terminal(self):
        check=self.checker()
        with self.assertRaisesRegex(AssertionError,'HUD_PUBLICATION_BOUND'):
            check.line(write(check.lcd+65664+4480,0x9801,1))
        with self.assertRaisesRegex(AssertionError,'HUD_INCOMPLETE'):
            self.checker().finish(140000+PERIOD,b'')

    def test_dma_completion_exceeds_bound_before_vblank_end(self):
        check=self.checker();check.triggers=[100];check.ready=[200]
        with self.assertRaisesRegex(AssertionError,'HUD_DMA_COMPLETION_BOUND'):
            check.line(write(check.lcd+65664+3900,0xff46,0xc1))
