"""Host-only completion sensitivity; synthetic records are not DUT evidence."""
from pathlib import Path
import sys
import unittest
from hud_unit_check import Check
from hud_unit_cases import cases, expected, game
from interaction_cases import ADDRESSES, state_bytes

ROOT = Path(__file__).resolve().parents[3]
prior = sys.path[:]
try:
    sys.path.insert(0, str(ROOT/'src/dv/python/integration'))
    from test_integration import RECORDS
finally:
    sys.path[:] = prior


def retirement(**values):
    raw = shift = 0
    for field in RECORDS['retirement']:
        raw |= values.get(field['name'], 0) << shift
        shift += field['bits']
    return 'R '+format(raw, 'x')


def begin():
    check = Check(True)
    for a, v in zip(ADDRESSES, state_bytes(game(cases()[0]))): check.write(1, a, v)
    check.write(2, 0xc051, 0xa6)
    check.write(3, 0xc0fc, 1)
    return check


class UnitChecker(unittest.TestCase):
    def test_complete_and_closed_tail(self):
        check = begin()
        for a, v in expected(cases()[0]): check.write(4, a, v)
        check.write(5, 0xc0fd, 1); check.write(6, 0xc0ff, 0xa5)
        check.line(retirement(epoch=2, dot=8, opcode=0x76))
        check.line('END 1')
        self.assertEqual(check.finish(20)['cases'], 1)
        for line in ('END 1', 'W 0', retirement(epoch=2, dot=12, seq=1)):
            with self.assertRaisesRegex(AssertionError, 'AFTER_END'): check.line(line)

    def test_wrong_missing_and_duplicate_write(self):
        original = expected(cases()[0])
        for writes in (original[:-1], original+[original[-1]], [(original[0][0], 2)]+original[1:]):
            check = begin()
            for a, v in writes: check.write(4, a, v)
            with self.assertRaisesRegex(AssertionError, 'HUD_WRITES'): check.write(5, 0xc0fd, 1)
        check = begin()
        with self.assertRaisesRegex(AssertionError, 'GAME_MUTATION'): check.write(4, 0xc01b, 3)

    def test_pending_terminal_halt_and_end(self):
        check = begin()
        with self.assertRaisesRegex(AssertionError, 'HUD_TERMINAL'): check.write(4, 0xc0ff, 0xa5)
        with self.assertRaisesRegex(AssertionError, 'HUD_END'): check.line('END 0')
        with self.assertRaisesRegex(AssertionError, 'EARLY_HALT'):
            begin().line(retirement(epoch=2, dot=8, opcode=0x76))
        check = begin()
        for a, v in expected(cases()[0]): check.write(4, a, v)
        check.write(5, 0xc0fd, 1); check.write(6, 0xc0ff, 0xa5)
        with self.assertRaisesRegex(AssertionError, 'AFTER_TERMINAL'): check.write(7, 0xc200, 0)
        with self.assertRaisesRegex(AssertionError, 'HUD_END'): check.line('END 0')
        check.line(retirement(epoch=2, dot=8, opcode=0x76))
        with self.assertRaisesRegex(AssertionError, 'HUD_END'): check.line('END 2')
        with self.assertRaisesRegex(AssertionError, 'INCOMPLETE'): check.finish(20)


if __name__ == '__main__': unittest.main()
