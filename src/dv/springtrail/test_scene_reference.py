import unittest
from dataclasses import replace
from interactions_reference import Game
from scene_reference import image


class Scene(unittest.TestCase):
    def test_initial_literal(self):
        self.assertEqual(image(Game()).hex(),
            "80200c0000081000686812000010120000d812000098120000e814001098160010502000")

    def test_hidden_and_fractional_projection(self):
        game = Game()
        game = replace(game, player=replace(game.player, x=73*16-1, y=-1, camera=80),
                       collected=15, score=4, mode=3)
        data = image(game)
        self.assertEqual(data[:4], bytes((0, 0, 12, 0)))  # x=-8 is fully clipped.
        self.assertEqual(data[8:12], bytes((0, 24, 18, 0)))
        self.assertEqual(data[-8:], bytes((16, 152, 30, 0, 16, 80, 38, 0)))
        game = replace(game, player=replace(game.player, x=73*16))
        self.assertEqual(image(game)[:4], bytes((15, 1, 12, 0)))


if __name__ == '__main__':
    unittest.main()
