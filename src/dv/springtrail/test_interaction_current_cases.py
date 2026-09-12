"""Literal contract checks, not CPU execution evidence."""
import unittest

from interaction_current_cases import ADDRESSES, cases, operands, parts
from entities_reference import update


class CurrentInteractions(unittest.TestCase):
    def test_literal_outcomes(self):
        expected = (
            (1, 3, 2), (1, 7, 3), (1, 15, 4),
            (1, 1, 1), (1, 2, 1), (1, 4, 1), (1, 8, 1),
            (1, 0, 0), (1, 0, 0), (1, 0, 0),
            (1, 0, 0), (2, 0, 0), (2, 0, 0), (2, 15, 4),
            (1, 0, 0), (2, 14, 3), (1, 15, 4),
            (2, 7, 3), (4, 7, 3), (4, 15, 4))
        for (name, world, buttons), literal in zip(operands(), expected, strict=True):
            with self.subTest(name=name):
                after = update(world, buttons)
                self.assertEqual((after.mode, after.collected, after.score), literal)

    def test_turns_and_frame_counter(self):
        outcomes = {n: update(w, b) for n, w, b in operands()}
        for name, x, vx in (('patrol-right-depart', 4728, -8),
                             ('patrol-left-arrive', 3840, 8),
                             ('patrol-left-depart', 3848, 8)):
            self.assertEqual((outcomes[name].enemy_x, outcomes[name].enemy_vx), (x, vx))
        self.assertEqual(outcomes['select-ignored-playing'].timer, 43)
        self.assertEqual(outcomes['goal-frame-counter-wrap'].timer, 0)

    def test_complete_state_and_partition(self):
        rows = cases()
        self.assertEqual(len(rows), 20)
        self.assertEqual(len(ADDRESSES), 123)
        self.assertEqual(len({r['name'] for r in rows}), 20)
        self.assertEqual([r for group in parts().values() for r in group], rows)
        self.assertEqual([len(group) for group in parts().values()], [5, 5, 5, 5])
        for row in rows:
            self.assertEqual(row['kind'], 'game')
            self.assertEqual(len(row['before']), 123)
            self.assertEqual(len(row['after']), 123)


if __name__ == '__main__':
    unittest.main()
