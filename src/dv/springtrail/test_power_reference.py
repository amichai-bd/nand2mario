"""Literal histories for the contact/power contract, independent of DUT code."""
from dataclasses import FrozenInstanceError, fields, replace
import unittest

from motion_reference import Player
from power_reference import (World, Shot, update, world_update, power_up, grant_star,
                             overlap, selected_pose, hidden, SMALL, LARGE, THROWER,
                             NORMAL, GROW, HURT, SAFE, RETRY, PLAYING, PAUSED)


def history(world, masks):
    result = []
    for mask in masks:
        world = update(world, mask)
        result.append(world)
    return result


def playing(**player):
    return World(mode=PLAYING, player=Player(**player))


class PowerReferenceTests(unittest.TestCase):
    def test_reset_fields_and_frozen(self):
        self.assertEqual([f.name for f in fields(World)], [
            'player', 'mode', 'enemy_x', 'enemy_vx', 'collected', 'score', 'timer',
            'previous', 'power', 'phase', 'phase_timer', 'invincible', 'throw',
            'alive', 'crouch', 'shot', 'blocks', 'coins', 'effect_tile',
            'effect_x', 'effect_y', 'effect_timer'])
        reset = World()
        self.assertEqual((reset.power, reset.phase, reset.alive, reset.shot), (0, 0, True, Shot()))
        with self.assertRaises(FrozenInstanceError):
            reset.power = 1

    def test_stomp_kills_and_bounces(self):
        fall = playing(x=252*16, y=104*16, grounded=False, jump=3, pose=4)
        stomp = update(fall, 0)
        self.assertEqual((stomp.alive, stomp.enemy_x, stomp.player.y//16), (False, 256*16+8, 108))
        self.assertEqual((stomp.player.jump, stomp.player.index, stomp.player.saved,
                          stomp.player.pose, stomp.player.grounded), (1, 13, 0, 4, False))
        self.assertEqual(stomp.mode, PLAYING)
        rise = update(stomp, 0)
        self.assertEqual((rise.player.y//16, rise.player.index, rise.player.saved), (107, 16, 12))
        self.assertEqual((rise.enemy_x, rise.alive), (256*16+8, False))  # dead enemy holds
        # Eight pixels of penetration is a hit, not a stomp.
        deep = update(playing(x=252*16, y=108*16, grounded=False, jump=3, pose=4), 0)
        self.assertEqual((deep.mode, deep.alive), (RETRY, True))

    def test_side_hit_small_large_and_suppression(self):
        walk = playing(x=252*16, counter=6, direction=1, speed=2)
        self.assertEqual(update(walk, 1).mode, RETRY)
        large = replace(walk, power=LARGE)
        hit = update(large, 1)
        self.assertEqual((hit.mode, hit.power, hit.phase, hit.phase_timer), (PLAYING, SMALL, HURT, 32))
        states = history(hit, [0]*128)
        self.assertEqual([s.phase_timer for s in states[:3]], [31, 30, 29])
        self.assertEqual((states[30].phase, states[30].phase_timer), (HURT, 1))
        self.assertEqual((states[31].phase, states[31].phase_timer), (SAFE, 96))
        self.assertEqual((states[126].phase, states[126].phase_timer), (SAFE, 1))
        self.assertEqual((states[127].phase, states[127].phase_timer), (NORMAL, 0))
        self.assertTrue(all(s.mode == PLAYING and s.alive for s in states))
        # Re-place the patrolling enemy on the player: suppressed in HURT and SAFE, fatal after.
        self.assertEqual(update(replace(states[10], enemy_x=252*16), 0).mode, PLAYING)
        self.assertEqual(update(replace(states[100], enemy_x=252*16), 0).mode, PLAYING)
        self.assertEqual(update(replace(states[127], enemy_x=252*16), 0).mode, RETRY)
        thrower = update(replace(walk, power=THROWER, throw=5), 1)
        self.assertEqual((thrower.power, thrower.throw, thrower.phase), (SMALL, 0, HURT))

    def test_invincible_contact_and_blink(self):
        star = grant_star(playing(x=252*16))
        self.assertEqual(star.invincible, 248)
        after = update(star, 0)
        self.assertEqual((after.alive, after.invincible, after.mode, after.power), (False, 247, PLAYING, SMALL))
        self.assertEqual([hidden(replace(star, invincible=t)) for t in (248, 244, 8, 5, 4, 1)],
                         [True, False, True, True, False, False])
        drained = history(star, [0]*248)[-1]
        self.assertEqual(drained.invincible, 0)

    def test_power_up_chain_and_growth(self):
        small = playing()
        large = power_up(small)
        self.assertEqual((large.power, large.phase, large.phase_timer), (LARGE, GROW, 32))
        thrower = power_up(large)
        self.assertEqual((thrower.power, thrower.phase, thrower.phase_timer), (THROWER, GROW, 32))
        self.assertEqual(power_up(thrower), thrower)
        grown = history(large, [0]*32)
        self.assertEqual((grown[30].phase, grown[30].phase_timer), (GROW, 1))
        self.assertEqual((grown[31].phase, grown[31].phase_timer, grown[31].power), (NORMAL, 0, LARGE))
        safe = replace(small, phase=SAFE, phase_timer=50)
        self.assertEqual(power_up(safe).phase, GROW)

    def test_crouch_masks_motion(self):
        moving = replace(playing(counter=6, direction=1, speed=2, pose=2), power=LARGE)
        crouch = update(moving, 9)
        self.assertEqual((crouch.crouch, crouch.player.x, crouch.player.counter,
                          crouch.player.previous), (True, 25*16, 5, 8))  # coasts once
        self.assertEqual(selected_pose(crouch), 16)
        self.assertFalse(update(replace(moving, power=SMALL), 9).crouch)
        airborne = replace(moving, player=replace(moving.player, y=60*16, grounded=False, jump=1, index=4))
        self.assertFalse(update(airborne, 9).crouch)
        released = update(crouch, 1)
        self.assertEqual((released.crouch, released.player.x, released.player.counter), (False, 25*16, 6))

    def test_shot_spawn_bounce_kill_and_limits(self):
        thrower = replace(playing(), power=THROWER)
        fired = update(thrower, 32)
        self.assertEqual(fired.shot, Shot(26*16, 118*16, 32, 32, 63))
        self.assertEqual((fired.throw, selected_pose(fired)), (8, 17))
        path = history(fired, [32]*3)
        self.assertEqual([(s.shot.x//16, s.shot.y//16, s.shot.vy) for s in path],
                         [(28, 120, 32), (30, 120, -32), (32, 118, -32)])
        self.assertEqual(path[0].shot.ttl, 62)
        self.assertEqual(update(fired, 0).shot.ttl, 62)  # held B spawns nothing new
        self.assertEqual(update(replace(fired, previous=0), 32).shot.ttl, 62)  # one live shot
        self.assertEqual(update(replace(thrower, power=LARGE), 32).shot, Shot())
        self.assertEqual(update(thrower, 40).shot, Shot())  # crouching thrower
        expired = history(fired, [0]*63)[-1]
        self.assertEqual(expired.shot, Shot())
        left = update(replace(thrower, player=Player(facing=32)), 32)
        self.assertEqual((left.shot.x, left.shot.vx), (22*16, -32))
        edge = update(replace(thrower, player=Player(x=0, facing=32)), 32)
        self.assertEqual(edge.shot, Shot())
        near = replace(thrower, player=Player(x=240*16, y=104*16, grounded=False, jump=1, index=20))
        kill = history(update(near, 32), [0]*6)
        self.assertEqual([(s.alive, s.shot.ttl) for s in kill[-3:]], [(True, 59), (False, 0), (False, 0)])

    def test_pose_precedence_and_hidden(self):
        w = replace(playing(pose=2), power=LARGE)
        self.assertEqual(selected_pose(w), 8)
        self.assertEqual(selected_pose(replace(w, player=replace(w.player, pose=5))), 13)
        self.assertEqual(selected_pose(replace(w, power=SMALL, player=replace(w.player, pose=5))), 12)
        self.assertEqual([selected_pose(replace(w, phase=HURT, phase_timer=t)) for t in (32, 29, 28, 25, 8, 5, 4, 1)],
                         [15, 15, 14, 14, 15, 15, 14, 14])
        self.assertEqual([selected_pose(replace(w, phase=GROW, phase_timer=t)) for t in (32, 29, 28, 25, 4, 1)],
                         [2, 2, 8, 8, 8, 8])
        self.assertEqual(selected_pose(replace(w, throw=1, crouch=True)), 17)
        self.assertEqual(selected_pose(replace(w, crouch=True)), 16)
        self.assertEqual(selected_pose(replace(w, mode=RETRY)), 11)
        self.assertEqual(selected_pose(replace(w, mode=RETRY, power=SMALL)), 5)
        self.assertEqual(selected_pose(replace(w, mode=0, phase=HURT, phase_timer=9)), 0)
        self.assertEqual([hidden(replace(w, phase=SAFE, phase_timer=t)) for t in (96, 93, 92, 89, 8, 4, 1)],
                         [True, True, False, False, True, False, False])
        self.assertTrue(hidden(replace(w, player=replace(w.player, fell=True))))

    def test_contact_box_and_item_collection(self):
        held = playing(x=96*16, y=97*16, grounded=False, jump=1, index=20, previous=16)
        self.assertEqual(update(held, 16).collected, 0)
        large = update(replace(held, power=LARGE), 16)
        self.assertEqual((large.collected, large.score, large.player.y), (1, 1, 97*16))
        self.assertFalse(overlap(replace(held, power=LARGE, crouch=True), 96*16, 88*16))

    def test_flow_preserves_and_resets_power(self):
        w = replace(playing(), power=THROWER, phase=SAFE, phase_timer=10, invincible=5,
                    shot=Shot(30*16, 100*16, 32, -32, 9), alive=False, throw=3)
        paused = update(w, 128)
        self.assertEqual(paused.mode, PAUSED)
        self.assertEqual((paused.phase_timer, paused.invincible, paused.shot, paused.throw),
                         (10, 5, w.shot, 3))
        restarted = update(paused, 192)
        self.assertEqual(restarted, World(mode=PLAYING, previous=192,
                                          player=replace(Player(), previous=192)))
        self.assertEqual(update(replace(w, mode=RETRY), 128).power, SMALL)
        with self.assertRaises(ValueError):
            update(w, 256)


if __name__ == '__main__':
    unittest.main()
