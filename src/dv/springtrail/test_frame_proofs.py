"""Frozen-script and host-runner checks; synthetic results are not frame evidence."""
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from n2m import generated_interfaces as abi
import blocks_reference as B
from hud_reference import entering
from motion_frames import image as terrain_image
from power_reference import TITLE, PLAYING, RETRY, WON, SMALL
from frame_proofs import (run, games, samples, anchor, history, checkpoint, plan_captures, unpack,
                          image, SCRIPT, CAPTURES, EXPECTED, PLANS, FIRST_VBLANK, RESTORE_FRAMES,
                          SHOWCASE, SHOWCASE_CHECKPOINTS, LCD, PERIOD, START, INTACT_BLOCKS, update)

ZERO_ROM = bytes(32768)
ZERO_SHA = hashlib.sha256(ZERO_ROM).hexdigest()
VISIBLE = 65664


def packed(pixels):
    return bytes(sum(pixels[i+j] << (2*j) for j in range(4)) for i in range(0, 23040, 4))


class Fake:
    """A paused endpoint whose frames follow only the dots at which INPUT was applied."""

    def __init__(self, fault=None):
        self.dot = 0; self.epoch = 6; self.mask = 0; self.loaded = False
        self.sequence = 4242; self.uncertain = False; self.fault = fault
        self.calls = []; self.events = []; self.wall = 0.

    def clock(self):
        return self.wall

    def call(self, name):
        self.calls.append(name); self.sequence += 1; self.wall += .01

    def identify(self):
        return dict(build_id='fake')

    def load(self, rom):
        self.call('load'); self.wall += 1
        assert len(rom) == 32768
        self.dot = 0; self.epoch += 2; self.mask = 0; self.loaded = True; self.events = []
        return {'verified_bytes': len(rom)}

    def read_host(self, addr):
        self.call('read')
        return {abi.HOST_REG_DOT_LO: self.dot & 0xffffffff, abi.HOST_REG_DOT_HI: self.dot >> 32,
                abi.HOST_REG_RETIRE_LO: (self.dot//7) & 0xffffffff, abi.HOST_REG_RETIRE_HI: (self.dot//7) >> 32,
                abi.HOST_REG_STATE: abi.STATE_PAUSED, abi.HOST_REG_IMAGE_VALID: 1,
                abi.HOST_REG_INPUT_SOURCE: abi.INPUT_SOURCE_UART, abi.HOST_REG_INPUT: self.mask,
                abi.HOST_REG_INPUT_EFFECTIVE: self.mask}[addr]

    def control(self, name, value=None):
        self.call(name)
        if name == 'INPUT':
            self.mask = value
            self.events.append((self.dot, value))
            if self.fault == 'input' and len(self.events) == 3:
                return {'dot': self.dot+1}
        return {'dot': self.dot}

    def run_dots(self, count):
        self.call('RUN_DOTS')
        if self.fault == 'uncertain' and self.dot > LCD+30*PERIOD:
            self.uncertain = True
            raise RuntimeError('lost reply')
        self.dot += count
        executed = count-1 if self.fault == 'count' and self.dot > LCD+5*PERIOD else count
        return dict(dot=self.dot, executed=executed, reason=abi.WIRE_RUN_DOTS_COUNT)

    def game(self, frame):
        """State displayed by source frame `frame`: the masks each VBlank sampled."""
        state, mask, index = START, 0, 0
        for vblank in range(frame-1):
            sample = LCD+vblank*PERIOD+VISIBLE
            while index < len(self.events) and self.events[index][0] < sample:
                mask = self.events[index][1]
                index += 1
            state = update(state, mask)
        return state

    def snapshot(self):
        self.call('snapshot'); self.wall += .8
        assert self.loaded
        seq = (self.dot-LCD-VISIBLE)//PERIOD
        meta = dict(epoch=self.epoch, seq=seq, dot=LCD+seq*PERIOD+143*456+300, size=5760)
        data = bytearray(packed(image(self.game(seq))))
        if self.fault == 'pixel' and seq > 10: data[-1] ^= 64
        if self.fault == 'epoch': meta['epoch'] += 1
        if self.fault == 'stale' and seq > 10: meta['seq'] -= 1; meta['dot'] -= PERIOD
        if self.fault == 'dot': meta['dot'] -= 456
        return meta, bytes(data)


def short(client, root, plan='short', **extra):
    return run(client, ZERO_ROM, root, epoch=6, plan=plan, rom_sha256=ZERO_SHA,
               clock=client.clock, **extra)


class ScriptTests(unittest.TestCase):
    def test_literal_states_match_the_model(self):
        states = games()
        for name, k in CAPTURES:
            self.assertEqual(anchor(states[k]), EXPECTED[name], name)
        self.assertEqual(len(samples()), FIRST_VBLANK+sum(count for _, count in SCRIPT))
        self.assertEqual(samples()[-1], 0)

    def test_transitions_happen_where_the_script_says(self):
        states = games()
        modes = [(k, states[k].mode) for k in range(1, len(states)) if states[k].mode != states[k-1].mode]
        self.assertEqual(modes, [(3, PLAYING), (473, WON), (474, PLAYING), (604, RETRY), (605, PLAYING)])
        self.assertEqual(states[0].mode, TITLE)
        cameras = [k for k in range(1, len(states))
                   if states[k-1].player.camera == 0 and states[k].player.camera > 0]
        self.assertEqual(cameras[0], 36)
        self.assertEqual(entering(states[98].player.camera, states[99].player.camera), 32)
        self.assertTrue(all(entering(states[k-1].player.camera, states[k].player.camera) in (None, *range(32))
                            for k in range(1, 99)), 'the first captured entering column must be new to the ring')
        self.assertEqual((states[205].player.camera, states[206].player.camera), (255, 256))
        self.assertEqual((states[440].player.camera, states[441].player.camera), (607, 608))
        self.assertTrue(states[604].player.fell, 'RETRY comes from the first gap')
        self.assertEqual(states[604].score, 0)

    def test_restart_captures_follow_complete_ring_restoration(self):
        states = games()
        for restart, capture in ((474, 493), (605, 625)):
            self.assertEqual(states[restart].timer, 0)
            self.assertGreaterEqual(capture-restart, RESTORE_FRAMES)
            for k in range(restart, capture+1):
                self.assertEqual((states[k].mode, states[k].player.x, states[k].player.camera),
                                 (PLAYING, 24*16, 0))

    def test_history_is_the_declared_input_runs(self):
        self.assertEqual(history(0), [])
        self.assertEqual(history(3), [(0, 2), (161, 1)])
        self.assertEqual(history(473)[:3], [(0, 2), (161, 1), (33, 96)])
        self.assertEqual(sum(count for _, count in history(625)), 625)

    def test_captured_images_are_distinct_and_pixel_sensitive(self):
        states = games()
        frames = {name: image(states[k]) for name, k in CAPTURES}
        # Both restarts settle at spawn with the patrol offscreen: same pixels,
        # different timers and enemy phase. Every other capture is distinct.
        self.assertEqual(frames['won-restart'], frames['retry-restart'])
        self.assertEqual(len(set(frames.values())), len(frames)-1)
        for name, pixels in frames.items():
            data = bytearray(packed(pixels))
            data[-1] ^= 64
            self.assertNotEqual(unpack(bytes(data)), pixels, name)

    def test_route_touches_no_block(self):
        # Every capture literal carries the block layer's state; the route
        # leaves it at reset, so a bump or a pickup on the script fails here.
        for state in games():
            self.assertEqual((state.blocks, state.power, state.coins, state.effect_tile),
                             (INTACT_BLOCKS, SMALL, 0, 0))
            self.assertTrue(state.alive)
        self.assertEqual(INTACT_BLOCKS, B.reset())
        for name in EXPECTED:
            self.assertEqual(EXPECTED[name][8:], (INTACT_BLOCKS, SMALL))

    def test_second_gap_tap_walks_under_the_brick(self):
        # The brick at column 52 stands beside the second gap (46..49). A held
        # jump there lands against its side and the route never reaches the
        # goal; the one-VBlank tap lands at x 399 and walks under it.
        states = games()
        air = [k for k in range(226, 280) if states[k].player.y != 1792]
        self.assertEqual((air[0], air[-1]), (228, 252))
        landed = states[air[-1]+1].player
        self.assertEqual((landed.x, landed.y), (399*16, 1792))
        self.assertLess(landed.x + 128, 52*8*16)
        held = list(SCRIPT)
        self.assertEqual((held[6], held[7]), ((49, 1), (33, 127)))
        held[6], held[7] = (49, 12), (33, 116)
        state, stalled = START, None
        for k, mask in enumerate([0]*FIRST_VBLANK + [m for m, n in held for _ in range(n)], 1):
            before, state = state, update(state, mask)
            if state.mode == PLAYING and state.player.y != 1792 and state.player.x == before.player.x:
                stalled = (k, state.player.x//16, state.player.y//16)
                break
        self.assertEqual(stalled, (260, 408, 81))

    def test_block_layer_is_the_only_difference_from_the_terrain_model(self):
        # The block-aware image differs from the terrain-only image in the
        # 8x8 cells of the blocks in view and nowhere else. On the board the
        # first such capture, scroll-wrap, showed exactly this 16x16 cell.
        states = games()
        for name, k in CAPTURES:
            state = states[k]
            camera = state.player.camera
            cells = set()
            for bx, by, _kind, _content in B.BLOCKS:
                if not B.appearance(state.blocks, B.BLOCKS.index((bx, by, _kind, _content))):
                    continue
                for cx in (bx, bx+1):
                    for cy in (by, by+1):
                        sx = cx*8 - camera
                        if -8 < sx < 160:
                            cells.add((sx, cy*8))
            wanted, plain = image(state), terrain_image(state)
            differing = {i for i in range(23040) if wanted[i] != plain[i]}
            allowed = {(sy+y)*160+sx+x for sx, sy in cells for y in range(8) for x in range(8)
                       if 0 <= sx+x < 160}
            self.assertLessEqual(differing, allowed, name)
            for sx, sy in cells:
                cell = {(sy+y)*160+sx+x for y in range(8) for x in range(8) if 0 <= sx+x < 160}
                self.assertTrue(differing & cell, f'{name}: block cell at {sx},{sy} unchanged')
            if name == 'scroll-wrap':
                self.assertEqual(len(differing), 256)
                self.assertEqual(differing, {y*160+x for y in range(80, 96) for x in range(48, 64)})
                self.assertIn(12848, differing)
            else:
                self.assertEqual(differing, set(), name)

    def test_plans_and_checkpoints(self):
        self.assertEqual([name for name, _ in plan_captures('short')][-1], PLANS['short'])
        self.assertEqual(len(plan_captures('full')), len(CAPTURES))
        # The title (C2) and spawn (C5) checkpoints of the current image.
        # Bind to the independently assembled current startup, not an old ROM's dot.
        from startup_anchor import build, derive
        image, symbols = build()
        source_lcd = derive(image, symbols)['lcd']
        self.assertEqual(checkpoint(2), source_lcd + 2 * 70224 + 4096)
        self.assertEqual(checkpoint(5), source_lcd + 5 * 70224 + 4096)
        with self.assertRaisesRegex(AssertionError, 'FRAME_PLAN'):
            plan_captures('long')


class RunnerTests(unittest.TestCase):
    def test_short_and_full_pass_and_end_neutral(self):
        for plan, count in (('short', 4), ('full', len(CAPTURES))):
            with self.subTest(plan=plan), tempfile.TemporaryDirectory() as directory:
                client = Fake()
                result = short(client, Path(directory)/'run', plan)
                self.assertEqual(result['status'], 'PASS')
                self.assertEqual([c['name'] for c in result['captures']], [n for n, _ in plan_captures(plan)])
                self.assertEqual(client.mask, 0)
                self.assertEqual(result['epoch'], 8)
                self.assertEqual(result['final_dot'], checkpoint(plan_captures(plan)[-1][1]+2))
                self.assertNotIn('RUN', client.calls)
                self.assertEqual(client.calls.count('load'), 1)
                for capture in result['captures']:
                    self.assertEqual(capture['checked_pixels'], 23040)
                    self.assertEqual(capture['metadata']['seq'], capture['frame'])
                if plan == 'full':
                    self.assertEqual([m for _, m in client.events],
                                     [0]+[mask for i, mask in enumerate(samples()) if i >= FIRST_VBLANK and mask != samples()[i-1]]+[0])
                    self.assertEqual([(dot-LCD-4096) % PERIOD for dot, _ in client.events[1:]], [0]*(len(client.events)-1))

    def test_showcase_sampling_adds_frames_without_changing_the_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            plain, sampled = Fake(), Fake()
            root = Path(directory)
            base = short(plain, root/'plain', 'full')
            result = short(sampled, root/'sampled', 'full', showcase=True)
            self.assertEqual(result['status'], 'PASS')
            # The frozen history is untouched: same inputs, checkpoints and captures.
            self.assertEqual(sampled.events, plain.events)
            self.assertEqual(result['final_dot'], base['final_dot'])
            self.assertEqual(result['checkpoints'], base['checkpoints'])
            self.assertEqual([c['name'] for c in result['captures']],
                             [c['name'] for c in base['captures']])
            self.assertEqual([c['crc32'] for c in result['captures']],
                             [c['crc32'] for c in base['captures']])
            self.assertEqual(base['samples'], [])
            self.assertFalse(base['showcase'])
            # Every listed checkpoint is sampled once, in order, and checked whole.
            self.assertEqual([s['game'] for s in result['samples']], list(SHOWCASE))
            self.assertEqual(list(SHOWCASE), sorted(set(SHOWCASE)))
            self.assertEqual(sorted(SHOWCASE_CHECKPOINTS), [k+2 for k in SHOWCASE])
            states = games()
            for entry in result['samples']:
                self.assertEqual(entry['checked_pixels'], 23040)
                self.assertEqual(entry['frame'], entry['game']+1)
                self.assertEqual(entry['metadata']['seq'], entry['frame'])
                self.assertEqual(entry['pause_dot'], checkpoint(entry['game']+2))
                self.assertEqual(entry['name'], f'showcase-{entry["game"]:04d}')
                self.assertEqual(tuple(entry['anchor']), anchor(states[entry['game']]))
                self.assertEqual(entry['mask'], samples()[entry['game']-1] if entry['game'] else 0)
                self.assertTrue((root/'sampled'/entry['file']).is_file())
                self.assertEqual(unpack((root/'sampled'/entry['file']).read_bytes()), image(states[entry['game']]))
            # The eight checkpoints that are also captures reuse the read frame.
            shared = sorted(set(SHOWCASE) & {k for _, k in CAPTURES})
            self.assertEqual(shared, [0, 3, 36, 206, 441, 473, 493, 604])
            files = {c['game']: c['file'] for c in result['captures']}
            for entry in result['samples']:
                if entry['game'] in shared:
                    self.assertEqual(entry['file'], files[entry['game']])
                else:
                    self.assertTrue(entry['file'].startswith('showcase-'))
            self.assertEqual(sampled.calls.count('snapshot'),
                             plain.calls.count('snapshot')+len(SHOWCASE)-len(shared))
            # The samples read as a playthrough: the title, the spawn, four
            # jumps that leave and return to the ground, WON, the restart and
            # the fall into the first gap ending in RETRY.
            modes = [states[k].mode for k in SHOWCASE]
            self.assertEqual((modes[0], modes[1]), (TITLE, PLAYING))
            self.assertEqual([m for i, m in enumerate(modes) if i == 0 or m != modes[i-1]],
                             [TITLE, PLAYING, WON, PLAYING, RETRY])
            ys = [states[k].player.y for k in SHOWCASE]
            arcs = [(a, b) for a, b in ((100, 144), (156, 166), (232, 248), (359, 397))]
            for launch, last in arcs:
                inside = [states[k].player.y for k in SHOWCASE if launch <= k <= last]
                self.assertTrue(all(y < 1792 for y in inside), (launch, last))
                before = max(k for k in SHOWCASE if k < launch)
                self.assertEqual(states[before].player.y, 1792, launch)
            self.assertEqual(ys[SHOWCASE.index(151)], 1792)
            self.assertEqual(min(ys), 1200)
            self.assertGreater(states[601].player.y, 1792, 'the fall is sampled before RETRY')
            self.assertEqual(SHOWCASE[-1], 604)

    def test_showcase_sampling_requires_the_full_history(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(AssertionError, 'FRAME_SHOWCASE_PLAN'):
                short(Fake(), Path(directory)/'run', 'short', showcase=True)

    def test_failures_never_pass_and_clean_up(self):
        for fault in ('pixel', 'epoch', 'stale', 'dot', 'input', 'count', 'uncertain'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                client = Fake(fault)
                root = Path(directory)/'run'
                with self.assertRaises((AssertionError, RuntimeError)):
                    short(client, root, 'full')
                result = json.loads((root/'result.json').read_text())
                self.assertEqual(result['status'], 'FAIL')
                self.assertEqual(client.uncertain, fault == 'uncertain')
                if fault != 'uncertain':
                    self.assertEqual(client.mask, 0)
                    self.assertIn('cleanup', result)

    def test_wall_cap_stops_before_the_next_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Fake()
            root = Path(directory)/'run'
            with self.assertRaisesRegex(AssertionError, 'FRAME_WALL_CAP'):
                short(client, root, 'short', deadline=1.5)
            self.assertEqual(client.mask, 0)

    def test_wrong_rom_before_any_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            client = Fake()
            root = Path(directory)/'run'
            with self.assertRaisesRegex(AssertionError, 'FRAME_ROM'):
                run(client, ZERO_ROM, root, epoch=6, plan='short', rom_sha256='0'*64)
            with self.assertRaisesRegex(AssertionError, 'FRAME_ROM'):
                run(client, bytes(32767), root, epoch=6, plan='short', rom_sha256=ZERO_SHA)
            self.assertEqual(client.calls, [])
            self.assertFalse(root.exists())


if __name__ == '__main__':
    unittest.main()
