"""Finite ordinary operands and independent motion/integration snapshots."""
from dataclasses import replace

from motion_reference import Player, step
from interactions_reference import Game, ITEMS, overlap
from interaction_cases import ADDRESSES as GAME_ADDRESSES, state_bytes as game_bytes

ADDRESSES = (GAME_ADDRESSES + list(range(0xc060, 0xc06a)) + [0xc02e]
             + list(range(0xc06a, 0xc078)))
RANGES = ((0xc000, 1), (0xc010, 14), (0xc024, 1), (0xc026, 7), (0xc060, 10), (0xc02e, 1),
          (0xc06a, 14))
# Contact/power bytes at reset: small, normal, no timers, enemy alive, no shot.
POWER_RESET = bytes((0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0))


def state_bytes(game, buttons=0, new_level=0):
    p = game.player
    return game_bytes(game, buttons) + bytes((p.counter, p.direction, p.speed,
        p.phase, p.animation, p.pose, p.jump, p.index, p.saved, p.facing, new_level)) + POWER_RESET


def game_update(game, buttons, new_level):
    """Existing flow rules; selected world cases explicitly exclude contacts."""
    edges = buttons & ~game.previous
    if game.mode == 3:
        if edges & 64:
            return Game(mode=1, player=replace(Player(), previous=buttons), previous=buttons), 1
        return replace(game, mode=1 if edges & 128 else 3, previous=buttons,
                       player=replace(game.player, previous=buttons)), new_level
    if game.mode in (2, 4):
        if edges & 128:
            return Game(mode=1, player=replace(Player(), previous=buttons), previous=buttons), 1
        return replace(game, previous=buttons), new_level
    if game.mode == 0:
        if not edges & 128:
            return replace(game, previous=buttons), new_level
        game = replace(game, mode=1)
    elif edges & 128:
        return replace(game, mode=3, previous=buttons,
                       player=replace(game.player, previous=buttons)), new_level
    p = step(game.player, buttons)
    enemy = game.enemy_x + game.enemy_vx
    velocity = game.enemy_vx
    if enemy >= 296*16:
        enemy, velocity = 296*16, -8
    elif enemy <= 240*16:
        enemy, velocity = 240*16, 8
    assert not p.fell and not overlap(p, enemy, 120*16), 'fixture excludes death'
    assert not any(overlap(p, x*16, y*16) for x, y in ITEMS), 'fixture excludes collection'
    assert not overlap(p, 736*16, 112*16, 16), 'fixture excludes goal'
    return replace(game, player=p, enemy_x=enemy, enemy_vx=velocity,
                   timer=(game.timer+1) & 65535, previous=buttons), new_level


def cases():
    result = []
    def add(name, p=Player(), buttons=0, kind='step', game=None, new_level=0):
        before = game if game is not None else Game(mode=1, player=p)
        if kind == 'init':
            after, output_buttons, after_level = replace(before, player=Player()), 0, new_level
        elif kind == 'game':
            after, after_level = game_update(before, buttons, new_level)
            output_buttons = buttons
        else:
            after, output_buttons, after_level = replace(before, player=step(before.player, buttons)), buttons, new_level
        result.append(dict(name=name, kind=kind, buttons=buttons,
                           before=state_bytes(before, buttons, new_level),
                           after=state_bytes(after, output_buttons, after_level)))
        return after, after_level
    # The short harness exercises a real moving/collision path, then terminal.
    add('first-right', buttons=1)
    add('full-init', Player(x=500, y=700, vx=-16, vy=32, grounded=False,
        previous=255, camera=300, fell=True, counter=99, direction=3, speed=4,
        phase=1, animation=255, pose=5, jump=2, index=14, saved=3, facing=32), 255, 'init')
    for name, p, mask in (
        ('walk-threshold', Player(counter=6, direction=1), 1),
        ('run-first', Player(), 33),
        ('run-threshold', Player(counter=3, direction=1, speed=2), 33),
        ('run-release', Player(counter=6, direction=1, speed=4, previous=33), 1),
        ('run-new-edge', Player(counter=6, direction=1, speed=2, previous=1), 33),
        ('coast', Player(counter=6, direction=2, speed=4), 0),
        ('stop', Player(counter=0, direction=1, speed=2, pose=3), 0),
        ('neutral-counter', Player(counter=48), 0),
        ('reverse-entry', Player(counter=6, direction=1, pose=2), 2),
        ('reverse-count', Player(counter=1, direction=3, pose=5), 2),
        ('reverse-clear', Player(counter=0, direction=3, pose=5), 2),
        ('opposites', Player(), 3),
        ('phase-wrap', Player(counter=255, direction=1, animation=255), 1),
        ('left-animation-wrap', Player(counter=6, direction=2, animation=0, pose=3), 2),
        ('jump-walk', Player(), 16),
        ('jump-run', Player(counter=6, direction=1, speed=4, previous=33), 49),
        ('air-steer', Player(y=60*16, grounded=False, jump=1, index=4, pose=4, previous=16), 18),
        ('air-reverse', Player(y=60*16, grounded=False, jump=1, index=4, pose=4, direction=1, previous=16), 18),
        ('release', Player(y=60*16, grounded=False, jump=1, index=5, pose=4, previous=16), 0),
        ('release-zero', Player(y=60*16, grounded=False, jump=1, index=0, pose=4, previous=16), 0),
        ('restore-down', Player(y=60*16, grounded=False, jump=2, index=14, saved=4, pose=4), 0),
        ('sentinel', Player(y=60*16, grounded=False, jump=1, index=26, pose=4, previous=16), 16),
        ('exhaustion', Player(y=60*16, grounded=False, jump=2, index=0, pose=4), 0),
        ('ceiling', Player(x=80*16, y=104*16, grounded=False, jump=1, index=4, previous=16), 16),
        ('fractional-wall', Player(x=72*16-1, y=96*16, counter=6, direction=1, speed=2), 1),
        ('right-clamp', Player(x=760*16, counter=6, direction=1, speed=2), 1),
        ('left-clamp', Player(x=0, counter=6, direction=2, speed=2, facing=32), 2),
        ('support-loss', Player(x=176*16, counter=6, direction=1, speed=2), 1),
        ('landing', Player(x=80*16, y=79*16+1, grounded=False, jump=3, pose=4), 0),
        ('fall', Player(x=180*16, y=140*16, grounded=False, jump=3, pose=4), 0),
        ('already-fell', Player(y=145*16, grounded=False, jump=3, fell=True), 16),
    ):
        add(name, p, mask)
    g = Game(mode=1, timer=123, player=Player(counter=6, direction=1, speed=2, pose=2))
    for name, mask in (('pause', 128), ('paused-held', 16), ('resume-held', 144), ('after-resume-held', 16)):
        g, _ = add(name, buttons=mask, kind='game', game=g)
    dirty = Game(mode=3, player=Player(x=760*16, counter=8, direction=3, speed=4,
        phase=1, animation=44, pose=5, jump=2, index=14, saved=7, facing=32,
        grounded=False, camera=608), enemy_x=280*16, enemy_vx=-8, score=4, collected=15, timer=42)
    add('select-restart', buttons=192, kind='game', game=dirty)
    add('retry-restart', buttons=128, kind='game', game=replace(dirty, mode=2))
    add('title-direction', buttons=129, kind='game', game=Game(player=Player()))
    return result
