"""Literal expectations for the progression contract, frozen before the code.

One test per contract rule. Every expected value is read from
wiki/src/sw/springtrail/PROGRESS.md, never from the DUT or from a build.
"""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import progress_cases
import progress_reference as g
from movement_reference import (STAGE_BASE, STAGE_COLUMNS, STAGE_X_MAX,
                                STAGE_CAMERA_MAX, solid)
from motion_reference import Player
from power_reference import STAGE_GOAL_X, STAGE_ITEMS, STAGE_ENEMY_HI, STAGE_ENEMY_LO


def play(value=400, sub=1, **fields):
    return g.World(mode=g.PLAYING, timer_sub=sub, timer_high=value // 100,
                   timer_low=((value // 10 % 10) << 4) | (value % 10), **fields)


class StageTableTests(unittest.TestCase):
    def test_three_stages_fill_one_collision_page(self):
        self.assertEqual(STAGE_BASE, (0, 96, 176))
        self.assertEqual(STAGE_COLUMNS, (96, 80, 80))
        self.assertEqual(STAGE_BASE[2] + STAGE_COLUMNS[2], 256)
        for stage in range(3):
            self.assertEqual(STAGE_X_MAX[stage], STAGE_COLUMNS[stage] * 8 - 8)
            self.assertEqual(STAGE_CAMERA_MAX[stage], STAGE_COLUMNS[stage] * 8 - 160)

    def test_stage_zero_keeps_every_original_bound(self):
        self.assertEqual((STAGE_X_MAX[0], STAGE_CAMERA_MAX[0]), (760, 608))
        self.assertEqual(STAGE_GOAL_X[0], 736)
        self.assertEqual(STAGE_ITEMS[0], ((96, 88), (264, 72), (464, 88), (656, 80)))
        self.assertEqual((STAGE_ENEMY_LO[0], STAGE_ENEMY_HI[0]), (240 * 16, 296 * 16))

    def test_terrain_rules_equal_the_literal_world(self):
        """The independent rule model must equal every committed world cell."""
        rows = []
        for line in (ROOT / 'src/sw/springtrail/world.asm').read_text(encoding='utf-8').splitlines():
            body = line.split(';')[0].strip()
            if body.startswith('DB '):
                rows.append([int(part) for part in body[3:].split(',')])
        self.assertEqual(len(rows), 18)
        self.assertTrue(all(len(row) == 256 for row in rows))
        for stage in range(3):
            for column in range(STAGE_COLUMNS[stage]):
                for row in range(18):
                    expected = 11 if solid(column, row, stage) else 0
                    self.assertEqual(rows[row][STAGE_BASE[stage] + column], expected,
                                     (stage, column, row))

    def test_every_stage_goal_stands_on_solid_ground(self):
        for stage in range(3):
            self.assertTrue(solid(STAGE_GOAL_X[stage] // 8, 16, stage), stage)


class TimerTests(unittest.TestCase):
    def test_subdivision_alone_changes_nothing_else(self):
        after = g.update(play(400, sub=2), 0)
        self.assertEqual((after.timer_sub, g.timer_value(after), after.expiring), (1, 400, 0))

    def test_one_unit_reloads_forty_updates(self):
        after = g.update(play(400), 0)
        self.assertEqual((after.timer_sub, g.timer_value(after), after.expiring),
                         (g.SUBDIVISION, 399, 0))

    def test_grade_thresholds(self):
        self.assertEqual([g.grade(v) for v in (999, 100, 99, 50, 49, 1, 0)],
                         [0, 0, 1, 1, 2, 2, 3])
        self.assertEqual(g.update(play(100), 0).expiring, 1)
        self.assertEqual(g.update(play(50), 0).expiring, 2)
        self.assertEqual(g.update(play(1), 0).expiring, 3)

    def test_zero_is_reached_then_consumed_on_the_next_update(self):
        zero = g.update(play(1), 0)
        self.assertEqual((g.timer_value(zero), zero.expiring, zero.mode), (0, 3, g.PLAYING))
        consumed = g.update(zero, 0)
        self.assertEqual((consumed.expiring, consumed.mode), (0xFF, g.TIMEUP))

    def test_zero_never_underflows(self):
        after = g.update(replace(play(0, sub=1), expiring=0xFF), 0)
        self.assertEqual((g.timer_value(after), after.timer_sub, after.expiring),
                         (0, g.SUBDIVISION, 0xFF))

    def test_bcd_borrow_across_the_hundreds(self):
        after = g.update(play(100), 0)
        self.assertEqual((after.timer_high, after.timer_low), (0x00, 0x99))

    def test_timer_is_frozen_outside_play(self):
        for mode in (0, g.PAUSED, g.RETRY, g.WON, g.TIMEUP, g.OVER):
            before = replace(play(300, sub=1), mode=mode)
            after = g.update(before, 0)
            self.assertEqual((after.timer_sub, g.timer_value(after)), (1, 300), mode)


class LivesTests(unittest.TestCase):
    def test_no_request_changes_nothing(self):
        world = g.World(lives=0x42)
        after, alive = g.update_lives(world)
        self.assertEqual((after.lives, after.pending, alive), (0x42, 0, True))

    def test_gain_uses_packed_bcd_and_clears_the_request(self):
        for before, expected in ((0x02, 0x03), (0x09, 0x10), (0x19, 0x20), (0x98, 0x99)):
            after, alive = g.update_lives(g.World(lives=before, pending=1))
            self.assertEqual((after.lives, after.pending, alive), (expected, 0, True))

    def test_gain_saturates_at_ninety_nine(self):
        after, alive = g.update_lives(g.World(lives=0x99, pending=1))
        self.assertEqual((after.lives, after.pending, alive), (0x99, 0, True))

    def test_spend_uses_packed_bcd(self):
        for before, expected in ((0x02, 0x01), (0x10, 0x09), (0x01, 0x00)):
            after, alive = g.update_lives(g.World(lives=before, pending=0xFF))
            self.assertEqual((after.lives, after.pending, alive), (expected, 0, True))

    def test_spend_at_zero_ends_the_game_without_wrapping(self):
        after, alive = g.update_lives(g.World(lives=0x00, pending=0xFF))
        self.assertEqual((after.lives, after.pending, after.mode, alive),
                         (0x00, 0, g.OVER, False))


class TransitionTests(unittest.TestCase):
    def test_retry_spends_one_life_and_re_enters_the_same_stage(self):
        after = g.update(g.World(mode=g.RETRY, lives=0x02, stage=1, collected=15, score=4), 128)
        self.assertEqual((after.lives, after.mode, after.stage), (0x01, g.PLAYING, 1))
        self.assertEqual((after.collected, after.score, g.timer_value(after)), (0, 0, 300))

    def test_time_up_transition_matches_retry(self):
        source = g.World(mode=g.TIMEUP, lives=0x02, stage=1, expiring=0xFF)
        self.assertEqual(g.update(source, 128),
                         g.update(replace(source, mode=g.RETRY), 128))

    def test_retry_without_a_life_ends_the_game(self):
        after = g.update(g.World(mode=g.RETRY, lives=0x00, stage=2), 128)
        self.assertEqual((after.lives, after.mode, after.stage), (0x00, g.OVER, 2))

    def test_clearing_a_stage_advances_and_reloads_its_timer(self):
        first = g.update(g.World(mode=g.WON, lives=0x02, stage=0), 128)
        self.assertEqual((first.stage, first.mode, g.timer_value(first), first.lives),
                         (1, g.PLAYING, 300, 0x02))
        # The press must be released first; a held A cannot cross two clears.
        second = g.update(replace(first, mode=g.WON, previous=0), 128)
        self.assertEqual((second.stage, g.timer_value(second)), (2, 200))

    def test_clearing_the_last_stage_resets_the_game(self):
        after = g.update(g.World(mode=g.WON, lives=0x05, stage=2), 128)
        self.assertEqual((after.stage, after.lives, after.mode, g.timer_value(after)),
                         (0, g.RESET_LIVES, g.PLAYING, 400))

    def test_game_over_and_paused_select_both_reset(self):
        dirty = dict(lives=0x00, stage=2, collected=15, score=4)
        over = g.update(g.World(mode=g.OVER, **dirty), 128)
        select = g.update(g.World(mode=g.PAUSED, **dirty), 192)
        for after in (over, select):
            self.assertEqual((after.stage, after.lives, after.collected, after.score),
                             (0, g.RESET_LIVES, 0, 0))

    def test_a_held_press_cannot_cross_two_transitions(self):
        held = g.World(mode=g.RETRY, lives=0x02, previous=128)
        after = g.update(held, 128)
        self.assertEqual((after.mode, after.lives), (g.RETRY, 0x02))

    def test_entering_a_stage_stores_the_sampled_buttons(self):
        after = g.update(g.World(mode=g.WON, stage=0), 144)
        self.assertEqual((after.previous, after.player.previous), (144, 144))

    def test_a_waiting_transition_leaves_the_player_untouched(self):
        before = g.World(mode=g.RETRY, lives=0x02, player=Player(x=99 * 16, previous=8))
        after = g.update(before, 16)
        self.assertEqual((after.mode, after.player), (g.RETRY, before.player))
        self.assertEqual(after.previous, 16)


class StageWorldTests(unittest.TestCase):
    def test_each_stage_goal_clears_its_own_stage(self):
        for stage in range(3):
            player = Player(x=STAGE_GOAL_X[stage] * 16)
            after = g.update(g.World(mode=g.PLAYING, stage=stage, player=player), 0)
            self.assertEqual(after.mode, g.WON, stage)

    def test_a_player_short_of_the_goal_keeps_playing(self):
        after = g.update(g.World(mode=g.PLAYING, stage=1, player=Player(x=600 * 16)), 0)
        self.assertEqual(after.mode, g.PLAYING)

    def test_stage_bounds_stop_the_player_and_the_camera(self):
        after = g.update(g.World(mode=g.PLAYING, stage=1,
                                 player=Player(x=632 * 16, counter=6, direction=1, speed=2)), 1)
        self.assertEqual((after.player.x, after.player.camera), (632 * 16, 480))

    def test_each_stage_patrols_its_own_enemy_range(self):
        for stage in range(3):
            high = g.update(g.World(mode=g.PLAYING, stage=stage,
                                    enemy_x=STAGE_ENEMY_HI[stage] - 8), 0)
            self.assertEqual((high.enemy_x, high.enemy_vx), (STAGE_ENEMY_HI[stage], -8), stage)
            low = g.update(g.World(mode=g.PLAYING, stage=stage,
                                   enemy_x=STAGE_ENEMY_LO[stage] + 8, enemy_vx=-8), 0)
            self.assertEqual((low.enemy_x, low.enemy_vx), (STAGE_ENEMY_LO[stage], 8), stage)

    def test_each_stage_collects_its_own_items(self):
        for stage in range(3):
            x, y = STAGE_ITEMS[stage][0]
            after = g.update(g.World(mode=g.PLAYING, stage=stage,
                                     player=Player(x=x * 16, y=(y - 8) * 16)), 0)
            self.assertEqual((after.collected, after.score), (1, 1), stage)


class PrecedenceTests(unittest.TestCase):
    def test_a_consumed_time_up_precedes_the_goal(self):
        player = Player(x=STAGE_GOAL_X[0] * 16)
        after = g.update(replace(play(0, sub=40, expiring=3), player=player), 0)
        self.assertEqual(after.mode, g.TIMEUP)

    def test_a_fall_precedes_the_goal(self):
        player = Player(x=STAGE_GOAL_X[0] * 16, y=140 * 16, grounded=False, jump=3)
        after = g.update(replace(play(400, sub=40), player=player), 0)
        self.assertEqual(after.mode, g.RETRY)

    def test_a_consumed_time_up_leaves_the_world_alone(self):
        before = replace(play(0, sub=40, expiring=3), player=Player(x=300 * 16))
        after = g.update(before, 1)
        self.assertEqual(after.player.x, before.player.x)
        self.assertEqual((after.mode, after.expiring), (g.TIMEUP, 0xFF))


class CaseSetTests(unittest.TestCase):
    def test_every_case_has_a_complete_seeded_and_expected_state(self):
        cases = progress_cases.cases()
        self.assertEqual(len(progress_cases.ADDRESSES),
                         sum(count for _, count in progress_cases.RANGES))
        for case in cases:
            self.assertEqual(len(case['before']), len(progress_cases.ADDRESSES), case['name'])
            self.assertEqual(len(case['after']), len(progress_cases.ADDRESSES), case['name'])
        names = [case['name'] for case in cases]
        self.assertEqual(len(names), len(set(names)))
        halves = progress_cases.parts()
        self.assertEqual(len(halves['a']) + len(halves['b']), len(cases))

    def test_the_short_pair_covers_a_life_request_and_a_timer_unit(self):
        short = progress_cases.cases()[:progress_cases.SHORT]
        self.assertEqual([case['name'] for case in short], ['retry-spend', 'timer-unit'])



class StageShotBounds(unittest.TestCase):
    def test_stage_edges_remove_at_boundary_but_keep_inside(self):
        from power_reference import _shot, Shot
        for stage, edge in ((0, 760), (1, 632), (2, 632)):
            for start, ttl in ((edge - 3, 9), (edge - 2, 0)):
                with self.subTest(stage=stage, start=start):
                    world = g.World(stage=stage, alive=False,
                                    shot=Shot(start*16, 32*16, 32, 32, 10))
                    self.assertEqual(_shot(world).shot.ttl, ttl)

    def test_cpu_operand_cases_include_every_inside_and_edge_snapshot(self):
        rows = {row['name']: row for row in progress_cases.parts()['b']}
        ttl_index = progress_cases.ADDRESSES.index(0xc077)
        for stage in range(3):
            for suffix, ttl in (('inside', 9), ('edge', 0)):
                row = rows[f'stage{stage}-shot-{suffix}']
                self.assertEqual(row['kind'], 'game')
                self.assertEqual(len(row['before']), 55)
                self.assertEqual(len(row['after']), 55)
                self.assertEqual(row['after'][ttl_index], ttl)


if __name__ == '__main__':
    unittest.main()
