"""Fixed renderer operands, independent of CPU output and map selection."""
from dataclasses import replace
from interactions_reference import Game
from interaction_cases import ADDRESSES, state_bytes
from scene_reference import image
from movement_reference import world_tile


def cases():
    g = Game()
    variants = [g,
        replace(g, player=replace(g.player, x=73*16-1, y=-1, camera=80), collected=15, score=4, mode=3),
        replace(g, player=replace(g.player, x=73*16, y=-1, camera=80), mode=1),
        replace(g, player=replace(g.player, x=240*16, camera=80), mode=2),
        replace(g, player=replace(g.player, x=240*16-1, camera=80), collected=10, score=2, mode=4),
        replace(g, player=replace(g.player, x=760*16, y=146*16, camera=608, fell=True), enemy_x=296*16)]
    return [dict(game=variants[i%6], restart=i in (0, 2)) for i in range(18)]


def maps(count):
    data = bytearray(576)
    column = 0
    writes = []
    for case in cases()[:count]:
        if case['restart']:
            column = 0
        step = []
        for c in (column, column+1):
            for row in range(18):
                value = world_tile(c, row)
                data[row*32+c] = value
                step.append((0x9c00+row*32+c, value))
        writes.append(step)
        column += 2
    return bytes(data), writes
