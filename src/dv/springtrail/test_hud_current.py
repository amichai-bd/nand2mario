"""Literal current HUD/column expectations, before any CPU observation."""
import unittest
from hud_current_cases import cases,expected,operands,world


class Literals(unittest.TestCase):
    def setUp(self):self.rows={c['name']:c for c in cases()}
    def writes(self,name):return expected(self.rows[name])
    def test_finite_matrix_and_ordinary_world(self):
        self.assertEqual(len(self.rows),30)
        self.assertEqual(self.rows['paused-pair0']['mode'],3)
        self.assertEqual(operands(self.rows['paused-pair0'])[0xc051],0xa6)
    def test_columns_have_literal_first_last_gap_and_platform(self):
        for name in ('decode-0-0','decode-0-95','decode-1-79','decode-2-79'):
            self.assertEqual(self.writes(name),list(enumerate([0]*14+[11,11],0xc200)))
        self.assertEqual(self.writes('decode-0-22'),list(enumerate([0]*16,0xc200)))
        self.assertEqual(self.writes('decode-0-31'),list(enumerate([0]*8+[11]+[0]*5+[11,11],0xc200)))
    def test_ring_wrap_clamp_and_direction(self):
        for name,col in (('camera-0-80-88',31),('camera-0-88-96',32),('camera-0-96-88',11),('camera-0-608-607',75)):
            writes=self.writes(name);vram=[a for a,_ in writes if a>=0x8000 and a<0xa000]
            self.assertEqual(vram,[0x9c40+(col&31)+32*y for y in range(16)])
        self.assertEqual(self.writes('camera-0-607-608'),[(0xc053,0),(0xc023,76)])
        self.assertEqual(self.writes('camera-0-96-96'),[(0xc053,0),(0xc023,12)])
        self.assertEqual(self.writes('camera-2-479-480'),[(0xc053,0),(0xc023,60)])
    def test_restore_switch_is_last_and_restart_repeats(self):
        rows=self.writes('final-pair30')
        switch=rows.index((0xff40,0x19))
        self.assertEqual(rows[switch-1],(0xc02f,32))
        self.assertEqual([a for a,_ in rows[-6:]],[0x9c22,0x9c23,0x9c2d,0x9c2e,0x9c2f,0x9c32])
        self.assertEqual([a for a,_ in rows if 0x9840<=a<0x9a40 or 0x9c40<=a<0x9e40],
                         [0x9c40+col+32*y for col in (30,31) for y in range(16)])
        restart=self.writes('restart-twice');self.assertEqual(restart[:len(restart)//2],restart[len(restart)//2:])
    def test_hud_literals_and_dual_map(self):
        for mode,tiles in ((0,[90,83,90,84,82,0,74]),(5,[90,83,145,82,91,87,74]),(6,[86,146,82,88,0,0,75])):
            rows=self.writes(f'hud-mode{mode}')
            self.assertEqual(rows[:7],list(enumerate(tiles,0xc220)))
            self.assertEqual(rows[7:14],[(0x9801+i,v) for i,v in enumerate(tiles[:6])]+[(0x9812,tiles[6])])
            self.assertEqual(rows[14:],[(a+0x400,v) for a,v in rows[7:14]])
    def test_progress_values_select_one_map(self):
        for bit,base in ((0,0x9800),(8,0x9c00)):
            rows=self.writes(f'progress-map{bit}');values=[74,144,77,143,142,77]
            self.assertEqual(rows[:6],list(enumerate(values,0xc097)))
            self.assertEqual(rows[6:],[(base+32+x,v) for x,v in zip((2,3,13,14,15,18),values)])
    def test_dirty_then_entering_and_full_shadow(self):
        rows=self.writes('dirty-defers-entering');self.assertEqual(rows[-1],(0xc023,12))
        self.assertEqual(sum(a==0xc052 for a,_ in rows),2)
        self.assertLess(rows.index((0xc083,0)),rows.index((0xc08f,0)))
        rows=self.writes('scene-publication');shadow=rows[:160]
        self.assertEqual([a for a,_ in shadow],list(range(0xc100,0xc1a0)))
        self.assertEqual(rows[-160:],[(a+0x300,v) for a,v in shadow])
        self.assertEqual(rows[-161],(0xff46,0xc1))


if __name__=='__main__':unittest.main()
