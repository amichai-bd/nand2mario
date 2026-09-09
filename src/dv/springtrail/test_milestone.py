"""Check the fixed schedule and ordinary route phases before execution."""
import unittest
from interactions_reference import Game, update
from interaction_routes import anchor
from milestone import masks, plan


class Milestone(unittest.TestCase):
    def test_short_endpoints_and_input_phase(self):
        p = plan(True)
        self.assertEqual(p['normal_frames'], 8)
        self.assertEqual(p['end_dot'], 642852)
        self.assertEqual(p['captures'][0], dict(seq=0, pause_dot=151284,
                         reference_offset=46080, input_after=None))
        self.assertEqual(p['captures'][4], dict(seq=4, pause_dot=432180,
                         reference_offset=138240, input_after=1))
        self.assertEqual([e['buttons'] for e in p['inputs']], [129,1,1,1,0,0])

    def test_full_route_is_live_and_restarts_by_input(self):
        game = Game()
        wins = []
        for index, buttons in enumerate(masks(), 1):
            before = game.mode
            game = update(game, buttons)
            self.assertNotIn(game.mode, (0,2,3))
            if game.mode == 4 and before != 4:
                wins.append(index)
        self.assertEqual(wins, [360,721,1082,1443,1804,2165,2526,2887,3248])
        self.assertEqual(anchor(game), (1,11616,984,64,608,4360,-8,10,2,351))
        p = plan()
        self.assertEqual(len(p['inputs']), 3602)
        self.assertEqual(p['normal_frames'], 3604)
        self.assertEqual(p['captures'][-1], dict(seq=3603, pause_dot=253168356,
                         reference_offset=83059200, input_after=None))
