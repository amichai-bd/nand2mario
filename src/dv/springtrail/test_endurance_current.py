"""Current lifecycle source/model anchors; no simulator or board observations."""
import unittest
from dataclasses import replace

from entities_reference import World, update
from progress_reference import RETRY, row_tiles
from startup_anchor import Model, build


class Lifecycle(unittest.TestCase):
    def test_retry_countdown_over_and_released_restart_match_source(self):
        rom, symbols = build()
        labels = {name: address for address, name in symbols.items()}
        cpu = Model(rom)
        while cpu.lcd is None:
            cpu.mcycles += cpu.step()

        def call(name):
            cpu.sp = 0xdffc
            cpu.memory[0xdffc:0xdffe] = bytes([0xff, 0x7f])
            cpu.pc = labels[name]
            start = cpu.mcycles
            while cpu.pc != 0x7fff:
                self.assertLess(cpu.mcycles - start, 20000)
                cpu.mcycles += cpu.step()

        def step(buttons):
            nonlocal world
            cpu.memory[0xc019] = buttons
            call('UpdateGame')
            call('PrepareProgress')
            world = update(world, buttons)
            self.assertEqual(tuple(cpu.memory[0xc097:0xc09d]), row_tiles(world))
            self.assertEqual(cpu.memory[0xc000], world.mode)
            self.assertEqual(tuple(cpu.memory[0xc090:0xc097]),
                             (world.lives, world.pending, world.timer_sub, world.timer_low,
                              world.timer_high, world.expiring, world.stage))
            return tuple(cpu.memory[0xc097:0xc09d])

        world = World()
        for death, lives, mode in ((1, 1, 1), (2, 0, 1), (3, 0, 6)):
            cpu.memory[0xc000] = RETRY
            cpu.memory[0xc024] = 0
            world = replace(world, mode=RETRY, previous=0)
            self.assertEqual(step(128), (74, 74 + lives, 78, 74, 74, 75))
            self.assertEqual((world.lives, world.mode), (lives, mode))
            if death == 1:
                for _ in range(40):
                    row = step(0)
                self.assertEqual(row, (74, 75, 77, 144, 144, 75))
        step(0)
        self.assertEqual(step(128), (74, 76, 78, 74, 74, 75))
        self.assertEqual((world.mode, world.lives, world.stage), (1, 2, 0))


    def test_current_frame_route_matches_625_source_calls(self):
        from entities_cases import ADDRESSES, state_bytes
        from frame_proofs import samples, games
        rom, symbols = build()
        labels = {name: address for address, name in symbols.items()}
        cpu = Model(rom)
        while cpu.lcd is None:
            cpu.mcycles += cpu.step()
        for k, buttons in enumerate(samples(), 1):
            cpu.memory[0xc019] = buttons
            cpu.sp = 0xdffc
            cpu.memory[0xdffc:0xdffe] = bytes([0xff, 0x7f])
            cpu.pc = labels['UpdateGame']
            start = cpu.mcycles
            while cpu.pc != 0x7fff:
                self.assertLess(cpu.mcycles - start, 20000)
                cpu.mcycles += cpu.step()
            # This calls UpdateGame directly, so main's publication never clears
            # NewLevel after the actual stage entry at474; compare that ownership.
            expected = state_bytes(games()[k], buttons, int(k >= 474))
            self.assertEqual(bytes(cpu.memory[a] for a in ADDRESSES), expected, k)


