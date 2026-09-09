import unittest
from unit_check import check_tail


class Tail(unittest.TestCase):
    def test_complete_order(self):
        check_tail('W', False)
        check_tail('terminal', False, (None,)*4)
        check_tail('END', True, (None,)*4)

    def test_duplicate_missing_and_postterminal(self):
        for kind, terminal in (('terminal', True), ('END', False), ('W', True)):
            with self.assertRaises(AssertionError):
                check_tail(kind, terminal, (None,)*4)

    def test_each_pending_boundary(self):
        for kind, terminal in (('terminal', False), ('END', True)):
            for index in range(4):
                pending = [None]*4
                pending[index] = 1
                with self.assertRaisesRegex(AssertionError, 'STACKDROP_PENDING_TAIL'):
                    check_tail(kind, terminal, pending)
            with self.assertRaisesRegex(AssertionError, 'STACKDROP_PENDING_TAIL'):
                check_tail(kind, terminal, (None,)*4, [(0x9800, 0)])


if __name__ == '__main__':
    unittest.main()
