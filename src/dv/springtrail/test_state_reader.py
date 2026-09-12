"""Decoder, binding, renderer and rejection checks against model-built bytes.

Every fixture state is produced by `power_reference.update`, so each one is a
state the ROM can actually hold. No serial port, simulator or board is used.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'tools'), str(Path(__file__).resolve().parent)]
from n2m import generated_interfaces as abi  # noqa: E402
from n2m import springtrail_state as state  # noqa: E402
import state_support as support  # noqa: E402
from state_fake import reachable  # noqa: E402
import blocks_frames  # noqa: E402


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.image, self.binding = support.binding()

    def test_selected_ranges_are_small_and_cover_every_field(self):
        identity = self.binding.identity()
        self.assertEqual(identity['decoder'], state.DECODER_VERSION)
        self.assertEqual(identity['rom_sha256'], support.ROM_SHA256)
        # Selected ranges, not the whole store: one request instead of 32.
        self.assertLessEqual(identity['requests'], 4)
        self.assertLess(identity['bytes'], abi.WIRE_MAX_PAYLOAD)
        self.assertLess(identity['bytes'], state.WRAM_BYTES // 16)
        covered = set()
        for entry in identity['ranges']:
            self.assertLessEqual(entry['count'], abi.WIRE_MAX_PAYLOAD)
            self.assertGreaterEqual(entry['offset'], abi.GB_WRAM_START)
            covered.update(range(entry['offset'], entry['offset'] + entry['count']))
        for name, size, _signed in state.FIELDS:
            address = self.binding.symbols[name]
            self.assertTrue(set(range(address, address + size)) <= covered, name)

    def test_unsupported_rom_and_moved_layout_are_refused(self):
        symbols = dict(self.binding.symbols)
        with self.assertRaisesRegex(state.StateFailure, 'STATE_ROM_UNSUPPORTED'):
            state.Binding('0' * 64, symbols)
        moved = dict(symbols, PlayerX=symbols['PlayerX'] + 2)
        with self.assertRaisesRegex(state.StateFailure, 'STATE_LAYOUT_MISMATCH'):
            state.Binding(support.ROM_SHA256, moved)
        short = {name: value for name, value in symbols.items() if name != 'GameTimer'}
        with self.assertRaisesRegex(state.StateFailure, 'STATE_SYMBOLS_MISSING GameTimer'):
            state.Binding(support.ROM_SHA256, short)

    def test_addresses_come_from_the_package_not_from_the_decoder(self):
        text = Path(state.__file__).read_text(encoding='utf-8')
        for literal in ('0xC010', '0xc010', '49168', '0xC000', '0xc000'):
            self.assertNotIn(literal, text)
        self.assertEqual(self.binding.symbols['GameMode'], abi.GB_WRAM_START)


class DecodeTests(unittest.TestCase):
    def setUp(self):
        self.image, self.binding = support.binding()

    def decode(self, world, **kwargs):
        return state.decode(self.binding, support.chunks(self.binding, world, **kwargs))

    def test_every_decoded_field_matches_the_model_state(self):
        for name, world in support.states():
            with self.subTest(name):
                observed = self.decode(world)
                player = world.player
                self.assertEqual(observed['mode'], world.mode)
                self.assertEqual(observed['mode_name'], state.MODES[world.mode])
                self.assertEqual(observed['player']['x'], player.x)
                self.assertEqual(observed['player']['y'], player.y)
                self.assertEqual(observed['player']['vx'], player.vx)
                self.assertEqual(observed['player']['vy'], player.vy)
                self.assertEqual(observed['player']['grounded'], player.grounded)
                self.assertEqual(observed['player']['jump'], player.jump)
                self.assertEqual(observed['player']['pose'], player.pose)
                self.assertEqual(observed['player']['facing'], 'left' if player.facing else 'right')
                self.assertEqual(observed['camera'], player.camera)
                self.assertEqual(observed['enemy']['x'], world.enemy_x)
                self.assertEqual(observed['enemy']['vx'], world.enemy_vx)
                self.assertEqual(observed['enemy']['alive'], world.alive)
                self.assertEqual(observed['items']['collected'], world.collected)
                self.assertEqual(observed['items']['score'], world.score)
                self.assertEqual(observed['timer'], world.timer)
                self.assertEqual(observed['power']['state'], world.power)
                self.assertEqual(observed['shot']['ttl'], world.shot.ttl)
                self.assertEqual(observed['blocks']['states'], list(world.blocks))
                self.assertEqual(observed['hud']['word'], state.HUD_WORDS[world.mode])

    def test_to_world_round_trips_the_model_state(self):
        for name, world in support.states():
            with self.subTest(name):
                self.assertEqual(state.to_world(self.decode(world)), world)

    def test_incomplete_or_misplaced_observations_are_refused(self):
        _name, world = support.states()[1]
        complete = support.chunks(self.binding, world)
        with self.assertRaisesRegex(state.StateFailure, 'STATE_INCOMPLETE'):
            state.decode(self.binding, complete[:-1])
        truncated = [(offset, data[:-1]) for offset, data in complete]
        with self.assertRaisesRegex(state.StateFailure, 'STATE_INCOMPLETE'):
            state.decode(self.binding, truncated)
        shifted = [(offset + 1, data) for offset, data in complete]
        with self.assertRaisesRegex(state.StateFailure, 'STATE_INCOMPLETE'):
            state.decode(self.binding, shifted)

    def test_a_partly_updated_record_is_refused_not_repaired(self):
        """The exact read the acquisition boundary exists to avoid."""
        before = reachable(((129, 1), (33, 100)))
        after = support.model_update(before, 33)
        self.assertNotEqual(before.player.camera, after.player.camera)
        torn = support.chunks(self.binding, after, torn=before)
        with self.assertRaisesRegex(state.StateFailure, 'STATE_MALFORMED Camera'):
            state.decode(self.binding, torn)

    def test_the_camera_check_is_blind_wherever_the_clamp_is_active(self):
        """Pin the limit, so it is never claimed to be the tear protection.

        The camera is clamped, so near the start and at the far right it does
        not move with the player and a partly written record passes unseen.
        The paused acquisition boundary is what prevents tears; this check only
        catches the cases where the camera happens to move.
        """
        worlds = support.clamped_states()
        clamped = worlds['clamped']
        after = support.model_update(clamped, 33)
        self.assertNotEqual(clamped.player.x, after.player.x)
        self.assertEqual(clamped.player.camera, after.player.camera, 'clamp must be active')
        blind = state.decode(self.binding, support.chunks(self.binding, after, torn=clamped))
        # Accepted: the record is torn and nothing in the field values says so.
        self.assertEqual(blind['player']['x'], after.player.x)
        self.assertEqual(blind['enemy']['x'], clamped.enemy_x)
        self.assertNotEqual(blind['enemy']['x'], after.enemy_x)

        moving = worlds['moving']
        moved = support.model_update(moving, 33)
        self.assertNotEqual(moving.player.camera, moved.player.camera)
        with self.assertRaisesRegex(state.StateFailure, 'STATE_MALFORMED Camera'):
            state.decode(self.binding, support.chunks(self.binding, moved, torn=moving))

    def test_duplicate_ranges_are_refused_rather_than_resolved(self):
        _name, world = support.states()[3]
        complete = support.chunks(self.binding, world)
        other = support.chunks(self.binding, support.states()[1][1])
        with self.assertRaisesRegex(state.StateFailure, 'STATE_INCOMPLETE duplicate'):
            state.decode(self.binding, complete + other[:1])

    def test_values_outside_the_game_contract_are_refused(self):
        _name, world = support.states()[3]
        faults = {'GameMode': 9, 'EnemyVX': 3, 'Grounded': 2, 'JumpState': 7,
                  'MotionFacing': 7, 'Score': 4, 'EffectTile': 7, 'BlockState': 5}
        for symbol, value in faults.items():
            with self.subTest(symbol):
                chunks = support.chunks(self.binding, world, poke={symbol: value})
                with self.assertRaises(state.StateFailure):
                    state.decode(self.binding, chunks)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.image, self.binding = support.binding()

    def test_reconstruction_uses_the_existing_renderer_and_is_labelled(self):
        for name, world in support.states()[:4]:
            with self.subTest(name):
                observed = state.decode(self.binding, support.chunks(self.binding, world))
                pixels = state.render(observed)
                self.assertEqual(pixels, blocks_frames.image(world))
                self.assertEqual(len(pixels), 160 * 144)
                record, same = state.reconstruction(observed, {'dot': 5, 'epoch': 2,
                                                               'boundary': 'vblank-complete'})
                self.assertEqual(same, pixels)
                self.assertTrue(record['reconstructed'])
                self.assertIn('RECONSTRUCTED', record['label'])
                self.assertEqual(record['represents'], 'logical')
                self.assertEqual(record['rom_sha256'], support.ROM_SHA256)
                self.assertEqual(record['provenance']['boundary'], 'vblank-complete')
                self.assertEqual(record['decoder'], state.DECODER_VERSION)

    def test_different_states_reconstruct_to_different_images(self):
        seen = {}
        for name, world in support.states()[:4]:
            observed = state.decode(self.binding, support.chunks(self.binding, world))
            seen[name] = state.render(observed)
        self.assertEqual(len(set(seen.values())), len(seen))



class ProgressionTests(unittest.TestCase):
    def setUp(self):
        self.image, self.binding = support.binding()

    def decode(self, world, **kwargs):
        return state.decode(self.binding, support.chunks(self.binding, world, **kwargs))

    def test_current_image_cutover_rejects_old_profile(self):
        _image, symbols = support.build()
        self.assertEqual(state.DECODER_VERSION, 2)
        with self.assertRaisesRegex(state.StateFailure, 'STATE_ROM_UNSUPPORTED'):
            state.Binding('35aae757bde0ec9a15d6d6c84f14b45b451c341d2d4775f43ed8a9a762625192', symbols)
        for name in ('Lives', 'StageIndex'):
            moved = dict(symbols)
            moved[name] += 1
            with self.assertRaisesRegex(state.StateFailure, 'STATE_LAYOUT_MISMATCH'):
                state.Binding(support.ROM_SHA256, moved)

    def test_three_stages_and_lifecycle_round_trip(self):
        from dataclasses import replace
        from progress_reference import World, enter_stage, update, WON, RETRY, TIMEUP, OVER
        from hud_reference import art
        for stage in range(3):
            start = enter_stage(World(stage=stage, lives=0x12), 0)
            for mode in (1, 3, WON, RETRY, TIMEUP, OVER):
                world = replace(start, mode=mode)
                observed = self.decode(world)
                self.assertEqual(state.to_world(observed), world)
                pixels = state.render(observed)
                # Literal reset row: lives12, countdown400/300/200, stage1/2/3.
                for column, digit in ((2, 1), (3, 2), (13, 4-stage), (14, 0),
                                      (15, 0), (18, stage+1)):
                    tile = art('glyph-' + str(digit))
                    actual = b''.join(pixels[(8+y)*160+column*8:(8+y)*160+column*8+8]
                                      for y in range(8))
                    self.assertEqual(actual, tile)
                transitioned = update(world, 128)
                self.assertEqual(state.to_world(self.decode(transitioned)), transitioned)
            won = update(replace(start, mode=WON), 128)
            self.assertEqual(won.stage, stage+1 if stage < 2 else 0)
            dead = update(replace(start, mode=RETRY, lives=0), 128)
            self.assertEqual(dead.mode, OVER)

    def test_progression_and_stage_bounds_refuse_malformed_values(self):
        from dataclasses import replace
        from progress_reference import World, enter_stage
        world = enter_stage(World(stage=2), 0)
        for name, value in (('Lives', 0x1a), ('TimerLow', 0xa0), ('TimerHigh', 10),
                            ('TimerSub', 0), ('TimerSub', 41), ('Expiring', 4),
                            ('StageIndex', 3), ('GameMode', 7)):
            with self.subTest(name=name, value=value):
                with self.assertRaisesRegex(state.StateFailure, 'STATE_MALFORMED ' + name):
                    self.decode(world, poke={name: value})
        invalid = replace(world, player=replace(world.player, x=633*16, camera=480))
        with self.assertRaisesRegex(state.StateFailure, 'STATE_MALFORMED PlayerX'):
            self.decode(invalid)
        for stage, limit in enumerate((760, 632, 632)):
            current = enter_stage(World(stage=stage), 0)
            current = replace(current, player=replace(current.player, x=limit*16,
                                                      camera=(608, 480, 480)[stage]))
            self.assertEqual(state.to_world(self.decode(current)), current)

if __name__ == '__main__':
    unittest.main()
