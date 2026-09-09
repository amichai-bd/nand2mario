"""Deterministic legal placements from Stackdrop's decoded visible board."""
from collections import deque

SPAWN = (
    ((0, 1), (1, 1), (2, 1), (3, 1)),
    ((1, 0), (2, 0), (1, 1), (2, 1)),
    ((1, 0), (0, 1), (1, 1), (2, 1)),
    ((2, 0), (0, 1), (1, 1), (2, 1)),
    ((0, 0), (0, 1), (1, 1), (2, 1)),
    ((1, 0), (2, 0), (0, 1), (1, 1)),
    ((0, 0), (1, 0), (1, 1), (2, 1)),
)
MASKS = (2, 1, 16, 32)


def cells(piece, rotation, x, y):
    points = SPAWN[piece]
    for _ in range(rotation):
        if piece != 1:
            edge = 3 if piece == 0 else 2
            points = tuple((edge-b, a) for a, b in points)
    return tuple((x+a, y+b) for a, b in points)


def valid(board, points):
    return all(0 <= x < 8 and 0 <= y < 12 and not board[y*8+x]
               for x, y in points)


def state(screen):
    """Infer an exact origin using the visible rotation and next-piece identity."""
    board = screen['board']
    if (screen['status'] != 1 or len(board) != 96 or
            any(v not in (0, 1) for v in board) or
            screen['rotation'] not in range(4) or
            screen['next_piece'] not in range(7)):
        raise ValueError('STACKDROP_PLAYER_SCREEN')
    piece = (screen['next_piece']-1) % 7
    active = set(map(tuple, screen['active']))
    if len(active) != 4:
        raise ValueError('STACKDROP_PLAYER_ACTIVE')
    matches = [(x, y, screen['rotation']) for x in range(-3, 8)
               for y in range(-3, 12)
               if set(cells(piece, screen['rotation'], x, y)) == active]
    if len(matches) != 1 or not valid(board, active):
        raise ValueError('STACKDROP_PLAYER_AMBIGUOUS')
    return piece, matches[0]


def evaluate(board, points):
    placed = list(board)
    for x, y in points:
        placed[y*8+x] = 1
    rows = [placed[y*8:y*8+8] for y in range(12)]
    kept = [row for row in rows if not all(row)]
    lines = 12-len(kept)
    rows = [[0]*8 for _ in range(lines)] + kept
    heights, holes = [], 0
    for x in range(8):
        occupied = [y for y in range(12) if rows[y][x]]
        first = min(occupied, default=12)
        heights.append(12-first)
        holes += sum(not rows[y][x] for y in range(first, 12))
    bumpiness = sum(abs(a-b) for a, b in zip(heights, heights[1:]))
    return 1000*lines-50*holes-5*sum(heights)-2*bumpiness


def choose(screen, mode):
    """Return one edge; the caller must observe again before choosing another."""
    piece, initial = state(screen)
    if mode == 'baseline':
        return dict(mask=32, path=[32], score=None)
    if mode != 'strategy':
        raise ValueError('STACKDROP_PLAYER_MODE')
    board = screen['board']
    queue = deque([(initial, ())])
    seen = {initial}
    candidates = []
    while queue:
        (x, y, rotation), path = queue.popleft()
        drop_y = y
        while valid(board, cells(piece, rotation, x, drop_y+1)):
            drop_y += 1
        value = evaluate(board, cells(piece, rotation, x, drop_y))
        actions = path+(3,)
        candidates.append((-value, len(actions), actions))
        for action, target in enumerate(((x-1, y, rotation),
                                         (x+1, y, rotation),
                                         (x, y, (rotation+1) % 4))):
            tx, ty, tr = target
            if target not in seen and valid(board, cells(piece, tr, tx, ty)):
                seen.add(target)
                queue.append((target, path+(action,)))
    score, _, actions = min(candidates)
    return dict(mask=MASKS[actions[0]], path=[MASKS[a] for a in actions],
                score=-score)
