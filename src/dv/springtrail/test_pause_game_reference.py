import unittest
import zlib
from pause_game_reference import (Check, FRAMES, PERIOD, PUBLICATIONS, TITLE_ROWS,
                                  publication_writes, restoration, samples, states)
from hud_reference import column, hud_tiles
from motion_game_reference import initial_states, state_bytes
from interactions_reference import PAUSED, PLAYING, TITLE


def write(dot, address, data):
    return f'W {(dot<<24)|(address<<8)|data:022x}'


def applied(dot, buttons):
    return f'I {(2<<72)|(dot<<8)|buttons:026x}'


class PauseScript(unittest.TestCase):
    """The frozen script and its independent consequences, before any DUT run."""

    def test_source_main_matches_all_six_current_state_and_shadow_histories(self):
        from startup_anchor import Model, build
        from entities_cases import ADDRESSES
        from entities_frames import scene
        from entities_render_check import expected_tiles
        from pause_game_reference import SCRIPT
        rom, symbols = build()
        labels = {name: address for address, name in symbols.items()}

        class Inputs(Model):
            buttons = 0

            def read(self, address):
                if address == 0xff00:
                    select = self.memory[address] & 0x30
                    low = 15
                    if not select & 0x10:
                        low &= ~self.buttons & 15
                    if not select & 0x20:
                        low &= ~(self.buttons >> 4) & 15
                    return 0xc0 | select | low
                return super().read(address)

        model = Inputs(rom)
        while model.lcd is None:
            self.assertLess(model.mcycles, 100000)
            model.mcycles += model.step()
        for index, game in enumerate(states()):
            if index:
                # Ordinary JOYP operand; execute actual publication/update/main
                # instructions. This source-model proof is not RTL execution.
                model.buttons = SCRIPT[index-1]
                model.pc = labels['ConsumeFrame']
                start = model.mcycles
                while model.pc != labels['WaitFrame']:
                    self.assertLess(model.mcycles-start, 100000)
                    model.mcycles += model.step()
            wanted = state_bytes(game, 0 if index == 0 else SCRIPT[index-1],
                                 int(index in (1, 4)))
            self.assertEqual(bytes(model.memory[a] for a in ADDRESSES), wanted, index)
            self.assertEqual(model.memory[0xc100:0xc1a0], scene(game), index)
        self.assertEqual(model.memory[0x8000:0x8ae0], expected_tiles())

    def test_states_pause_then_restart(self):
        games = states()
        self.assertEqual([g.mode for g in games], [TITLE, PLAYING, PLAYING, PAUSED, PLAYING, PLAYING])
        self.assertEqual([g.player.x//16 for g in games], [24, 25, 25, 25, 24, 24])
        self.assertEqual([g.timer for g in games], [0, 1, 2, 2, 0, 1])
        self.assertEqual([g.previous for g in games], [0, 129, 0, 128, 64, 64])
        self.assertEqual(games[4].enemy_x, 256*16)
        self.assertEqual(samples(), (129, 0, 128, 64, 64, 64))

    def test_frames_are_literal(self):
        check = Check()
        self.assertEqual(len(check.images), FRAMES)
        self.assertEqual([f'{zlib.crc32(i):08x}' for i in check.images],
                         # Row1's progression cells are new pixels in every world frame;
                         # the title frame is unchanged because it publishes before them.
                         ['b15161f6', '4a3bad02', 'fbaaf984', 'fbaaf984', '73237315', '305ee4b6'])
        # The neutral frame repeats the first world frame's pixels: STAND holds
        # until the fourth animation step. Its state bytes still differ.
        self.assertEqual(len(set(check.images)), FRAMES-1)
        games = states()
        self.assertEqual([g.player.animation for g in games], [1, 2, 3, 3, 1, 1])
        self.assertEqual([g.player.direction for g in games], [0, 1, 1, 1, 0, 0])
        self.assertNotEqual(state_bytes(games[1], 129), state_bytes(games[2], 0))

    def test_first_world_state_is_the_motion_composition_state(self):
        self.assertEqual(states()[1], initial_states()[1])

    def test_restoration_restarts_at_the_select_edge(self):
        pairs, reselect = restoration(states())
        self.assertEqual(pairs, [None, (0, 1), (2, 3), (4, 5), (0, 1), (2, 3)])
        self.assertEqual(reselect, [False, True, False, False, True, False])

    def test_publication_writes_follow_the_source_order(self):
        games = states(); pairs, reselect = restoration(games)
        title = publication_writes(games, 0, pairs, reselect)
        tiles = hud_tiles(games[0])
        self.assertEqual(title[:3], [(0xff43, 0), (0xff42, 0), (0xff40, 0x91)])
        # The progression row's six value cells follow the row0 cache, to the
        # displayed map only: the static map through the title and restoration.
        row = [(0x9822, 74), (0x9823, 76), (0x982d, 78), (0x982e, 74), (0x982f, 74), (0x9832, 75)]
        self.assertEqual(title[3:], [(0x9801+i, t) for i, t in enumerate(tiles[:6])] + [(0x9812, tiles[6])]
                         + [(0x9c01+i, t) for i, t in enumerate(tiles[:6])] + [(0x9c12, tiles[6])]
                         + row + [(0xff46, 0xc1)])
        self.assertEqual(publication_writes(games, 2, pairs, reselect)[-7:-1], row)
        first = publication_writes(games, 1, pairs, reselect)
        self.assertEqual(first[3:25], [(a, 0) for a in TITLE_ROWS])
        self.assertEqual(first[25], (0xff40, 0x91))
        self.assertEqual(first[26:58], [(0x9c40+c+y*32, v) for c in (0, 1) for y, v in enumerate(column(c))])
        restart = publication_writes(games, 4, pairs, reselect)
        self.assertEqual(restart[3], (0xff40, 0x91))
        self.assertEqual(restart[4:36], first[26:58])
        self.assertNotIn((0x98a4, 0), restart)
        self.assertEqual(len(publication_writes(games, 5, pairs, reselect)), 3+32+14+6+1)


class PauseGuards(unittest.TestCase):
    def checker(self):
        check = Check(); check.lcd = 140000
        return check

    def test_sample_order_and_restart_rewrite(self):
        check = self.checker()
        for n, mask in enumerate(samples()):
            check.line(write(check.lcd+n*PERIOD+66000, 0xc019, mask))
        self.assertEqual(len(check.samples), FRAMES)
        with self.assertRaisesRegex(AssertionError, 'PAUSE_JOYP_SAMPLE'):
            self.checker().line(write(140000+66000, 0xc019, 128))
        check = self.checker(); check.samples = [1]
        check.line(write(check.lcd+4*PERIOD+20000, 0xc019, 0))
        check.line(write(check.lcd+4*PERIOD+20100, 0xc019, 64))
        self.assertEqual(check.restores, [(4, 0), (4, 64)])
        for frame, mask in ((3, 64), (4, 128), (1, 129)):
            with self.subTest(frame=frame), self.assertRaisesRegex(AssertionError, 'PAUSE_RESTART_SAMPLE'):
                check = self.checker(); check.samples = [1]
                check.line(write(check.lcd+frame*PERIOD+20000, 0xc019, mask))

    def test_hud_cache_rejects_lost_pause(self):
        check = self.checker(); check.hud = [1, 2, 3]
        dot = check.lcd+3*PERIOD+30000
        lost = hud_tiles(states()[1])
        for offset in range(6):
            check.line(write(dot+offset, 0xc220+offset, lost[offset]))
        with self.assertRaisesRegex(AssertionError, 'PAUSE_HUD_CACHE'):
            check.line(write(dot+6, 0xc226, lost[6]))

    def test_column_cache_follows_restoration(self):
        check = self.checker(); check.cache = [0]*96
        for offset, value in enumerate(column(0)+column(1)):
            check.line(write(check.lcd+4*PERIOD+10000+offset, 0xc200+offset, value))
        self.assertEqual(len(check.cache), 128)
        with self.assertRaisesRegex(AssertionError, 'PAUSE_COLUMN_CACHE'):
            check = self.checker(); check.cache = [0]*96
            check.line(write(check.lcd+4*PERIOD+10000, 0xc200, column(6)[0]+1))
        with self.assertRaisesRegex(AssertionError, 'PAUSE_COLUMN_CACHE_ORDER'):
            check = self.checker(); check.cache = [0]*160
            check.line(write(check.lcd+6*PERIOD+10000, 0xc200, 0))

    def test_scripted_input_windows(self):
        check = self.checker()
        self.assertIsNone(check.next_input(check.lcd+59999))
        self.assertEqual(check.next_input(check.lcd+60000), 0)
        check.input_dots = [check.lcd+60100]
        self.assertEqual(check.next_input(check.lcd+PERIOD+60000), 1)
        check.input_dots += [0, 0, 0]
        self.assertIsNone(check.next_input(check.lcd+4*PERIOD+60000))
        check = self.checker()
        check.line(applied(check.lcd+60500, 129))
        with self.assertRaisesRegex(AssertionError, 'PAUSE_INPUT'):
            check.line(applied(check.lcd+PERIOD+60500, 128))
        with self.assertRaisesRegex(AssertionError, 'PAUSE_INPUT_WINDOW'):
            check.line(applied(check.lcd+PERIOD+62001, 0))

    def test_split_publication_and_incomplete_terminal(self):
        check = self.checker(); dot = check.lcd+5*PERIOD+15*456+300
        check.line(write(dot, 0xff43, 0)); check.line(write(dot+32, 0xff40, 0x93))
        self.assertEqual([row[0] for row in check.split], [5, 5])
        with self.assertRaisesRegex(AssertionError, 'PAUSE_PUBLICATION_BOUND'):
            check.line(write(check.lcd+65664+4480, 0x9801, 1))
        with self.assertRaisesRegex(AssertionError, 'PAUSE_INCOMPLETE'):
            self.checker().finish(140000+PERIOD, b'')
        check = self.checker(); check.triggers = [100]; check.ready = [200]
        with self.assertRaisesRegex(AssertionError, 'PAUSE_DMA_COMPLETION_BOUND'):
            check.line(write(check.lcd+65664+3900, 0xff46, 0xc1))
        self.assertEqual(Check().count, PUBLICATIONS)
        self.assertEqual(Check(short=True).count, 1)


if __name__ == '__main__':
    unittest.main()
