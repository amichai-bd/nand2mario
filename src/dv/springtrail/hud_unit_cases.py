"""Finite ordinary operands and independent cache/publication expectations."""
from composition_reference import scene
from hud_reference import column, entering, hud_tiles
from interactions_reference import Game, Player


def cases():
    result = [dict(kind='decode', column=i) for i in (0, 95, 22, 31)]
    result += [dict(kind='restore', restore=0, mode=3), dict(kind='restore', restore=30)]
    result += [dict(kind='restart', restore=14)]
    result += [dict(kind='enter', old=a, camera=b) for a, b in
               ((80, 88), (88, 96), (96, 88), (607, 608), (608, 607), (96, 96))]
    result += [dict(kind='hud', mode=i, score=i) for i in range(5)]
    result += [dict(kind='scene', camera=96, old=88, score=2)]
    return result


def game(case):
    return Game(mode=case.get('mode', 1), score=case.get('score', 0),
                player=Player(x=120*16, camera=case.get('camera', 0)))


def shadow(case):
    return scene(game(case))[:64] + bytes(96)


def expected(case):
    """Ordered writes to caches, complete shadow/readback and display owners."""
    writes = []
    def cache(indices):
        writes.extend((0xc200+n*16+y, value) for n, index in enumerate(indices)
                      for y, value in enumerate(column(index)))
    def publish(indices):
        writes.extend((0x9c00+(y+2)*32+(index & 31), value) for index in indices
                      for y, value in enumerate(column(index)))
    def hud():
        writes.extend(enumerate(hud_tiles(game(case)), 0xc220))
    def publish_hud():
        values = hud_tiles(game(case))
        for base in (0x9800, 0x9c00):
            writes.extend((base+1+i, value) for i, value in enumerate(values[:6]))
            writes.append((base+18, values[6]))
    kind = case['kind']
    if kind == 'decode':
        cache([case['column']])
    elif kind == 'restore':
        indices = [case['restore'], case['restore']+1]
        cache(indices); publish(indices)
        if case['restore'] == 30: writes.append((0xff40, 8))
    elif kind == 'restart':
        for _ in range(2):
            cache([0, 1]); writes.append((0xff40, 0)); publish([0, 1])
    elif kind == 'enter':
        index = entering(case['old'], case['camera'])
        if index is not None: cache([index]); publish([index])
    elif kind == 'hud':
        hud(); publish_hud()
    else:
        writes.extend(enumerate(shadow(case), 0xc100))
        index = entering(case['old'], case['camera'])
        cache([index]); hud(); publish([index]); publish_hud()
        writes.append((0xff46, 0xc1))
        writes.extend(enumerate(shadow(case), 0xc300))
    return writes


def metadata(case):
    kind = case['kind']
    if kind == 'restore':
        return {0xc052:case['restore'], 0xc053:2, 0xc02f:case['restore']+2}
    if kind == 'restart':
        return {0xc052:0, 0xc053:2, 0xc02f:2, 0xc023:0}
    if kind in ('enter', 'scene'):
        index = entering(case['old'], case['camera'])
        result = {0xc053:int(index is not None), 0xc023:case['camera']//8}
        if index is not None: result[0xc052] = index
        return result
    return {}
