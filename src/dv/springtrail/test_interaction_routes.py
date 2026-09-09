"""Literal model-only route anchors; no display or DUT timing assumption."""
from dataclasses import replace
import unittest

from interactions_reference import Game, Player, PLAYING, RETRY, WON
from interaction_routes import (SUCCESS, DEATH_RETRY, SUCCESS_ANCHORS,
                                DEATH_ANCHORS, expected, anchor)


class Routes(unittest.TestCase):
    def test_success_complete_and_literal_checkpoints(self):
        rows = expected(SUCCESS)
        self.assertEqual(len(rows), 360)
        self.assertTrue(all(row['state'].mode == PLAYING for row in rows[:-1]))
        self.assertEqual(rows[-1]['state'].mode, WON)
        for number, value in SUCCESS_ANCHORS.items():
            self.assertEqual(anchor(rows[number-1]['state']), value, number)
        changes = [(r['update'], r['state'].collected) for i, r in enumerate(rows)
                   if r['state'].collected != (rows[i-1]['state'].collected if i else 0)]
        self.assertEqual(changes, [(117, 2), (313, 10)])
        self.assertEqual(rows[-1]['state'].score, 2)

    def test_crosses_three_gaps_alive(self):
        rows = expected(SUCCESS)
        for number, x in ((80, 184), (180, 384), (270, 564)):
            game = rows[number-1]['state']
            self.assertEqual(game.player.x, x*16)
            self.assertLess(game.player.y, 112*16)
            self.assertFalse(game.player.fell)
            self.assertEqual(game.mode, PLAYING)

    def test_failure_after_collection_then_full_restore(self):
        rows = expected(DEATH_RETRY)
        self.assertEqual(len(rows), 188)
        self.assertTrue(all(r['state'].mode == PLAYING for r in rows[:186]))
        self.assertEqual(rows[186]['state'].mode, RETRY)
        self.assertTrue(rows[186]['state'].player.fell)
        for number, value in DEATH_ANCHORS.items():
            self.assertEqual(anchor(rows[number-1]['state']), value)
        self.assertEqual(rows[-1]['state'], Game(mode=PLAYING, previous=128,
                         player=replace(Player(), previous=128)))


if __name__ == '__main__':
    unittest.main()
