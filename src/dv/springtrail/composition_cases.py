"""Finite operand cases; expected state and OAM are independently composed."""
from dataclasses import replace
from interactions_reference import Game, update
from composition_reference import courier, scene


def cases():
    result=[dict(kind='courier',pose=p,left=left,x=24,y=32,hidden=False)
            for p in range(12) for left in (False,True)]
    result += [dict(kind='courier',pose=p,left=left,x=x,y=y,hidden=hidden)
               for p,left,x,y,hidden in ((0,False,-8,-8,False),(0,True,-7,-7,False),
               (11,True,159,143,False),(11,False,24,32,True))]
    result += [dict(kind='game',game=Game(),buttons=130),
               dict(kind='game',game=Game(),buttons=129),
               dict(kind='game',game=replace(Game(),mode=3),buttons=192),
               dict(kind='scene',game=replace(Game(),mode=1,player=replace(Game().player,
                    x=256*16-1,y=-1,camera=256)),buttons=0)]
    return result


def expected(case):
    if case['kind']=='courier':
        return courier(case['pose'],case['left'],case['x'],case['y'],case['hidden'])
    return scene(update(case['game'],case['buttons']) if case['kind']=='game' else case['game'])
