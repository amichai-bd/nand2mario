import unittest
from dataclasses import replace

from interactions_reference import Game, Player, PLAYING, PAUSED, RETRY, WON, overlap, update, world_update


class Interactions(unittest.TestCase):
    def test_patrol_endpoints(self):
        right = world_update(Game(mode=PLAYING, enemy_x=296*16-8), 0)
        self.assertEqual((right.enemy_x, right.enemy_vx), (296*16, -8))
        left = world_update(Game(mode=PLAYING, enemy_x=240*16+8, enemy_vx=-8), 0)
        self.assertEqual((left.enemy_x, left.enemy_vx), (240*16, 8))

    def test_half_open_fraction_and_contact(self):
        p = Player(x=88*16, y=72*16)
        self.assertFalse(overlap(p, 96*16, 88*16))
        self.assertTrue(overlap(replace(p, x=p.x+1, y=p.y+1), 96*16, 88*16))
        hit = world_update(Game(mode=PLAYING, player=Player(x=256*16)), 0)
        self.assertEqual(hit.mode, RETRY)

    def test_once_and_death_priority(self):
        initial = Game(mode=PLAYING, player=Player(x=96*16, y=80*16, grounded=False))
        collected = world_update(initial, 0)
        self.assertEqual((collected.collected, collected.score), (1, 1))
        self.assertEqual(world_update(collected, 0).score, 1)
        dead = world_update(replace(initial, player=replace(initial.player, fell=True)), 0)
        self.assertEqual((dead.mode, dead.collected, dead.score), (RETRY, 0, 0))

    def test_goal_and_restart(self):
        won = world_update(Game(mode=PLAYING, player=Player(x=736*16)), 0)
        self.assertEqual(won.mode, WON)
        reset = update(replace(won, score=3, collected=7, timer=123), 128)
        self.assertEqual(reset, Game(mode=PLAYING, previous=128,
                                    player=replace(Player(), previous=128)))

    def test_pause_resume_no_queued_jump(self):
        playing = Game(mode=PLAYING, timer=500)
        paused = update(playing, 128)
        held = update(paused, 16)
        self.assertEqual((held.mode, held.player.x, held.player.y,
                          held.enemy_x, held.timer), (PAUSED, 384, 1792, 4096, 500))
        resumed = update(held, 144)
        moved = update(resumed, 16)
        self.assertEqual((resumed.mode, moved.player.y), (PLAYING, 1792))

    def test_select_only_paused_and_start_edge(self):
        self.assertEqual(update(Game(mode=PLAYING, timer=10), 64).timer, 11)
        paused = Game(mode=PAUSED, timer=10, collected=3, score=2)
        self.assertEqual(update(paused, 64).timer, 0)
        self.assertEqual(update(Game(previous=128), 128).mode, 0)
        self.assertEqual(update(Game(), 129).player.x, 25*16)


if __name__ == '__main__':
    unittest.main()
