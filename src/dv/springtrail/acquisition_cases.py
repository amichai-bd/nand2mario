"""Supplementary seeded CPU cases; ordinary unseeded history has its own proof."""
from dataclasses import replace
from entities_reference import World, initialize, update
from progress_reference import enter_stage
from power_reference import grant_star
from state_seed import ADDRESSES, RANGES, state_bytes
from thrower_route import masks

SHORT = 1
SHORT_BOUND = 60000
FULL_BOUND = 180000
ROUTINE_BOUND = 50000
TITLE = 'ACQUIRE UNIT'


def history():
    result = [World()]
    for mask in masks():
        result.append(update(result[-1],mask))
    return result


def cases():
    worlds = history()
    before, acquired = worlds[383],worlds[409]
    assert before.power == 1 and before.blocks[2] == 0
    result = []
    def add(name,w,buttons=16,kind='game'):
        level = 0
        after = update(w,buttons)
        out = buttons
        if kind == 'coinshot':
            after = update(after,32)
            out = 32
        elif kind == 'reset':
            after = initialize(enter_stage(World(),buttons))
            level = 1
        elif kind == 'star':
            after = grant_star(w)
        elif w.mode in (2,4,5,6) and after.mode == 1:
            level = 1
        result.append(dict(name=name,kind=kind,before=state_bytes(w,buttons),
                           after=state_bytes(after,out,level)))
    add('coin-then-fresh-B',before,kind='coinshot')
    add('ordinary-coin-update384',before)
    add('small-coin-only',replace(before,power=0,phase=0,phase_timer=0))
    add('saturated-coin-upgrade',replace(before,coins=255))
    add('thrower-coin-unchanged',replace(before,power=2))
    add('spent-while-small-no-retroactive',replace(before,blocks=(1,0,1,0)))
    # Relocated contact is an explicit seeded branch operand, not route history.
    add('acquired-power-damage',replace(acquired,alive=True,
                                      player=replace(acquired.player,x=248*16,camera=176),
                                      enemy_x=256*16,enemy_vx=-8,
                                      phase=0,phase_timer=0,invincible=0),0)
    add('retry-clears-acquisition',replace(acquired,mode=2,previous=0),128)
    add('stage-entry-clears-acquisition',replace(acquired,mode=4,previous=0),128)
    add('full-reset-clears-acquisition',acquired,0,'reset')
    add('paused-shot-freezes',replace(acquired,mode=3),0)
    add('GrantStar-keeps-thrower',acquired,0,'star')
    return result


def parts():
    rows = cases()
    return {name:rows[index:index+4] for name,index in zip('abc',(0,4,8))}
