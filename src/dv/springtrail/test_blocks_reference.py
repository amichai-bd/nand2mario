"""One test per rule of the frozen interactive-block contract."""
from dataclasses import replace
import unittest

import blocks_reference as B
from power_reference import (World, Player, update, PLAYING, PAUSED, RETRY,
                             LARGE, THROWER, GROW, SMALL)


def playing(**player):
    return World(mode=PLAYING, player=Player(**player))


def rise(world, updates, buttons=16):
    for _ in range(updates):
        world = update(world, buttons)
    return world


class TableTests(unittest.TestCase):
    def test_table_is_four_blocks_in_rows_ten_and_eleven(self):
        self.assertEqual(len(B.BLOCKS), 4)
        self.assertEqual([b[0] for b in B.BLOCKS], [38, 52, 64, 88])
        self.assertTrue(all(b[1] == 10 for b in B.BLOCKS))

    def test_only_a_brick_carries_no_content(self):
        for _column, _row, kind, content in B.BLOCKS:
            self.assertEqual(content == B.NONE, kind == B.BRICK)

    def test_no_block_cell_is_terrain_solid(self):
        from movement_reference import solid
        for column, row, _kind, _content in B.BLOCKS:
            for cell in ((column, row), (column + 1, row),
                         (column, row + 1), (column + 1, row + 1)):
                self.assertFalse(solid(*cell), cell)

    def test_find_covers_the_two_by_two_footprint_only(self):
        self.assertEqual(B.find(38, 10), 0)
        self.assertEqual(B.find(39, 11), 0)
        self.assertIsNone(B.find(40, 10))
        self.assertIsNone(B.find(38, 12))
        self.assertIsNone(B.find(38, 9))


class SolidityTests(unittest.TestCase):
    def test_item_block_is_solid_intact_and_used(self):
        for state in (B.INTACT, B.USED):
            self.assertTrue(B.solid((state, 0, 0, 0), 38, 11))

    def test_broken_brick_is_passable(self):
        self.assertTrue(B.solid((0, B.INTACT, 0, 0), 52, 10))
        self.assertFalse(B.solid((0, B.BROKEN, 0, 0), 52, 10))

    def test_intact_hidden_block_is_solid_only_to_an_ascending_scan(self):
        self.assertFalse(B.solid((0, 0, 0, B.INTACT), 88, 11, False))
        self.assertTrue(B.solid((0, 0, 0, B.INTACT), 88, 11, True))

    def test_revealed_hidden_block_is_solid_to_every_scan(self):
        self.assertTrue(B.solid((0, 0, 0, B.USED), 88, 11, False))

    def test_cells_outside_the_table_are_never_block_solid(self):
        self.assertFalse(B.solid(B.reset(), 30, 10))


class AppearanceTests(unittest.TestCase):
    def test_state_selects_the_documented_tile_base(self):
        self.assertEqual(B.appearance((B.INTACT, 0, 0, 0), 0), B.SEALED)
        self.assertEqual(B.appearance((B.USED, 0, 0, 0), 0), B.USED_TILE)
        self.assertEqual(B.appearance((0, B.INTACT, 0, 0), 1), B.CRACK)
        self.assertEqual(B.appearance((0, B.BROKEN, 0, 0), 1), 0)
        self.assertEqual(B.appearance((0, 0, 0, B.INTACT), 3), 0)
        self.assertEqual(B.appearance((0, 0, 0, B.USED), 3), B.REVEAL)

    def test_column_tiles_split_the_block_into_its_two_sub_columns(self):
        self.assertEqual(B.column_tiles(B.reset(), 38),
                         {10: B.SEALED, 11: B.SEALED + 2})
        self.assertEqual(B.column_tiles(B.reset(), 39),
                         {10: B.SEALED + 1, 11: B.SEALED + 3})

    def test_blank_states_write_nothing_over_the_terrain_column(self):
        self.assertEqual(B.column_tiles((0, B.BROKEN, 0, 0), 52), {})
        self.assertEqual(B.column_tiles(B.reset(), 88), {})

    def test_columns_without_a_block_are_untouched(self):
        self.assertEqual(B.column_tiles(B.reset(), 30), {})

    def test_appearance_and_solidity_agree_on_every_state(self):
        # A visible block is solid and an invisible one is passable, for every
        # kind and state, except the deliberately invisible intact hidden block
        # that only an ascending head scan sees.
        for index, (column, row, kind, _content) in enumerate(B.BLOCKS):
            for state in (B.INTACT, B.USED, B.BROKEN):
                states = tuple(state if i == index else B.INTACT for i in range(4))
                visible = bool(B.appearance(states, index))
                solid = B.solid(states, column, row, False)
                if kind == B.HIDDEN and state == B.INTACT:
                    self.assertFalse(visible or solid)
                else:
                    self.assertEqual(visible, solid)


