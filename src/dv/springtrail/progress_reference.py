"""Independent per-update model of the approved progression contract.

Every rule here is read from wiki PROGRESS.md, never from the DUT. The world
step, the contact classes and the motion rules stay with their own contracts;
this module adds the lives, the countdown timer and the stage lifecycle.
"""
from dataclasses import dataclass, replace

from motion_reference import Player
from power_reference import (World as PowerWorld, world_update, _timers,
                             TITLE, PLAYING, RETRY, PAUSED, WON,
                             STAGE_ENEMY_START)

TIMEUP, OVER = 5, 6
# Stage entry timer values as packed BCD hundreds: 400, 300, 200.
STAGE_TIMER_HIGH = (0x04, 0x03, 0x02)
SUBDIVISION = 40
RESET_LIVES = 0x02
MAX_LIVES = 0x99
STAGES = 3

__all__ = ['World', 'TITLE', 'PLAYING', 'RETRY', 'PAUSED', 'WON', 'TIMEUP', 'OVER',
           'STAGE_TIMER_HIGH', 'SUBDIVISION', 'RESET_LIVES', 'MAX_LIVES', 'STAGES',
           'timer_value', 'grade', 'tick_timer', 'check_time_up', 'update_lives',
           'enter_stage', 'reset', 'update', 'row_tiles', 'glyph']


@dataclass(frozen=True)
class World(PowerWorld):
    """The power world plus the progression bytes at C090..C096."""
    lives: int = RESET_LIVES
    pending: int = 0
    timer_sub: int = SUBDIVISION
    timer_low: int = 0x00
    timer_high: int = STAGE_TIMER_HIGH[0]
    expiring: int = 0


def _decimal(value):
    """One packed BCD byte as its decimal value; inputs are always valid BCD."""
    return (value >> 4) * 10 + (value & 15)


def _packed(value):
    return ((value // 10) << 4) | (value % 10)


def timer_value(world):
    """The displayed countdown as a plain integer 0..999."""
    return (world.timer_high & 15) * 100 + _decimal(world.timer_low)


def grade(value):
    """0 at 100 or above, 1 below 100, 2 below 50, 3 at zero."""
    if value >= 100:
        return 0
    if value == 0:
        return 3
    return 1 if value >= 50 else 2


def tick_timer(world):
    """One PLAY update of the countdown. The value never underflows."""
    sub = (world.timer_sub - 1) & 255
    if sub:
        return replace(world, timer_sub=sub)
    value = timer_value(world)
    if value == 0:
        return replace(world, timer_sub=SUBDIVISION)
    value -= 1
    return replace(world, timer_sub=SUBDIVISION, timer_high=value // 100,
                   timer_low=_packed(value % 100), expiring=grade(value))


def check_time_up(world):
    """Consume a zero grade raised by an earlier update; True ends the update."""
    if world.expiring != 3:
        return world, False
    return replace(world, expiring=0xFF, mode=TIMEUP), True


def update_lives(world):
    """Apply and clear one pending request. False means the game ended."""
    request = world.pending
    if request == 0:
        return world, True
    if request == 0xFF:
        if world.lives == 0:
            return replace(world, pending=0, mode=OVER), False
        return replace(world, pending=0, lives=_packed(_decimal(world.lives) - 1)), True
    if world.lives == MAX_LIVES:
        return replace(world, pending=0), True
    return replace(world, pending=0, lives=_packed(_decimal(world.lives) + 1)), True


def enter_stage(world, buttons):
    """Stage entry. Lives and the stage index are the only carried state."""
    return World(mode=PLAYING, previous=buttons,
                 player=replace(Player(), previous=buttons),
                 enemy_x=STAGE_ENEMY_START[world.stage], enemy_vx=8,
                 stage=world.stage, lives=world.lives, pending=0,
                 timer_sub=SUBDIVISION, timer_low=0x00,
                 timer_high=STAGE_TIMER_HIGH[world.stage], expiring=0)


def reset(world, buttons):
    """A reset clears the lives and the stage, then enters stage 0."""
    return enter_stage(World(stage=0, lives=RESET_LIVES), buttons)


def _waiting(world, buttons):
    """A transition with no A edge stores only the shared previous byte."""
    return replace(world, previous=buttons)


def update(world, buttons):
    """Flow decisions precede world updates; one held A never crosses two."""
    if not isinstance(buttons, int) or not 0 <= buttons <= 255:
        raise ValueError('buttons must be a byte')
    edges = buttons & ~world.previous
    if world.mode == PAUSED:
        if edges & 64:
            return reset(world, buttons)
        return replace(world, mode=PLAYING if edges & 128 else PAUSED, previous=buttons,
                       player=replace(world.player, previous=buttons))
    if world.mode in (RETRY, TIMEUP):
        if not edges & 128:
            return _waiting(world, buttons)
        spent, alive = update_lives(replace(world, pending=0xFF))
        return enter_stage(spent, buttons) if alive else _waiting(spent, buttons)
    if world.mode == WON:
        if not edges & 128:
            return _waiting(world, buttons)
        if world.stage >= STAGES - 1:
            return reset(world, buttons)
        return enter_stage(replace(world, stage=world.stage + 1), buttons)
    if world.mode == OVER:
        return reset(world, buttons) if edges & 128 else _waiting(world, buttons)
    if world.mode == TITLE:
        if not edges & 128:
            return _waiting(world, buttons)
        world = replace(world, mode=PLAYING)
    elif edges & 128:
        return replace(world, mode=PAUSED, previous=buttons,
                       player=replace(world.player, previous=buttons))
    # Contract order: power timers, time-up death, countdown, then input. The
    # grade is raised on one update and consumed at the top of the next.
    world, expired = check_time_up(_timers(world))
    if expired:
        return replace(world, previous=buttons,
                       player=replace(world.player, previous=buttons))
    return world_update(tick_timer(world), buttons, timers=False)


# Approved glyph identifiers; digits 0..4 are the loaded font and 5..9 follow
# the block terrain copies at VRAM 140. The life and clock icons are static.
LIFE_TILE, CLOCK_TILE = 147, 148


def glyph(digit):
    return 74 + digit if digit < 5 else 135 + digit


def row_tiles(world):
    """The six prepared HUD row1 value cells, in publication order."""
    return (glyph(world.lives >> 4), glyph(world.lives & 15),
            glyph(world.timer_high & 15), glyph(world.timer_low >> 4),
            glyph(world.timer_low & 15), glyph(world.stage + 1))
