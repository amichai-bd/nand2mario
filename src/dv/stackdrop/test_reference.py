"""Literal boundary cases and shape-table checks before actual CPU execution."""
import unittest
from reference import Game, cells


class Rules(unittest.TestCase):
    def test_shapes(self):
        for piece in range(7):
            for rotation in range(4):
                points = cells(piece, rotation)
                self.assertEqual(len(set(points)), 4)
                self.assertTrue(all(0 <= x < 4 and 0 <= y < 4 for x, y in points))
            self.assertEqual(set(cells(piece, 4)), set(cells(piece, 0)))
        self.assertEqual(set(cells(0, 1)), {(2, 0), (2, 1), (2, 2), (2, 3)})
        self.assertEqual(set(cells(2, 1)), {(2, 1), (1, 0), (1, 1), (1, 2)})

    def test_edges_and_gravity(self):
        game = Game()
        game.update(128)
        self.assertEqual((game.status, game.x, game.y), (1, 2, 0))
        game.update(1)
        game.update(1)
        self.assertEqual(game.x, 3)
        game.update(3)
        self.assertEqual(game.x, 3)
        for _ in range(56):
            game.update(0)
        self.assertEqual((game.gravity, game.y), (59, 0))
        game.update(0)
        self.assertEqual((game.gravity, game.y), (0, 1))

    def test_rotation_bounds_and_drop_priority(self):
        game = Game(status=1, x=0)
        game.update(2)
        self.assertEqual(game.x, 0)
        game.update(16)
        self.assertEqual(game.rotation, 1)
        game.update(40)
        self.assertEqual((game.piece, game.gravity, game.y), (1, 0, 0))
        self.assertEqual([i for i, cell in enumerate(game.board) if cell], [66, 74, 82, 90])

    def test_clear_and_saturation(self):
        game = Game(status=1, x=0, y=10)
        game.board[88:96] = [0, 0, 0, 0, 1, 1, 1, 1]
        game.lock()
        self.assertEqual((game.score, sum(game.board), game.piece), (100, 0, 1))
        game = Game(status=1, piece=1, x=0, y=10, score=9900)
        game.board[80:96] = [1, 0, 0, 1, 1, 1, 1, 1]*2
        game.lock()
        self.assertEqual((game.score, sum(game.board), game.piece), (9999, 0, 2))

    def test_gameover_and_restart(self):
        game = Game(status=1)
        game.board[3] = 1
        game.piece = 1
        game.spawn()
        self.assertEqual(game.status, 2)
        game.update(128)
        self.assertEqual((game.status, game.score, game.piece, sum(game.board), game.previous), (1, 0, 0, 0, 128))
        game.update(128)
        self.assertEqual(game.gravity, 1)


if __name__ == '__main__':
    unittest.main()
