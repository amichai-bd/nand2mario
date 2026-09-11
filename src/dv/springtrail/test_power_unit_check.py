"""Synthetic checker sensitivity for the power suite, not CPU evidence."""
import unittest
import power_cases
from power_cases import ADDRESSES, cases, parts
from motion_unit_check import Check


def begin():
    check = Check(True, power_cases)
    for address, value in zip(ADDRESSES, cases()[0]['before']):
        check.write(1, address, value)
    check.write(2, 0xc0fc, 1)
    return check


class PowerUnitCheckTests(unittest.TestCase):
    def test_cases_split_and_first_is_stomp(self):
        rows = cases()
        self.assertEqual(len(rows), 46)
        self.assertEqual([len(v) for v in parts().values()], [23, 23])
        self.assertEqual(rows[0]['name'], 'stomp')
        self.assertEqual(rows[0]['before'][39], 1)   # enemy alive before
        self.assertEqual(rows[0]['after'][39], 0)    # dead after the stomp
        self.assertEqual(rows[0]['after'][29:31], bytes([1, 13]))  # jump state, index
        self.assertEqual(len(set(ADDRESSES)), 48)
        self.assertEqual(len(rows[0]['before']), 48)

    def test_stomp_state_and_alive_fault(self):
        check = begin()
        for address, value in zip(ADDRESSES, cases()[0]['after']):
            check.write(3, address, value)
        check.write(3, 0xc06f, 1)
        with self.assertRaisesRegex(AssertionError, 'MOTION_STATE stomp'):
            check.write(4, 0xc0fd, 1)
        check = begin()
        for address, value in zip(ADDRESSES, cases()[0]['after']):
            check.write(3, address, value)
        check.write(4, 0xc0fd, 1)
        check.write(5, 0xc0ff, 0xa5)
        self.assertTrue(check.terminal)

    def test_part_checker_uses_its_own_selection(self):
        check = Check(False, power_cases, 'b')
        self.assertEqual(check.selected[0]['name'], 'crouch-airborne')
        with self.assertRaisesRegex(AssertionError, 'MOTION_OPERANDS'):
            for address, value in zip(ADDRESSES, cases()[0]['before']):
                check.write(1, address, value)
            check.write(2, 0xc0fc, 1)


if __name__ == '__main__':
    unittest.main()
