"""Literal scene anchors and checker sensitivity; no simulator or board."""
import unittest
from entities_render_check import Check, expected_tiles
from entities_render_program import SCENES
from entities_cases import ADDRESSES, state_bytes
from hud_reference import column


def write(check,dot,address,data):
    check.line(f'W {(dot<<24)|(address<<8)|data:x}')


def complete_short():
    check=Check(short=True,source_lcd=1000)
    check.lcd=1000;check.ended=True;check.ready=[20];check.hud=[25]
    check.bus_count=1;check.records=101;check.pixels=200;check.triggers=[30]
    check.tiles=list(enumerate(expected_tiles(),0x8000))
    check.initial_columns=[(0x9c40+(x&31)+y*32,v) for x in range(12,44)
                           for y,v in enumerate(column(x,check.world.blocks))]
    check.dma=[((30+8+4*i)<<18)|(i<<8)|v for i,v in enumerate(check.shadow)]
    return check


class EntityRenderer(unittest.TestCase):
    def test_literal_fixed_scenes_and_complete_tail(self):
        normal,changed=Check(),Check(variant='changed')
        self.assertEqual(len(expected_tiles()),2784)
        for check in (normal,changed):
            self.assertEqual(len(check.shadow),160)
            self.assertEqual(check.shadow[112:],bytes(48))
            self.assertEqual(check.shadow[:4],bytes([28,44,42,0]))
        self.assertEqual(list(normal.shadow[18:32:4]),[149,150,151,152])
        self.assertEqual(list(changed.shadow[18:32:4]),[155,155,158,159])
        self.assertEqual(list(normal.shadow[74:88:4]),[160,161,162,163])
        self.assertEqual(list(changed.shadow[74:88:4]),[164,165,166,167])
        self.assertEqual(normal.shadow[88:92],bytes([96,88,168,0]))
        self.assertEqual(changed.shadow[88:92],bytes([96,120,168,0]))
        self.assertEqual(list(changed.shadow[102:112:4]),[172,173,170])
        self.assertNotEqual(normal.images[1],changed.images[1])

    def test_uploaded_unused_legacy_tile_is_not_raster_blank(self):
        self.assertEqual(expected_tiles()[16:24],bytes([0x38,0x38,0x40,0x40,0x40,0x40,0x38,0x38]))
        check=complete_short();check.tiles[16]=(0x8010,0)
        with self.assertRaisesRegex(AssertionError,'ENTITY_TILES'):
            check.finish(2000,expected_tiles())

    def test_shadow_tile_mutation_fails_unchanged_oracle(self):
        check=Check()
        for a,v in zip(ADDRESSES,state_bytes(SCENES['normal'])):write(check,1,a,v)
        output=bytearray(check.shadow);output[18]=0
        with self.assertRaisesRegex(AssertionError,'ENTITY_SHADOW'):
            for i,v in enumerate(output):write(check,2+i,0xc100+i,v)

    def test_actual_pixel_mismatch_and_split_window(self):
        check=Check(source_lcd=1000);check.lcd=1000;check.pixels=23040
        wrong=(check.images[1][0]+1)%4
        value=((1000+70224+200)<<53)|(2<<21)|(wrong<<3)|4|1
        with self.assertRaisesRegex(AssertionError,'HUD_PIXEL'):
            check.pixel(value)
        with self.assertRaisesRegex(AssertionError,'ENTITY_SPLIT_WINDOW'):
            write(check,1000+16*456,0xff43,96)

    def test_complete_short_and_dma_corruption(self):
        self.assertEqual(complete_short().finish(2000,expected_tiles())['dma_bytes'],160)
        check=complete_short();check.dma[18]^=1
        with self.assertRaisesRegex(AssertionError,'ENTITY_DMA_BYTE'):
            check.finish(2000,expected_tiles())
        check=complete_short();check.ended=False
        with self.assertRaisesRegex(AssertionError,'ENTITY_INCOMPLETE'):
            check.finish(2000,expected_tiles())
