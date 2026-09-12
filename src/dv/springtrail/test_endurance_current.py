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
