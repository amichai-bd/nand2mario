"""Independent model of the approved interactive-block contract.

This module owns only the block layer: the table, its solidity override, its
appearance and the resolution of one head hit. It holds no world state and
imports no world model, so `power_reference` can consume it without a cycle.
"""

ITEM, BRICK, HIDDEN = range(3)
NONE, COIN, MUSHROOM, STAR = range(4)
INTACT, USED, BROKEN = range(3)
SMALL = 0

# column, row, kind, content. Rows are always 10 and 11; see BLOCKS.md.
BLOCKS = ((38, 10, ITEM, MUSHROOM),
          (52, 10, BRICK, NONE),
          (64, 10, ITEM, COIN),
          (88, 10, HIDDEN, STAR))
ROWS = (10, 11)
EFFECT_UPDATES = 16
COIN_LIMIT = 255

# VRAM 108..139 hold approved terrain atlas tiles 10..33 and 38..45.
FIRST_TILE = 108
ATLAS_TILES = tuple(range(10, 34)) + tuple(range(38, 46))
SEALED, USED_TILE, CRACK, REVEAL = 108, 112, 116, 120
SHARDS, COIN_TILE, LEAF, GEM = 124, 128, 132, 136
CONTENT_TILE = {COIN: COIN_TILE, MUSHROOM: LEAF, STAR: GEM, NONE: 0}

for _column, _row, _kind, _content in BLOCKS:
    assert _row == ROWS[0], 'every block is anchored in row 10'
    assert (_content == NONE) == (_kind == BRICK), 'only a brick carries no content'


def reset():
    return tuple(INTACT for _ in BLOCKS)


def find(column, row):
    """Index of the block covering one cell, or None."""
    for index, (bx, by, _kind, _content) in enumerate(BLOCKS):
        if bx <= column <= bx + 1 and by <= row <= by + 1:
            return index
    return None


def solid(states, column, row, ascending=False):
    """Block-layer solidity. Terrain is decided by the caller and never overridden."""
    index = find(column, row)
    if index is None:
        return False
    kind, state = BLOCKS[index][2], states[index]
    if state == BROKEN:
        return False
    if kind == HIDDEN:
        return state == USED or ascending
    return True


def appearance(states, index):
    """Tile base of one block, or 0 when it shows the blank background."""
    kind, state = BLOCKS[index][2], states[index]
    if state == BROKEN:
        return 0
    if kind == BRICK:
        return CRACK
    if kind == HIDDEN:
        return REVEAL if state == USED else 0
    return SEALED if state == INTACT else USED_TILE


def column_tiles(states, column):
    """{world row: tile} the column decoder writes over rows 10 and 11."""
    result = {}
    for index, (bx, by, _kind, _content) in enumerate(BLOCKS):
        if not bx <= column <= bx + 1:
            continue
        base = appearance(states, index)
        if not base:
            continue
        half = column - bx
        result[by] = base + half
        result[by + 1] = base + 2 + half
    return result


def resolve(states, coins, power, hit):
    """One head hit. Returns (states, coins, tile, x, y, grant).

    `hit` is a (column, row) cell or None. `grant` is None, 'power' or 'star'.
    `tile` is 0 when nothing is released; x and y are then meaningless.
    """
    index = None if hit is None else find(*hit)
    if index is None or states[index] != INTACT:
        return states, coins, 0, 0, 0, None
    column, row, kind, content = BLOCKS[index]
    updated = list(states)
    if kind == BRICK:
        if power == SMALL:
            return states, coins, 0, 0, 0, None
        updated[index] = BROKEN
        return tuple(updated), coins, SHARDS, column * 8, row * 8, None
    updated[index] = USED
    grant = None
    if content == COIN:
        coins = min(COIN_LIMIT, coins + 1)
        if power == 1:
            grant = 'power'
    elif content == MUSHROOM:
        grant = 'power'
    elif content == STAR:
        grant = 'star'
    return tuple(updated), coins, CONTENT_TILE[content], column * 8, row * 8, grant
