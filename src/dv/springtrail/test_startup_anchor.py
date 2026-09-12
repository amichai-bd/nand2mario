"""The startup anchor derives from the built image and stays frozen at LCD.

The model's timing rules are checked against the CPU contract's own examples
(MAS_cpu, "Time, bus and retirement"); the current image is then derived term
by term and must give `motion_game_reference.LCD`. A longer startup path moves
the derived dot, so this file fails at level 0 before any board session.
"""
import unittest

from endurance import require_anchor, LCD
from startup_anchor import Model, build, derive

# main.asm's startup order: the header stub, Start's inline stores and loops,
# then each CALL through PublishScene; the LCDC write follows.
STARTUP = ('reset fetch', 'header', 'Start', 'InitSceneDMA', 'InitGame', 'ClearObjects',
           'CopyTiles', 'CopyMap', 'InitHUD', 'InitMotionArt', 'InitBlockArt', 'PrepareScene',
           'PrepareHUD', 'PrepareMap', 'PublishHUD', 'PublishScene')
# Independent hand counts of two terms, from the listing:
# CopyTiles (attributed by nearest preceding label, so its own three setup
#   loads belong to Start and CopyMap's belong to it): 1184 x (LD A,[DE] 2,
#   INC DE 2, LD [HL+],A 2, DEC BC 2, LD A,B 1, OR A,C 1, JR NZ 3) minus the
#   final untaken JR, plus LD DE/LD HL/LD BC 9: 15400 M-cycles.
# InitBlockArt: the count PR #418's reviewer made, 5183 M-cycles.
HAND = {'CopyTiles': 4 * 15400, 'InitBlockArt': 4 * 5183}


def rom(*pieces):
    image = bytearray(32768)
    for address, data in pieces:
        image[address:address + len(data)] = data
    return bytes(image)


LCD_ON = bytes([0x3e, 0x91, 0xe0, 0x40])  # LD A,$91 ; LDH [$FF40],A


class ContractTests(unittest.TestCase):
    def test_reset_fetch_and_jump_match_the_cpu_contract(self):
        # MAS_cpu: with 0100:C3 00 02, dots 4, 8, 12 fetch, 16 is idle, 20 fetches 0200.
        model = Model(rom((0x100, bytes([0xc3, 0x00, 0x02]))))
        model.mcycles += model.step()
        self.assertEqual((model.pc, 4 * model.mcycles), (0x200, 20))
        # NOP at 0100 retires at dot 8 and a following JP at dot 24.
        model = Model(rom((0x100, bytes([0x00, 0xc3, 0x00, 0x02]))))
        model.mcycles += model.step()
        self.assertEqual(4 * model.mcycles, 8)
        model.mcycles += model.step()
        self.assertEqual((model.pc, 4 * model.mcycles), (0x200, 24))

    def test_the_write_commits_inside_its_instruction(self):
        # Initial fetch 1, LD A,d8 2, then LDH's operand fetch and write: 4 x 5 = 20.
        self.assertEqual(derive(rom((0x100, LCD_ON)))['lcd'], 20)
        # NOP; JP 0200; LD A; LDH: 1 + 1 + 4 + 2 + 2 = 10 M-cycles.
        image = rom((0x100, bytes([0x00, 0xc3, 0x00, 0x02])), (0x200, LCD_ON))
        result = derive(image, {0x200: 'Code'})
        self.assertEqual(result['lcd'], 40)
        self.assertEqual(result['terms'], [('reset fetch', 4), ('header', 20), ('Code', 16)])

    def test_conditional_branches_cost_by_outcome(self):
        # XOR A,A 1 sets Z; JR NZ falls through 2; JR Z taken 3; RET NZ untaken 2.
        code = bytes([0xaf, 0x20, 0x00, 0x28, 0x00, 0xc0]) + LCD_ON
        self.assertEqual(derive(rom((0x100, code)))['lcd'], 4 * (1 + 1 + 2 + 3 + 2 + 2 + 2))
        # CALL 6 and RET 4 nest one level; the callee's cost carries its name.
        code = bytes([0xcd, 0x00, 0x02]) + LCD_ON
        result = derive(rom((0x100, code), (0x200, bytes([0x00, 0xc9]))), {0x200: 'Sub'})
        self.assertEqual(result['lcd'], 4 * (1 + 6 + 1 + 4 + 2 + 2))
        self.assertEqual(dict(result['terms'])['Sub'], 4 * (6 + 1 + 4))

    def test_a_runaway_image_stops(self):
        with self.assertRaisesRegex(AssertionError, 'ANCHOR_RUNAWAY'):
            derive(bytes(32768), limit=10000)


class ImageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image, cls.symbols = build()
        cls.result = derive(cls.image, cls.symbols)

    def test_the_current_image_derives_the_frozen_anchor(self):
        self.assertEqual(self.result['lcd'], LCD)
        self.assertEqual(sum(dots for _, dots in self.result['terms']), LCD)
        self.assertEqual(tuple(name for name, _ in self.result['terms']), STARTUP)
        terms = dict(self.result['terms'])
        for name, dots in HAND.items():
            self.assertEqual(terms[name], dots, name)
        self.assertEqual(require_anchor(self.image, self.symbols)['lcd'], LCD)

    def test_a_longer_startup_moves_the_anchor_and_is_refused(self):
        # ClearObjects: LD HL,$FE00 / LD B,160; one more byte costs one more
        # LD [HL+],A / DEC B / JR NZ iteration, 6 M-cycles.
        loop = bytes([0x21, 0x00, 0xfe, 0x06, 0xa0])
        at = self.image.index(loop)
        moved = self.image[:at + 4] + bytes([0xa1]) + self.image[at + 5:]
        self.assertEqual(derive(moved, self.symbols)['lcd'], LCD + 24)
        with self.assertRaisesRegex(AssertionError, 'ENDURANCE_ANCHOR'):
            require_anchor(moved, self.symbols)


if __name__ == '__main__':
    unittest.main()
