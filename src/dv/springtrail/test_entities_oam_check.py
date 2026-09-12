"""Host negatives for order and adjacent capacity canaries."""
import unittest
from entities_oam_check import Check


class OAMCheck(unittest.TestCase):
    def begin(self,part=None):
        check=Check(part=part)
        row=check.selected[0]
        for address,value in zip(check.addresses,row['before']):
            check.write(0,address,value)
        check.write(1,0xc0fc,1)
        return check,row

    def test_complete_order(self):
        check,row=self.begin()
        for address,value in row['writes']:check.write(2,address,value)
        check.write(100,0xc0fd,1)
        self.assertEqual(len(check.reports),1)

    def test_duplicate_store_even_when_final_memory_matches(self):
        check,row=self.begin()
        for address,value in row['writes']:check.write(2,address,value)
        check.write(3,*row['writes'][-1])
        with self.assertRaisesRegex(AssertionError,'ENTITY_OAM_ORDER'):
            check.write(100,0xc0fd,1)

    def test_adjacent_canary(self):
        check,row=self.begin()
        for address,value in row['writes']:check.write(2,address,value)
        with self.assertRaisesRegex(AssertionError,'ENTITY_OAM_UNRELATED_WRITE'):
            check.write(3,0xc1a0,0)

    def test_unrelated_state_cannot_be_written_and_restored(self):
        check,row=self.begin()
        with self.assertRaisesRegex(AssertionError,'ENTITY_OAM_UNRELATED_WRITE'):
            check.write(3,0xc330,0)

    def test_declared_entity_scratch_only(self):
        check,row=self.begin()
        for address in range(0xc338,0xc350):check.write(2,address,0x5a)
        for address in (0xc337,0xc350):
            with self.assertRaisesRegex(AssertionError,'ENTITY_OAM_UNRELATED_WRITE'):
                check.write(3,address,0)

    def test_literal_maximum_and_clipping(self):
        from entities_oam_cases import cases,STATE_ADDRESSES
        rows=cases();offset=len(STATE_ADDRESSES)
        large=rows[2]['after'][offset:offset+160]
        self.assertEqual(len(rows[2]['writes']),160)
        self.assertEqual(large[140:],bytes(20))
        # Six courier, four patrol, eight pickup, two goal, one shot, four
        # release effect, four CURL, three moving and three falling entries.
        self.assertEqual(list(large[26:40:4]),[149,150,153,154])
        self.assertEqual(large[82],107)
        self.assertEqual(list(large[86:100:4]),[124,125,126,127])
        self.assertEqual(list(large[102:116:4]),[160,161,162,163])
        self.assertEqual(list(large[130:140:4]),[168,169,170])
        clipped=rows[4]['after'][offset:offset+160]
        self.assertEqual(clipped[:8],bytes([0,0,42,0,28,8,43,0]))
        self.assertEqual(clipped[88:100:4],bytes([156,0,0]))

    def test_capacity_case_has_no_writes_and_keeps_shadow(self):
        from entities_oam_cases import cases
        check=Check();check.selected=[cases()[-1]];row=check.selected[0]
        for address,value in zip(check.addresses,row['before']):check.write(0,address,value)
        check.write(1,0xc0fc,1)
        check.write(80,0xc0fd,1)
        self.assertEqual(check.reports[0]['state'],row['before'].hex())
        check=Check();check.selected=[cases()[-1]];row=check.selected[0]
        for address,value in zip(check.addresses,row['before']):check.write(0,address,value)
        check.write(1,0xc0fc,1)
        with self.assertRaisesRegex(AssertionError,'ENTITY_OAM_LIMIT_WRITE'):
            check.write(2,0xc1a0,0)
