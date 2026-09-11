"""Synthetic checker sensitivity for the block suite, not CPU evidence."""
import unittest

import blocks_cases
from blocks_cases import ADDRESSES, cases, parts
from motion_unit_check import Check


def begin():
    check = Check(True, blocks_cases)
    for address, value in zip(ADDRESSES, cases()[0]['before']):
        check.write(1, address, value)
    check.write(2, 0xc0fc, 1)
    return check


class BlocksUnitCheckTests(unittest.TestCase):
    def test_cases_split_and_first_is_the_item_hit(self):
        rows = cases()
        self.assertEqual(len(rows), 20)
        self.assertEqual([len(v) for v in parts().values()], [10, 10])
        self.assertEqual([r['name'] for r in rows[:2]], ['item-hit', 'effect-rise'])
        self.assertEqual(len(set(ADDRESSES)), 59)
        self.assertEqual(len(rows[0]['before']), 59)
        # Block 0 goes intact to used and releases the approved leaf tile.
        self.assertEqual((rows[0]['before'][48], rows[0]['after'][48]), (0, 1))
        self.assertEqual(rows[0]['after'][53], 132)
        self.assertEqual(rows[0]['after'][58], 16)

    def test_operand_slot_holds_every_half(self):
        # The unit fixture's assets section is 2 KiB of operand snapshots.
        for half in parts().values():
            self.assertLessEqual(len(half) * (len(ADDRESSES) + 1), 2048)

    def test_a_missed_block_state_is_rejected(self):
        check = begin()
        corrupt = bytearray(cases()[0]['after'])
        corrupt[48] = 0
        for address, value in zip(ADDRESSES, bytes(corrupt)):
            check.write(3, address, value)
        with self.assertRaisesRegex(AssertionError, 'MOTION_STATE item-hit'):
            check.write(4, 0xc0fd, 1)

    def test_two_case_short_completes_and_closes(self):
        check = begin()
        for index in range(2):
            case = cases()[index]
            if index:
                for address, value in zip(ADDRESSES, case['before']):
                    check.write(10, address, value)
                check.write(11, 0xc0fc, 2)
            for address, value in zip(ADDRESSES, case['after']):
                check.write(12, address, value)
            check.write(13, 0xc0fd, index + 1)
        check.write(14, 0xc0ff, 0xa5)
        self.assertTrue(check.terminal)

    def test_part_checker_uses_its_own_selection(self):
        check = Check(False, blocks_cases, 'b')
        self.assertEqual(check.selected[0]['name'], 'coin-hit')
        with self.assertRaisesRegex(AssertionError, 'MOTION_OPERANDS'):
            for address, value in zip(ADDRESSES, cases()[0]['before']):
                check.write(1, address, value)
            check.write(2, 0xc0fc, 1)


if __name__ == '__main__':
    unittest.main()
