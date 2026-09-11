"""Finite ordinary operands and independent interactive-block snapshots."""
from dataclasses import replace

import blocks_reference as B
from motion_cases import ADDRESSES as MOTION_ADDRESSES, RANGES as MOTION_RANGES
from motion_reference import Player
from power_cases import state_bytes as power_bytes
from power_reference import (World, Shot, update, PLAYING, PAUSED, RETRY,
                             LARGE, THROWER, SAFE)

__all__ = ['ADDRESSES', 'RANGES', 'state_bytes', 'cases', 'parts', 'SHORT', 'SHORT_BOUND']

ADDRESSES = MOTION_ADDRESSES + list(range(0xc078, 0xc084))
RANGES = MOTION_RANGES + ((0xc078, 12),)
# The short harness runs the item hit first, so the consumer fault can corrupt
# that update's head-hit column store and be consumed by the same call.
SHORT = 2
SHORT_BOUND = 26000


def state_bytes(world, buttons=0, new_level=0):
    blocks = bytes(world.blocks) + bytes((world.coins, world.effect_tile))
    effect = ((world.effect_x & 65535).to_bytes(2, 'little')
              + (world.effect_y & 65535).to_bytes(2, 'little')
              + bytes((world.effect_timer, world.block_dirty)))
    return power_bytes(world, buttons, new_level) + blocks + effect


def playing(**player):
    return World(mode=PLAYING, player=Player(**player))


def hold(world, updates, buttons=16):
    """Advance the model only; no observed DUT value enters this function."""
    for _ in range(updates):
        world = update(world, buttons)
    return world


def under(column, **world):
    """A player one update short of head-hitting the block at that column."""
    start = replace(playing(x=column * 8 * 16, y=112 * 16), **world)
    return hold(start, 7)


def cases():
    result = []

    def add(name, world, buttons=0, kind='game', new_level=0):
        if kind == 'reset':
            after = World(mode=PLAYING, previous=buttons,
                          player=replace(Player(), previous=buttons))
            after_level = 1
        else:
            after, after_level = update(world, buttons), new_level
        out = buttons & ~3 if kind == 'game' and after.crouch else buttons
        result.append(dict(name=name, kind=kind, buttons=buttons,
                           before=state_bytes(world, buttons, new_level),
                           after=state_bytes(after, out, after_level)))
        return after

    # Block 0 at column 38: an item block releasing a mushroom into PowerUp.
    used = add('item-hit', under(38), 16)
    add('effect-rise', used, 16)
    add('item-again', hold(replace(used, player=replace(Player(), x=304 * 16)), 7), 16)
    add('effect-end', replace(used, effect_timer=1))
    add('rise-no-hit', hold(playing(x=304 * 16, y=112 * 16), 3), 16)

    # Block 1 at column 52: a brick only a large or thrower player breaks.
    add('brick-small', under(52), 16)
    broken = add('brick-large', under(52, power=LARGE), 16)
    add('brick-passes', hold(replace(broken, player=replace(Player(), x=416 * 16),
                                     power=LARGE, effect_tile=0, effect_timer=0), 7), 16)
    add('brick-no-support', replace(playing(x=416 * 16, y=64 * 16, grounded=False, jump=3),
                                    blocks=(0, B.BROKEN, 0, 0)))
    add('brick-support', playing(x=416 * 16, y=64 * 16, grounded=False, jump=3))

    # Block 2 at column 64: a coin block whose counter saturates and never scores.
    coin = add('coin-hit', under(64), 16)
    add('coin-again', hold(replace(coin, player=replace(Player(), x=512 * 16),
                                   effect_tile=0, effect_timer=0), 7), 16)
    add('coin-cap', under(64, coins=255), 16)

    # Block 3 at column 88: hidden until an ascending head scan reveals it.
    add('hidden-side', playing(x=700 * 16, y=88 * 16, grounded=False, jump=2,
                               counter=6, direction=1, speed=2), 1)
    star = add('hidden-hit', under(88), 16)
    add('hidden-revealed-side', replace(playing(x=700 * 16, y=88 * 16, grounded=False,
                                                jump=2, counter=6, direction=1, speed=2),
                                        blocks=star.blocks, invincible=200), 1)
    add('hidden-top-support', replace(playing(x=704 * 16, y=64 * 16, grounded=False, jump=3),
                                      blocks=star.blocks))

    # A shot reverses off a block exactly as it does off terrain.
    add('shot-block', replace(playing(x=280 * 16), power=THROWER,
                              shot=Shot(300 * 16, 90 * 16, 32, 32, 20)))

    # Persistence: pause holds every block byte and restart clears them.
    dirty = replace(playing(x=700 * 16, camera=608), power=LARGE, phase=SAFE,
                    phase_timer=9, blocks=(B.USED, B.BROKEN, B.USED, B.USED),
                    coins=7, effect_tile=B.GEM, effect_x=704 * 16, effect_y=70 * 16,
                    effect_timer=5, block_dirty=89, collected=15, score=4,
                    timer=42, mode=PAUSED)
    add('pause-holds', dirty, 16)
    add('reset', replace(dirty, mode=RETRY), 128, 'reset')
    return result


def parts():
    """Two bounded halves; each keeps the default wall budget."""
    all_cases = cases()
    half = len(all_cases) // 2
    return {'a': all_cases[:half], 'b': all_cases[half:]}
