"""Finite ordinary operands and independent progression snapshots.

Each case is one shared-routine call with a complete seeded state and a
complete expected state. Nothing here reads the DUT.
"""
from dataclasses import replace

from motion_reference import Player
from motion_cases import ADDRESSES as MOTION_ADDRESSES, RANGES as MOTION_RANGES
from power_cases import state_bytes as power_bytes
from progress_reference import (World, update, update_lives, enter_stage,
                                PLAYING, PAUSED, RETRY, WON, TIMEUP, OVER,
                                STAGE_TIMER_HIGH)

ADDRESSES = MOTION_ADDRESSES + list(range(0xc090, 0xc097))
RANGES = MOTION_RANGES + ((0xc090, 7),)
__all__ = ['ADDRESSES', 'RANGES', 'state_bytes', 'cases', 'parts', 'SHORT', 'SHORT_BOUND']
# The short harness runs the retry spend then one timer unit: the request fault
# is consumed by the first call's own UpdateLives.
SHORT = 2
SHORT_BOUND = 20000


def state_bytes(world, buttons=0, new_level=0):
    progress = bytes((world.lives, world.pending, world.timer_sub, world.timer_low,
                      world.timer_high, world.expiring, world.stage))
    return power_bytes(world, buttons, new_level) + progress


def playing(**fields):
    player = {k: fields.pop(k) for k in list(fields)
              if k in Player.__dataclass_fields__}
    return World(mode=PLAYING, player=Player(**player), **fields)


def timer(value, sub=1, **fields):
    """A PLAY world whose countdown reads `value` with `sub` updates left."""
    return playing(timer_sub=sub, timer_high=value // 100,
                   timer_low=((value // 10 % 10) << 4) | (value % 10), **fields)


def cases():
    result = []

    def add(name, world, buttons=0, kind='game', new_level=0):
        if kind == 'lives':
            after, after_level = update_lives(world)[0], new_level
        elif kind == 'reset':
            after, after_level = enter_stage(World(), buttons), 1
        else:
            after = update(world, buttons)
            # Only a stage entry raises NewLevel. The title start just leaves
            # TITLE for PLAY; main.asm owns that map transition, not UpdateGame.
            entered = after.mode == PLAYING and world.mode in (RETRY, TIMEUP, WON, OVER, PAUSED)
            after_level = 1 if entered else new_level
        out = buttons & ~3 if kind == 'game' and after.crouch else buttons
        result.append(dict(name=name, kind=kind, buttons=buttons,
                           before=state_bytes(world, buttons, new_level),
                           after=state_bytes(after, out, after_level)))
        return after

    # Transitions first so the short harness covers a life request and a tick.
    add('retry-spend', World(mode=RETRY, lives=0x02), 128)
    add('timer-unit', timer(400))

    # Countdown boundaries.
    add('timer-subdivision', timer(400, sub=2))
    add('timer-below-100', timer(100))
    add('timer-below-50', timer(50))
    zero = add('timer-zero', timer(1))
    consumed = add('timer-consumed', zero)
    add('timer-after-consumed', replace(consumed, mode=PLAYING, timer_sub=1))
    add('timer-paused', replace(timer(300), mode=PAUSED))
    add('timer-retry-idle', replace(timer(300), mode=RETRY))
    add('timer-title-idle', replace(timer(300), mode=0))

    # Life requests through the shared consumer.
    add('lives-no-request', playing(), 0, 'lives')
    add('lives-gain', replace(playing(), lives=0x02, pending=1), 0, 'lives')
    add('lives-gain-carry', replace(playing(), lives=0x09, pending=1), 0, 'lives')
    add('lives-saturate', replace(playing(), lives=0x99, pending=1), 0, 'lives')
    add('lives-spend', replace(playing(), lives=0x10, pending=0xFF), 0, 'lives')
    add('lives-last', replace(playing(), lives=0x00, pending=0xFF), 0, 'lives')

    # Mode transitions and what survives them.
    add('retry-hold', replace(World(mode=RETRY, lives=0x02), previous=128), 128)
    add('retry-idle', World(mode=RETRY, lives=0x02), 16)
    add('retry-none-left', World(mode=RETRY, lives=0x00), 128)
    add('retry-keeps-stage', World(mode=RETRY, lives=0x03, stage=2), 128)
    add('timeup-spend', World(mode=TIMEUP, lives=0x02, stage=1, expiring=0xFF), 128)
    add('over-reset', World(mode=OVER, lives=0x00, stage=2), 128)
    add('over-idle', World(mode=OVER, lives=0x00, stage=2), 16)
    add('clear-advance', World(mode=WON, lives=0x02, stage=0, collected=15, score=4), 128)
    add('clear-advance-last', World(mode=WON, lives=0x01, stage=1), 128)
    add('clear-final', World(mode=WON, lives=0x05, stage=2), 128)
    add('clear-idle', World(mode=WON, lives=0x02, stage=0), 16)
    add('pause-select-reset', World(mode=PAUSED, lives=0x00, stage=2), 192)
    add('title-start', World(lives=0x02), 128)

    # Stage geometry: goal, item, camera, patrol and terrain per stage.
    add('stage1-goal', playing(stage=1, x=608 * 16), 0, 'game', 0)
    add('stage1-goal-short', playing(stage=1, x=600 * 16))
    add('stage1-item', playing(stage=1, x=80 * 16, y=72 * 16))
    add('stage1-right-bound', playing(stage=1, x=632 * 16, counter=6, direction=1, speed=2), 1)
    add('stage2-goal', playing(stage=2, x=608 * 16))
    add('stage2-enemy-high', playing(stage=2, enemy_x=328 * 16 - 8))
    add('stage2-enemy-low', playing(stage=2, enemy_x=272 * 16 + 8, enemy_vx=-8))
    add('stage2-gap', playing(stage=2, x=31 * 8 * 16, y=140 * 16, grounded=False, jump=3, pose=4))
    add('stage0-unchanged', playing(x=252 * 16))

    # A dirty world proves the reset scope.
    dirty = replace(playing(x=700 * 16, camera=608, pose=3), stage=2, lives=0x07,
                    pending=0xFF, timer_sub=3, timer_low=0x21, timer_high=0x01,
                    expiring=1, collected=15, score=4, mode=RETRY)
    add('reset', dirty, 128, 'reset')
    return result


def parts():
    """Two bounded halves; each keeps the default wall budget."""
    all_cases = cases()
    half = len(all_cases) // 2
    return {'a': all_cases[:half], 'b': all_cases[half:]}
