"""Current state and completion sensitivity; these synthetic events are not RTL proof."""
import unittest

import interaction_current_cases as suite
from motion_unit_check import Check
from n2m.generated_interfaces import RECORDS


def retirement(**values):
    raw = shift = 0
    for field in RECORDS['retirement']:
        raw |= values.get(field['name'], 0) << shift
        shift += field['bits']
    return 'R ' + format(raw, 'x')


def begin():
    check = Check(short=True, suite=suite)
    for address, value in zip(suite.ADDRESSES, check.selected[0]['before']):
        check.write(1, address, value)
    check.write(2, 0xc0fc, 1)
    return check


def result(check):
    for address, value in zip(suite.ADDRESSES, check.selected[0]['after']):
        check.write(3, address, value)


class InteractionCheck(unittest.TestCase):
    def test_complete_then_closed(self):
        check = begin()
        result(check)
        check.write(4, 0xc0fd, 1)
        check.write(5, 0xc0ff, 0xa5)
        check.line(retirement(epoch=2, dot=8, opcode=0x76))
        check.line('END 1')
        self.assertEqual(check.finish(20)['cases'], 1)
        with self.assertRaisesRegex(AssertionError, 'AFTER_END'):
            check.line('END 1')

    def test_wrong_score_and_preserved_fields(self):
        for address in (0xc029, 0xc093, 0xc307, 0xc337):
            with self.subTest(address=hex(address)):
                check = begin()
                result(check)
                check.write(3, address, check.memory[address] ^ 1)
                with self.assertRaisesRegex(AssertionError, 'MOTION_STATE'):
                    check.write(4, 0xc0fd, 1)

    def test_order_completion_and_bound(self):
        with self.assertRaisesRegex(AssertionError, 'MOTION_TERMINAL'):
            begin().write(3, 0xc0ff, 0xa5)
        with self.assertRaisesRegex(AssertionError, 'MOTION_REPORT'):
            begin().write(3, 0xc0fd, 2)
        with self.assertRaisesRegex(AssertionError, 'MOTION_END'):
            begin().line('END 0')
        with self.assertRaisesRegex(AssertionError, 'MOTION_INCOMPLETE'):
            begin().finish(20)
        check = begin()
        result(check)
        with self.assertRaisesRegex(AssertionError, 'MOTION_ROUTINE_BOUND'):
            check.write(suite.ROUTINE_BOUND+3, 0xc0fd, 1)


if __name__ == '__main__':
    unittest.main()
