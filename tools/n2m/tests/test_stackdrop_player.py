"""Independent visible geometry and legal path checks for the fixed player."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'src/dv/stackdrop'))
from reference import Game, cells as reference_cells
from screen import decode, image
from n2m.stackdrop_player import cells, choose, evaluate, state


class PlayerTests(unittest.TestCase):
    def test_all_visible_orientations(self):
        for piece in range(7):
            for rotation in range(4):
                game = Game(status=1, piece=piece, rotation=rotation, x=2, y=2)
                screen = decode(image(game))
                self.assertEqual(state(screen), (piece, (2, 2, rotation)))
                self.assertEqual(set(cells(piece, rotation, 2, 2)),
                                 {(x+2, y+2) for x, y in reference_cells(piece, rotation)})

    def test_literal_clear_and_ties(self):
        board = [0]*88+[1, 1, 1, 1, 0, 0, 0, 0]
        self.assertEqual(evaluate(board, [(x, 11) for x in range(4, 8)]), 1000)
        screen = decode(image(Game(status=1)))
        self.assertEqual(choose(screen, 'baseline')['mask'], 32)
        first = choose(screen, 'strategy')
        self.assertEqual(first, choose(screen, 'strategy'))
        self.assertIn(first['mask'], (1, 2, 16, 32))

    def test_paths_use_legal_game_edges(self):
        for piece in range(7):
            game = Game(status=1, piece=piece)
            selected = choose(decode(image(game)), 'strategy')
            for mask in selected['path']:
                before = (game.x, game.y, game.rotation)
                game.previous = 0
                game.update(mask)
                if mask != 32:
                    self.assertNotEqual(before, (game.x, game.y, game.rotation))
            self.assertNotEqual(game.piece, piece)

    def test_reject_invalid_and_ambiguous(self):
        screen = decode(image(Game(status=1)))
        for field, bad in (('rotation', 4), ('next_piece', 7), ('active', [(0, 0)]), ('board', [0])):
            altered = dict(screen, **{field: bad})
            with self.assertRaises(ValueError):
                choose(altered, 'strategy')


if __name__ == '__main__':
    unittest.main()
