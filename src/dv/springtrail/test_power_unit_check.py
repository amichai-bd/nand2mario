"""Synthetic checker sensitivity for the power suite, not CPU evidence."""
import unittest
import power_cases
from power_cases import ADDRESSES, cases, parts
from motion_unit_check import Check
from current_unit_cases import adapt
import power_cases as original_suite
CURRENT=adapt(original_suite)


def begin():
    check = Check(True, power_cases)
    for address, value in zip(CURRENT.ADDRESSES, CURRENT.cases()[0]['before']):
        check.write(1, address, value)
    check.write(2, 0xc0fc, 1)
    return check


class PowerUnitCheckTests(unittest.TestCase):
    def test_cases_split_and_first_is_stomp(self):
        rows = cases()
        self.assertEqual(len(rows), 46)
        self.assertEqual([len(v) for v in parts().values()], [23, 23])
        self.assertEqual([r['name'] for r in rows[:2]], ['crouch', 'stomp'])
        self.assertEqual((rows[0]['before'][10], rows[0]['after'][10]), (9, 8))  # masked Buttons
        self.assertEqual((rows[0]['after'][23], rows[0]['after'][25], rows[0]['after'][40]), (5, 0, 1))
        self.assertEqual(rows[1]['before'][39], 1)   # enemy alive before
        self.assertEqual(rows[1]['after'][39], 0)    # dead after the stomp
        self.assertEqual(rows[1]['after'][29:31], bytes([1, 13]))  # jump state, index
        self.assertEqual(len(set(ADDRESSES)), 48)
        self.assertEqual(len(rows[0]['before']), 48)

    def test_crouch_fault_and_two_case_short(self):
        check = begin()
        for address, value in zip(CURRENT.ADDRESSES, CURRENT.cases()[0]['after']):
            check.write(3, address, value)
        check.write(3, 0xc019, 9)
        with self.assertRaisesRegex(AssertionError, 'MOTION_STATE crouch'):
            check.write(4, 0xc0fd, 1)
        check = begin()
        for index in range(2):
            case = CURRENT.cases()[index]
            if index:
                for address, value in zip(CURRENT.ADDRESSES, case['before']):
                    check.write(10, address, value)
                check.write(11, 0xc0fc, 2)
            for address, value in zip(CURRENT.ADDRESSES, case['after']):
                check.write(12, address, value)
            check.write(13, 0xc0fd, index+1)
        check.write(14, 0xc0ff, 0xa5)
        self.assertTrue(check.terminal)

    def test_part_checker_uses_its_own_selection(self):
        check = Check(False, power_cases, 'b')
        self.assertEqual(check.selected[0]['name'], 'crouch-airborne')
        with self.assertRaisesRegex(AssertionError, 'MOTION_OPERANDS'):
            for address, value in zip(CURRENT.ADDRESSES, CURRENT.cases()[0]['before']):
                check.write(1, address, value)
            check.write(2, 0xc0fc, 1)


if __name__ == '__main__':
    unittest.main()