class ResolveTests(unittest.TestCase):
    def test_no_hit_changes_nothing(self):
        self.assertEqual(B.resolve(B.reset(), 0, SMALL, None),
                         (B.reset(), 0, 0, 0, 0, None))

    def test_a_cell_outside_the_table_changes_nothing(self):
        self.assertEqual(B.resolve(B.reset(), 0, SMALL, (30, 10))[0], B.reset())

    def test_item_block_releases_its_mushroom_once(self):
        states, coins, tile, x, y, grant = B.resolve(B.reset(), 0, SMALL, (38, 11))
        self.assertEqual((states[0], coins, tile, x, y, grant),
                         (B.USED, 0, B.LEAF, 304, 80, 'power'))
        self.assertEqual(B.resolve(states, coins, SMALL, (38, 11))[5], None)

    def test_coin_block_saturates_its_counter(self):
        self.assertEqual(B.resolve(B.reset(), 0, SMALL, (64, 10))[1], 1)
        self.assertEqual(B.resolve(B.reset(), 255, SMALL, (64, 10))[1], 255)

    def test_hidden_block_releases_its_star(self):
        states, _coins, tile, _x, _y, grant = B.resolve(B.reset(), 0, SMALL, (88, 11))
        self.assertEqual((states[3], tile, grant), (B.USED, B.GEM, 'star'))

    def test_small_player_cannot_break_a_brick(self):
        self.assertEqual(B.resolve(B.reset(), 0, SMALL, (52, 11)),
                         (B.reset(), 0, 0, 0, 0, None))

    def test_large_and_thrower_break_a_brick(self):
        for power in (LARGE, THROWER):
            states, _coins, tile, x, y, grant = B.resolve(B.reset(), 0, power, (52, 11))
            self.assertEqual((states[1], tile, x, y, grant),
                             (B.BROKEN, B.SHARDS, 416, 80, None))


class WorldTests(unittest.TestCase):
    def test_a_changed_block_marks_its_columns_for_republication(self):
        world = rise(playing(x=304 * 16, y=112 * 16), 8)
        self.assertEqual(world.block_dirty, 39)
        broken = rise(replace(playing(x=416 * 16, y=112 * 16), power=LARGE), 8)
        self.assertEqual(broken.block_dirty, 53)
        # A small player's inert brick bump marks nothing.
        self.assertEqual(rise(playing(x=416 * 16, y=112 * 16), 8).block_dirty, 0)

    def test_jump_under_block_zero_grows_the_player_and_pops_a_leaf(self):
        world = rise(playing(x=304 * 16, y=112 * 16), 8)
        self.assertEqual(world.player.y, 96 * 16)
        self.assertEqual(world.blocks, (B.USED, 0, 0, 0))
        self.assertEqual((world.power, world.phase), (LARGE, GROW))
        self.assertEqual((world.effect_tile, world.effect_timer,
                          world.effect_x, world.effect_y),
                         (B.LEAF, B.EFFECT_UPDATES, 304 * 16, 80 * 16))

    def test_the_effect_rises_one_pixel_per_update_and_then_clears(self):
        world = rise(playing(x=304 * 16, y=112 * 16), 8)
        later = rise(world, 4, 0)
        self.assertEqual(later.effect_y, (80 - 4) * 16)
        self.assertEqual(rise(world, B.EFFECT_UPDATES, 0).effect_tile, 0)

    def test_a_small_player_bumps_brick_one_without_changing_it(self):
        world = rise(playing(x=416 * 16, y=112 * 16), 8)
        self.assertEqual(world.player.y, 96 * 16)
        self.assertEqual(world.blocks, B.reset())
        self.assertEqual(world.effect_tile, 0)

    def test_a_large_player_breaks_brick_one_and_then_passes_through(self):
        start = replace(playing(x=416 * 16, y=112 * 16), power=LARGE)
        world = rise(start, 8)
        self.assertEqual(world.blocks, (0, B.BROKEN, 0, 0))
        self.assertEqual(world.effect_tile, B.SHARDS)
        again = rise(replace(world, player=replace(Player(), x=416 * 16),
                             effect_timer=0, effect_tile=0), 8)
        self.assertLess(again.player.y, 96 * 16)

    def test_the_hidden_block_passes_a_walker_and_reveals_to_a_head_hit(self):
        walk = playing(x=700 * 16, y=88 * 16, grounded=False, jump=2)
        self.assertEqual(rise(walk, 1, 1).blocks, B.reset())
        world = rise(playing(x=704 * 16, y=112 * 16), 8)
        self.assertEqual(world.blocks, (0, 0, 0, B.USED))
        self.assertEqual(world.invincible, 248)

    def test_a_used_block_stays_solid_and_grants_nothing_again(self):
        world = rise(playing(x=512 * 16, y=112 * 16), 8)
        self.assertEqual((world.blocks[2], world.coins), (B.USED, 1))
        again = rise(replace(world, player=replace(Player(), x=512 * 16)), 8)
        self.assertEqual((again.player.y, again.coins), (96 * 16, 1))

    def test_coins_never_change_the_displayed_score(self):
        world = rise(playing(x=512 * 16, y=112 * 16), 8)
        self.assertEqual((world.coins, world.score), (1, 0))

    def test_pause_freezes_block_state_and_the_effect(self):
        world = rise(playing(x=304 * 16, y=112 * 16), 8)
        paused = update(replace(world, mode=PAUSED), 0)
        self.assertEqual((paused.blocks, paused.effect_timer, paused.effect_y),
                         (world.blocks, world.effect_timer, world.effect_y))

    def test_restart_restores_every_block_and_clears_the_coins(self):
        world = rise(playing(x=304 * 16, y=112 * 16), 8)
        fresh = update(replace(world, mode=RETRY, coins=7), 128)
        self.assertEqual((fresh.blocks, fresh.coins, fresh.effect_tile,
                          fresh.effect_timer, fresh.block_dirty),
                         (B.reset(), 0, 0, 0, 0))

    def test_a_broken_brick_no_longer_supports_a_falling_player(self):
        above = replace(playing(x=416 * 16, y=80 * 16 - 16 * 16, grounded=False, jump=3),
                        blocks=(0, B.INTACT, 0, 0))
        self.assertTrue(update(above, 0).player.grounded)
        broken = replace(above, blocks=(0, B.BROKEN, 0, 0))
        self.assertFalse(update(broken, 0).player.grounded)


if __name__ == '__main__':
    unittest.main()