class ScheduledFrames(unittest.TestCase):
    def test_row_read_offsets_derive_from_current_irq_and_halt_path(self):
        from endurance import DIRECTION_READ, ACTION_READ
        reads = []
        class InputModel(Model):
            def read(self, address):
                if address == 0xff00:
                    reads.append(4 * (self.mcycles + 2))  # LDH accepted data cycle
                    return 255
                return super().read(address)
        rom, _ = build()
        cpu = InputModel(rom)
        while cpu.memory[cpu.pc] != 0x76:
            cpu.mcycles += cpu.step()
        resume = cpu.pc + 1
        cpu.sp -= 2
        cpu.memory[cpu.sp:cpu.sp+2] = resume.to_bytes(2, 'little')
        cpu.pc = 0x40
        # T4-aligned PPU rise misses T3: wake4 + five-M-cycle entry20.
        cpu.mcycles = 6
        while len(reads) < 2:
            cpu.mcycles += cpu.step()
        self.assertEqual(reads, [DIRECTION_READ, ACTION_READ])
        self.assertEqual(reads, [316, 388])

    def test_row_order_multiple_events_and_late_input(self):
        from endurance import Schedule, LCD, PERIOD
        vblank = LCD + 65664
        for events, expected in (([(315,33)],33), ([(316,33)],32),
                                 ([(350,33)],32), ([(388,33)],0),
                                 ([(4559,33)],0), ([(310,1),(350,32)],33)):
            schedule = Schedule()
            for dot, mask in events:
                schedule.buttons(vblank+dot,mask)
            self.assertEqual(schedule.frame(1), {World()})
            self.assertEqual({w.previous for w in schedule.frame(2)}, {expected})
            self.assertEqual({w.previous for w in schedule.frame(3)}, {events[-1][1]})
        after = Schedule()
        after.buttons(LCD + PERIOD, 128)
        self.assertEqual({w.mode for w in after.frame(2)}, {0})
        self.assertEqual({w.mode for w in after.frame(3)}, {1})

    def test_mixed_frame_cannot_borrow_pixels_from_two_reachable_states(self):
        from endurance import Schedule, LCD, check_pixels
        from entities_frames import image
        from test_endurance import packed
        states = set()
        for dot in (LCD+65663, LCD+65664+400):
            schedule = Schedule()
            schedule.buttons(dot, 128)
            states.update(schedule.frame(41))
        frames = list({image(w) for w in states})
        self.assertEqual(len(frames), 2)
        first, second = frames
        differing = [i for i in range(23040) if first[i] != second[i]]
        mixed = bytearray(first)
        for i in differing[::2]:
            mixed[i] = second[i]
        self.assertNotIn(bytes(mixed), frames)
        with self.assertRaisesRegex(AssertionError, 'ENDURANCE_PIXELS'):
            check_pixels(packed(mixed), 'mixed', states)
        for frame in frames:
            self.assertEqual(check_pixels(packed(frame), 'whole', states), 23040)

    def test_all_90_cycles_follow_lives_countdown_over_and_reset(self):
        import hashlib
        import tempfile
        from pathlib import Path
        from endurance import run, PLANS
        from test_endurance import Fake
        from progress_reference import timer_value
        client = Fake()
        with tempfile.TemporaryDirectory() as directory:
            result = run(client, bytes(32768), Path(directory)/'run', epoch=6,
                         cycles=PLANS['full'], rom_sha256=hashlib.sha256(bytes(32768)).hexdigest(),
                         clock=client.clock, sleep=client.tick)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(len(result['samples']), 195)
        self.assertEqual(len(result['lifecycles']), 3)
        rows = [(s['name'], w) for s, w in zip(result['samples'], client.sampled)]
        restart = {name:w for name,w in rows if name.endswith('-restart')}
        self.assertEqual([(restart[f'{i:03d}-restart'].mode, restart[f'{i:03d}-restart'].lives)
                          for i in range(4)], [(1,1),(1,0),(6,0),(1,2)])
        self.assertTrue(any(timer_value(w) < 400 for _,w in rows if w.mode == 1))
        self.assertTrue(any(w.mode == 6 for _,w in rows))
        self.assertFalse(client.running)
        self.assertEqual(client.mask, 0)




class RoutinePlan(unittest.TestCase):
    def test_thirty_cycles_include_three_actual_pause_resume_pairs(self):
        import hashlib, tempfile
        from pathlib import Path
        from endurance import run, PLANS, CAPS
        from test_endurance import Fake
        self.assertEqual(PLANS, {'short': 2, 'routine': 30, 'full': 90})
        self.assertEqual(CAPS, {'short': 300, 'routine': 780, 'full': 1980})
        client = Fake()
        with tempfile.TemporaryDirectory() as directory:
            result = run(client, bytes(32768), Path(directory)/'run', epoch=6,
                         cycles=PLANS['routine'], rom_sha256=hashlib.sha256(bytes(32768)).hexdigest(),
                         clock=client.clock, sleep=client.tick)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['planned_seconds'], 600)
        self.assertGreaterEqual(result['continuous_seconds'], 600)
        self.assertEqual(len(result['samples']), 75)
        self.assertEqual(len(result['lifecycles']), 3)
        pairs = [(s['name'], w.mode, w.lives) for s,w in zip(result['samples'],client.sampled)
                 if s['name'].endswith(('-pause','-resume'))]
        self.assertEqual(pairs, [(f'{i:03d}-{name}', mode, 1) for i in (0,12,24)
                                for name,mode in (('pause',3),('resume',1))])
        self.assertFalse(client.running)
        self.assertEqual(client.mask, 0)
