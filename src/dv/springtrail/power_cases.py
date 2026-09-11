"""Finite ordinary operands and independent contact/power snapshots."""
from dataclasses import replace

from motion_reference import Player
from motion_cases import ADDRESSES, RANGES
from interaction_cases import state_bytes as game_bytes
from power_reference import (World, Shot, update, power_up, grant_star,
                             LARGE, THROWER, GROW, HURT, SAFE, PLAYING, PAUSED, RETRY)

__all__ = ['ADDRESSES', 'RANGES', 'state_bytes', 'cases', 'parts', 'SHORT', 'SHORT_BOUND']
# The short harness runs crouch then stomp: a masked-direction fault is consumed
# by the first call and the stomp exercises the enemy contact path.
SHORT = 2
SHORT_BOUND = 20000


def state_bytes(world, buttons=0, new_level=0):
    p, s = world.player, world.shot
    motion = bytes((p.counter, p.direction, p.speed, p.phase, p.animation, p.pose,
                    p.jump, p.index, p.saved, p.facing, new_level))
    power = bytes((world.power, world.phase, world.phase_timer, world.invincible,
                   world.throw, int(world.alive), int(world.crouch)))
    shot = ((s.x & 65535).to_bytes(2, 'little') + (s.y & 65535).to_bytes(2, 'little')
            + bytes((s.vx & 255, s.vy & 255, s.ttl)))
    return game_bytes(world, buttons) + motion + power + shot


def playing(**player):
    return World(mode=PLAYING, player=Player(**player))


def cases():
    result = []

    def add(name, world, buttons=0, kind='game', new_level=0):
        if kind == 'reset':
            after = World(mode=PLAYING, previous=buttons,
                          player=replace(Player(), previous=buttons))
            after_level = 1
        elif kind == 'power':
            after, after_level = power_up(world), new_level
        elif kind == 'star':
            after, after_level = grant_star(world), new_level
        else:
            after, after_level = update(world, buttons), new_level
        # Crouch masks Left/Right in the sampled byte that the routine leaves behind.
        out = buttons & ~3 if kind == 'game' and after.crouch else buttons
        result.append(dict(name=name, kind=kind, buttons=buttons,
                           before=state_bytes(world, buttons, new_level),
                           after=state_bytes(after, out, after_level)))
        return after

    # The short harness runs crouch then stomp; the consumer fault corrupts the
    # crouch update's masked Buttons store, which the same call's motion consumes.
    moving = replace(playing(counter=6, direction=1, speed=2, pose=2), power=LARGE)
    crouch = add('crouch', moving, 9)
    stomp = add('stomp', playing(x=252*16, y=104*16, grounded=False, jump=3, pose=4))
    add('bounce', stomp)
    add('deep-hit-small', playing(x=252*16, y=108*16, grounded=False, jump=3, pose=4))
    walk = playing(x=252*16, counter=6, direction=1, speed=2)
    add('walk-hit-small', walk, 1)
    hit = add('walk-hit-large', replace(walk, power=LARGE), 1)
    counted = add('hurt-count', hit)
    add('hurt-suppressed', replace(counted, enemy_x=252*16))
    add('hurt-to-safe', replace(counted, phase_timer=1, enemy_x=252*16))
    add('safe-suppressed', replace(counted, phase=SAFE, phase_timer=40, enemy_x=252*16))
    add('safe-to-normal', replace(counted, phase=SAFE, phase_timer=1))
    add('normal-hit-after', replace(counted, phase=0, phase_timer=0, enemy_x=252*16))
    add('thrower-hit', replace(walk, power=THROWER, throw=5), 1)
    star = add('star-grant', playing(x=252*16), 0, 'star')
    contact = add('star-contact', star)
    add('star-count', contact)
    large = add('power-small', playing(), 0, 'power')
    add('grow-count', large)
    add('grow-end', replace(large, phase_timer=1))
    thrower = add('power-large', replace(large, phase=0, phase_timer=0), 0, 'power')
    add('power-thrower', thrower, 0, 'power')
    add('power-during-safe', replace(playing(), phase=SAFE, phase_timer=50), 0, 'power')
    add('crouch-small', replace(moving, power=0), 9)
    add('crouch-airborne', replace(moving, player=replace(moving.player, y=60*16,
                                                          grounded=False, jump=1, index=4)), 9)
    add('crouch-release', crouch, 1)
    add('crouch-jump', crouch, 24)
    fired = add('shot-fire', thrower, 32)
    moved = add('shot-move', fired, 32)
    bounced = add('shot-bounce', moved, 32)
    add('shot-rise', bounced, 32)
    add('shot-blocked-large', large, 32)
    add('shot-blocked-crouch', thrower, 40)
    add('shot-second-blocked', replace(fired, previous=0), 32)
    add('shot-expire', replace(moved, shot=replace(moved.shot, ttl=1)))
    add('shot-left', replace(thrower, player=Player(facing=32)), 32)
    add('shot-edge', replace(thrower, player=Player(x=0, facing=32)), 32)
    add('shot-kill', replace(thrower, shot=Shot(250*16, 120*16, 32, -32, 10)))
    add('shot-wall', replace(thrower, shot=Shot(71*16, 98*16, 32, 32, 20)))
    add('shot-ceiling', replace(thrower, shot=Shot(88*16, 105*16, 32, -32, 20)))
    held = playing(x=96*16, y=97*16, grounded=False, jump=1, index=20, previous=16)
    add('item-large-box', replace(held, power=LARGE), 16)
    add('item-small-box', held, 16)
    add('goal-large', replace(playing(x=736*16), power=LARGE))
    add('fall-while-large', replace(playing(x=180*16, y=141*16, grounded=False, jump=3, pose=4),
                                    power=LARGE))
    add('enemy-dead-no-contact', replace(playing(x=252*16), alive=False))
    dirty = replace(playing(x=700*16, camera=608, pose=3, counter=6, direction=1, speed=4),
                    power=THROWER, phase=SAFE, phase_timer=9, invincible=7, throw=2,
                    alive=False, crouch=True, shot=Shot(30*16, 100*16, 32, -32, 9),
                    collected=15, score=4, timer=42, mode=RETRY)
    add('reset', dirty, 128, 'reset')
    add('pause-holds', replace(dirty, mode=PAUSED), 16)
    return result


def parts():
    """Two bounded halves; each keeps the default wall budget."""
    all_cases = cases()
    half = len(all_cases) // 2
    return {'a': all_cases[:half], 'b': all_cases[half:]}
