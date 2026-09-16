"""The current image's visible preparation stays inside its bound with a live shot.

`visible_bound.derive` runs the actual routines on the independent SM83 timing
model over exhaustive branch operands and composes the entity plan's profiles.
The composition rewrite that pays for the shot must also leave every shadow
byte unchanged: the scene the CPU composes for the ordinary acquisition route
and the OAM fixture operands equals the independent scene model byte for byte.
"""
import unittest

from dataclasses import replace

import visible_bound as bound
from entities_frames import scene
from entities_reference import World, Entity, update
from motion_reference import Player
from power_reference import Shot
from thrower_route import masks


class VisibleBound(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = bound.Source()

    def test_every_reachable_profile_fits_with_a_live_shot(self):
        result = bound.derive(self.source)
        self.assertGreaterEqual(result['worst'], 0, result['rows'])
        self.assertEqual(len(result['rows']), len(bound.PROFILES))
        rows = {row['profile']: row for row in result['rows']}
        # Stage-0 play profiles carry the shot; resets, later stages and idle modes do not.
        self.assertGreater(rows['stage0 falling failedcarry']['shot'], 0)
        self.assertEqual(rows['early stage restoration/title transition']['shot'], 0)
        self.assertEqual(rows['later-stage ordinary noncarrier']['shot'], 0)
        self.assertEqual(rows['idle/reset/next-stage modes']['shot'], 0)
        self.assertGreater(result['scenes'][bound.FULL]['cap'], result['scenes'][bound.SMALL]['cap'])
        self.assertLess(result['emit_piece_max'], 400)
        self.assertLessEqual(result['shot']['step_shot_max'], 5200)

    def test_emit_piece_refuses_the_exhausted_entry_without_a_write(self):
        cpu = self.source.reset()
        before = bytes(cpu.memory)
        cpu.b, cpu.c, cpu.d, cpu.e = 8, 8, 0xc1, 0xa0
        self.source.call('EmitPiece')
        changed = [a for a in range(0x8000, 0x10000) if cpu.memory[a] != before[a] and not 0xdfe0 <= a < 0xdffe]
        self.assertEqual(changed, [])
        self.assertEqual((cpu.d, cpu.e), (0xc1, 0xa0))

    def test_composed_scene_matches_the_independent_model(self):
        worlds = []
        world = World()
        for buttons in masks():
            world = update(world, buttons)
            worlds.append(world)
        route_end = worlds[-1]
        # The 35-entry maximum: large courier, live shot and release effect with
        # every entity on screen, mirrored and clipped variants included.
        normal = World(mode=1, player=Player(x=40 * 16, y=12 * 16), enemy_x=72 * 16,
                       curl=Entity(112 * 16, 64 * 16), moving=Entity(32 * 16, 80 * 16, 1, 0, 16),
                       falling=Entity(112 * 16, 104 * 16))
        worlds.append(replace(normal, power=2, patrol_frame=8, shot=Shot(48 * 16, 32 * 16, 32, 32, 8),
                              effect_tile=124, effect_x=48 * 16, effect_y=48 * 16, effect_timer=8))
        worlds.append(replace(normal, alive=False, stomp=16, enemy_vx=-8,
                              player=replace(normal.player, facing=32),
                              curl=replace(normal.curl, state=1, timer=16),
                              falling=replace(normal.falling, state=1, timer=16)))
        worlds.append(replace(normal, player=replace(normal.player, x=1, camera=4), enemy_x=1,
                              curl=Entity(-5 * 16, 16 * 16), moving=Entity(160 * 16, 140 * 16, 1, 0, 16)))
        checked = 0
        for world in worlds:
            self.source.reset()
            self.source.load(world)
            self.source.cpu.memory[0xc100:0xc1a0] = bytes([0xa5]) * 160
            self.source.call('PrepareScene')
            self.assertEqual(bytes(self.source.cpu.memory[0xc100:0xc1a0]), scene(world))
            self.assertEqual((self.source.cpu.d, self.source.cpu.e), (0xc1, 0xa0))
            checked += 1
        self.assertGreaterEqual(checked, 412)
        # The route ends with a live shot: its scene carries the 8x8 shot object.
        self.assertEqual(route_end.shot.ttl, 63)
        self.assertIn(107, scene(route_end))


if __name__ == '__main__':
    unittest.main()
