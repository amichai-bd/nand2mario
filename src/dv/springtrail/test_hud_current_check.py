"""Independent ordered-write and completion refusal tests."""
import unittest
from hud_current_check import Check
from hud_current_cases import operands,expected,CANARIES


def begin(check,index=0):
    case=check.selected[index]
    for a,v in (operands(case)|{a:0xa5 for a in CANARIES}).items():check.write(1,a,v)
    check.write(100,0xc0fc,index+1)
    return expected(case)


class Writes(unittest.TestCase):
    def test_complete_short_and_missing_end(self):
        c=Check(True);rows=begin(c)
        for a,v in rows:c.write(200,a,v)
        c.write(1000,0xc0fd,1);c.write(1010,0xc0ff,0xa5);c.halted=True
        with self.assertRaisesRegex(AssertionError,'MOTION_INCOMPLETE'):c.finish(1200)
        c.line('END 0');self.assertEqual(c.finish(1200)['cases'],1)
        with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_AFTER_TERMINAL'):c.write(1201,0xc052,0)
    def test_actual_published_byte_fault_is_not_a_cache_fault(self):
        c=Check(True);rows=begin(c)
        for a,v in rows:
            if 0x9800<=a<0xa000:
                with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_WRITE'):c.write(200,a,v^1)
                break
            c.write(200,a,v)
        self.assertEqual(bytes(c.memory[0xc200+i] for i in range(16)),bytes([0]*14+[11,11]))
    def test_missing_or_reordered_store_fails(self):
        for missing in (True,False):
            c=Check(True);rows=begin(c)
            if missing:
                for a,v in rows[:-1]:c.write(200,a,v)
                with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_MISSING_WRITE'):c.write(1000,0xc0fd,1)
            else:
                a,v=rows[1]
                with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_WRITE'):c.write(200,a,v)
    def test_transient_world_published_camera_and_canary_writes_fail(self):
        for address in (0xc000,0xc051,*CANARIES):
            c=Check(True);begin(c)
            with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_UNRELATED_WRITE'):c.write(200,address,0)
    def test_missing_report_and_early_terminal_fail(self):
        c=Check(True);begin(c)
        with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_TERMINAL'):c.write(1000,0xc0ff,0xa5)
    def test_source_metadata_is_not_mutable_scratch(self):
        c=Check(True);begin(c)
        with self.assertRaisesRegex(AssertionError,'HUD_CURRENT_WRITE'):c.write(200,0xc053,2)


if __name__=='__main__':unittest.main()
