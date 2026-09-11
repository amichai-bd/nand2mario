"""Synthetic checker sensitivity tests, not claimed CPU execution evidence."""
from pathlib import Path
import sys
import unittest
from motion_cases import ADDRESSES, RANGES, cases
from motion_unit_check import Check

# Read the shared record layout from its generator, not from the cocotb
# simulator fixture that re-exports it, so this host fixture imports without
# the simulator.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from n2m.generated_interfaces import RECORDS


def retirement(**values):
    raw = shift = 0
    for field in RECORDS['retirement']:
        raw |= values.get(field['name'], 0) << shift
        shift += field['bits']
    return 'R '+format(raw, 'x')


def begin():
    check = Check(True)
    for address, value in zip(ADDRESSES, cases()[0]['before']):
        check.write(1, address, value)
    check.write(2, 0xc0fc, 1)
    return check


def complete():
    check = begin()
    for address, value in zip(ADDRESSES, cases()[0]['after']):
        check.write(3, address, value)
    check.write(4, 0xc0fd, 1)
    check.write(5, 0xc0ff, 0xa5)
    return check


class MotionUnitCheckTests(unittest.TestCase):
    def test_addresses_and_fixed_integration_anchors(self):
        self.assertEqual(ADDRESSES, [a for start, count in RANGES for a in range(start, start+count)])
        self.assertEqual(len(set(ADDRESSES)), 34)
        rows = {c['name']:c for c in cases()}
        self.assertEqual(rows['first-right']['after'][1:3], bytes([0x90, 1]))
        for name in ('select-restart', 'retry-restart'):
            row = rows[name]['after']
            self.assertEqual(row[0], 1)
            self.assertEqual(row[1:5], bytes([0x80, 1, 0, 7]))
            self.assertEqual(row[23:33], bytes([0, 0, 0, 0, 1, 0, 0, 0, 0, 0]))
            self.assertEqual(row[-1], 1)
        for name in ('pause', 'paused-held', 'resume-held'):
            row = rows[name]
            self.assertEqual(row['before'][23:33], row['after'][23:33])

    def test_complete_and_closed_tail(self):
        check = complete()
        check.line(retirement(epoch=2, dot=8, opcode=0x76))
        check.line('END 1')
        self.assertEqual(check.finish(20)['cases'], 1)
        with self.assertRaisesRegex(AssertionError, 'AFTER_END'):
            check.line('END 1')

    def test_missing_wrong_state_and_markers(self):
        with self.assertRaisesRegex(AssertionError, 'MOTION_STATE'):
            begin().write(3, 0xc0fd, 1)
        check = begin()
        for address, value in zip(ADDRESSES, cases()[0]['after']):
            check.write(3, address, value)
        check.write(3, 0xc069, 32)
        with self.assertRaisesRegex(AssertionError, 'MOTION_STATE'):
            check.write(4, 0xc0fd, 1)
        with self.assertRaisesRegex(AssertionError, 'MOTION_REPORT'):
            begin().write(3, 0xc0fd, 2)
        with self.assertRaisesRegex(AssertionError, 'MOTION_TERMINAL'):
            begin().write(3, 0xc0ff, 0xa5)
        with self.assertRaisesRegex(AssertionError, 'DISPLAY_WRITE'):
            begin().write(3, 0xff46, 0xc1)

    def test_halt_end_and_watchdog(self):
        with self.assertRaisesRegex(AssertionError, 'EARLY_HALT'):
            begin().line(retirement(epoch=2, dot=8, opcode=0x76))
        check = complete()
        with self.assertRaisesRegex(AssertionError, 'MOTION_END'):
            check.line('END 0')
        check.line(retirement(epoch=2, dot=8, opcode=0x76))
        with self.assertRaisesRegex(AssertionError, 'MOTION_END'):
            check.line('END 2')
        with self.assertRaisesRegex(AssertionError, 'INCOMPLETE'):
            check.finish(20)
        check = begin()
        for address, value in zip(ADDRESSES, cases()[0]['after']):
            check.write(3, address, value)
        with self.assertRaisesRegex(AssertionError, 'ROUTINE_BOUND'):
            check.write(8003, 0xc0fd, 1)


if __name__ == '__main__':
    unittest.main()
