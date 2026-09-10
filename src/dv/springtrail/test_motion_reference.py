"""Literal histories for the original motion choices, independent of DUT code."""
from dataclasses import FrozenInstanceError, fields, replace
import unittest

from motion_reference import Player, profile, step


def history(player, masks):
    result = []
    for mask in masks:
        player = step(player, mask)
        result.append(player)
    return result


class MotionReferenceTests(unittest.TestCase):
    def test_reset_and_pause_operands(self):
        self.assertEqual([f.name for f in fields(Player)], [
            'x', 'y', 'vx', 'vy', 'grounded', 'previous', 'camera', 'fell',
            'counter', 'direction', 'speed', 'phase', 'animation', 'pose',
            'jump', 'index', 'saved', 'facing'])
        reset = Player()
        self.assertEqual((reset.x, reset.y, reset.animation, reset.phase, reset.facing),
                         (384, 1792, 1, 0, 0))
        with self.assertRaises(FrozenInstanceError):
            reset.x = 0
        moving = history(reset, [33]*5)[-1]
        paused = replace(moving, previous=16)
        self.assertEqual(replace(paused, previous=moving.previous), moving)
        self.assertEqual(step(paused, 16).jump, 0)  # Resume with synchronized held A.
        self.assertEqual(Player(), reset)  # Restart is a fresh complete state.

    def test_walk_run_and_opposites(self):
        walk = history(Player(), [1]*7)
        self.assertEqual([p.x//16 for p in walk], [25, 25, 26, 26, 27, 27, 28])
        self.assertEqual([p.counter for p in walk], [1, 2, 3, 4, 5, 6, 6])
        self.assertEqual([p.pose for p in walk], [0, 0, 0, 1, 1, 1, 1])
        run = history(Player(), [33]*7)
        self.assertEqual([p.x//16 for p in run], [25, 26, 27, 28, 30, 31, 33])
        self.assertEqual([p.speed for p in run], [2, 2, 2, 4, 4, 4, 4])
        self.assertEqual(history(Player(), [3]*7), [replace(p, previous=3) for p in walk])

    def test_coast_and_run_release(self):
        seed = Player(counter=6, direction=1, speed=4, phase=0, animation=9, pose=3,
                      previous=33)
        coast = history(seed, [0]*7)
        self.assertEqual([p.x//16 for p in coast], [25, 25, 26, 26, 27, 27, 27])
        self.assertEqual([p.counter for p in coast], [5, 4, 3, 2, 1, 0, 0])
        self.assertEqual((coast[-1].direction, coast[-1].pose, coast[-1].animation), (0, 0, 1))
        self.assertEqual(step(seed, 1).speed, 2)
        pressed = step(replace(seed, previous=1), 33)
        self.assertEqual((pressed.counter, pressed.speed), (1, 4))

    def test_reverse_hold_and_air_steering(self):
        seed = Player(counter=6, direction=1, speed=2, pose=2)
        states = history(seed, [2]*11)
        self.assertEqual([p.counter for p in states], [8, 7, 6, 5, 4, 3, 2, 1, 0, 0, 1])
        self.assertEqual([p.x for p in states[:10]], [384]*10)
        self.assertEqual([p.facing for p in states[:10]], [0]*10)
        self.assertEqual((states[0].pose, states[9].pose, states[10].facing), (5, 0, 32))
        airborne = step(replace(seed, y=60*16, grounded=False, jump=1, index=4, pose=4), 18)
        self.assertEqual((airborne.x, airborne.y, airborne.direction, airborne.pose),
                         (384, 58*16, 3, 4))
        accepted = step(Player(y=60*16, grounded=False, jump=1, index=4, pose=4), 18)
        self.assertEqual((accepted.x, accepted.facing, accepted.pose), (23*16, 32, 4))

    def test_phase_and_animation_wrap(self):
        p = step(Player(animation=255, direction=1, counter=6, speed=2, pose=3), 1)
        self.assertEqual((p.animation, p.pose), (0, 3))
        p = step(p, 1)
        self.assertEqual((p.animation, p.pose), (1, 1))
        p = step(Player(animation=0, direction=2, counter=6, speed=2, pose=1), 2)
        self.assertEqual((p.animation, p.pose), (255, 2))
        p = step(Player(counter=255, direction=1, speed=0), 1)
        self.assertEqual((p.counter, p.phase, p.x), (0, 1, 400))

    def test_profile_full_hold_and_rejump(self):
        self.assertEqual([profile(i) for i in range(26)],
                         [4, 4, 3, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2,
                          1, 1, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0])
        jump = history(Player(), [16]*49)
        self.assertEqual([p.y//16 for p in jump[:5]], [109, 106, 104, 102, 100])
        self.assertEqual((jump[23].y, jump[23].index, jump[23].jump), (79*16, 26, 1))
        self.assertEqual((jump[24].y, jump[24].index, jump[24].jump), (79*16, 24, 2))
        # Half-open boxes merely touch at update48; the next candidate contacts terrain.
        self.assertEqual((jump[47].y, jump[47].grounded), (112*16, False))
        self.assertEqual((jump[-1].y, jump[-1].grounded, jump[-1].jump,
                          jump[-1].index, jump[-1].saved), (112*16, True, 0, 0, 0))
        self.assertEqual(step(jump[-1], 16).jump, 0)
        self.assertEqual(step(step(jump[-1], 0), 16).y, 109*16)
        run = step(Player(counter=6, direction=1, speed=4, previous=33), 49)
        self.assertEqual((run.y, run.index, run.jump, run.pose), (108*16, 1, 1, 4))

    def test_release_restore_sentinel_and_exhaustion(self):
        seed = Player(y=60*16, grounded=False, jump=1, index=5, pose=4, previous=16)
        cut = step(seed, 0)
        self.assertEqual((cut.y, cut.index, cut.saved, cut.jump), (59*16, 16, 4, 1))
        restored = step(replace(cut, jump=2, index=14), 0)
        self.assertEqual((restored.y, restored.index, restored.saved, restored.jump),
                         (61*16, 3, 0, 2))
        zero = step(replace(seed, index=0), 0)
        self.assertEqual((zero.index, zero.saved), (16, 0))
        end = step(replace(seed, jump=2, index=0), 0)
        self.assertEqual((end.y, end.jump, end.index), (64*16, 3, 0))
        self.assertEqual(step(end, 0).y, 68*16)

    def test_wall_clamp_support_loss_and_fall(self):
        wall = Player(x=72*16, y=96*16, counter=6, direction=1, speed=2,
                      grounded=False, jump=1, index=20, previous=16, pose=4)
        states = history(wall, [17]*3)
        self.assertEqual([p.x for p in states], [72*16]*3)
        self.assertEqual([p.vx for p in states], [0]*3)
        self.assertEqual([p.phase for p in states], [1, 0, 1])
        self.assertEqual([p.animation for p in states], [2, 3, 4])
        bound = step(Player(x=760*16, counter=6, direction=1, speed=2), 1)
        self.assertEqual((bound.x, bound.vx, bound.phase, bound.camera), (760*16, 0, 1, 608))
        falling = step(Player(x=176*16, counter=6, direction=1, speed=2), 1)
        self.assertEqual((falling.y, falling.jump, falling.pose, falling.grounded),
                         (116*16, 3, 4, False))
        fell = history(falling, [0]*7)[-1]
        self.assertTrue(fell.fell)
        self.assertEqual(step(fell, 16), replace(fell, previous=16))

    def test_ceiling_landing_and_fractional_contacts(self):
        ceiling = step(Player(x=80*16, y=104*16, grounded=False, jump=1,
                              index=4, saved=0, pose=4, previous=16), 16)
        self.assertEqual((ceiling.y, ceiling.vy, ceiling.jump, ceiling.index, ceiling.saved),
                         (104*16, 0, 2, 0, 0))
        self.assertEqual(step(ceiling, 16).y, 108*16)
        landing = step(Player(x=80*16, y=79*16+1, grounded=False, jump=3, pose=4), 0)
        self.assertEqual((landing.y, landing.vy, landing.grounded, landing.jump),
                         (80*16, 0, True, 0))
        edge = step(Player(x=72*16-1, y=96*16, direction=1, counter=6, speed=2), 1)
        self.assertEqual((edge.x, edge.vx, edge.facing, edge.phase), (72*16, 0, 0, 1))


if __name__ == '__main__':
    unittest.main()
