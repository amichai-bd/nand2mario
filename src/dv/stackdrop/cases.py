"""Independent operand cases, not expected-result bytes in the unit ROM."""
from copy import deepcopy
from reference import Game


def groups():
    yield 'new', Game(), [128, 128, 0]
    for piece in range(7):
        yield f'rotate{piece}', Game(status=1, piece=piece, y=3), [16, 0, 16, 0, 16, 0, 16]
    yield 'edges', Game(status=1, x=0), [2, 3, 1, 0, 1, 1, 0, 2]
    yield 'gravity', Game(status=1, gravity=58), [0, 0, 8, 8]
    yield 'hard', Game(status=1), [40, 32]
    blocked = Game(status=1, rotation=1, x=-2, y=8)
    yield 'wall', blocked, [16, 8]
    single = Game(status=1, x=0, y=10)
    single.board[88:] = [0, 0, 0, 0, 1, 1, 1, 1]
    yield 'single', single, [8]
    multiple = Game(status=1, piece=0, rotation=1, x=0, y=8, score=9800)
    multiple.board[64:] = [1, 1, 0, 1, 1, 1, 1, 1]*4
    yield 'four', multiple, [8]
    over = Game(status=1, x=0, y=10)
    over.board[3] = 1
    yield 'over', over, [8, 128, 128]


def state(game):
    return bytes([game.status, game.piece, game.rotation, game.x & 255,
                  game.y, game.previous, game.gravity])


def buffer(game):
    from reference import cells
    values = [2*v for v in game.board]+[0]*16
    if game.status == 1:
        for x, y in cells(game.piece, game.rotation):
            values[(game.y+y)*8+game.x+x] = 3
    for x, y in cells((game.piece+1) % 7, 0):
        values[96+y*4+x] = 3
    return bytes(values+[10+int(d) for d in f'{game.score:04d}']+[4+game.status, 10+game.rotation])


def expected():
    results = []
    for name, initial, inputs in groups():
        game = deepcopy(initial)
        for index, buttons in enumerate(inputs):
            game.update(buttons)
            results.append(dict(group=name, buttons=buttons, state=state(game),
                                score=bytes(map(int, f'{game.score:04d}')),
                                board=bytes(game.board), image=buffer(game),
                                prepare=index == len(inputs)-1,
                                render=name == 'four'))
    return results
