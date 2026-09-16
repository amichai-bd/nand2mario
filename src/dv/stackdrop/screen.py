"""Read only original rendered tiles; no gameplay memory or predicted state."""
from pathlib import Path
from cases import FACES
# Original 5x7 glyphs for digits, labels and the status letter, drawn here and
# mirrored by the ROM atlas; `test_screen` compares both against the asset.
SMALL = """\
0 .###. #...# #..## #.#.# ##..# #...# .###.
1 ..#.. .##.. ..#.. ..#.. ..#.. ..#.. .###.
2 .###. #...# ....# ...#. ..#.. .#... #####
3 ####. ....# ....# .###. ....# ....# ####.
4 ...#. ..##. .#.#. #..#. ##### ...#. ...#.
5 ##### #.... ####. ....# ....# #...# .###.
6 ..##. .#... #.... ####. #...# #...# .###.
7 ##### ....# ...#. ..#.. .#... .#... .#...
8 .###. #...# #...# .###. #...# #...# .###.
9 .###. #...# #...# .#### ....# ...#. .##..
T ##### ..#.. ..#.. ..#.. ..#.. ..#.. ..#..
P ####. #...# #...# ####. #.... #.... #....
O .###. #...# #...# #...# #...# #...# .###.
N #...# ##..# ##..# #.#.# #..## #..## #...#
E ##### #.... #.... ####. #.... #.... #####
X #...# #...# .#.#. ..#.. .#.#. #...# #...#
S .#### #.... #.... .###. ....# ....# ####.
C .###. #...# #.... #.... #.... #...# .###.
R ####. #...# #...# ####. #.#.. #..#. #...#
A .###. #...# #...# ##### #...# #...# #...#"""
# Original 7x11 marquee letterforms; two stacked tiles carry one letter.
BIG = """\
S .#####. ##...## ##..... ##..... .#####. .....## .....## .....## ##...## ##...## .#####.
T ####### ####### ..###.. ..###.. ..###.. ..###.. ..###.. ..###.. ..###.. ..###.. ..###..
A ..###.. .#####. ##...## ##...## ##...## ####### ####### ##...## ##...## ##...## ##...##
C .#####. ##...## ##...## ##..... ##..... ##..... ##..... ##..... ##...## ##...## .#####.
K ##...## ##..##. ##.##.. #####.. ###.... #####.. ##.##.. ##..##. ##...## ##...## ##...##
D #####.. ##..##. ##...## ##...## ##...## ##...## ##...## ##...## ##...## ##..##. #####..
R ######. ##...## ##...## ##...## ######. ##.##.. ##..##. ##...## ##...## ##...## ##...##
O .#####. ##...## ##...## ##...## ##...## ##...## ##...## ##...## ##...## ##...## .#####.
P ######. ##...## ##...## ##...## ##...## ######. ##..... ##..... ##..... ##..... ##....."""
GLYPH = {line[0]: line[2:].split(' ') for line in SMALL.splitlines()}
LETTER = {line[0]: line[2:].split(' ') for line in BIG.splitlines()}
# Tile 4/5/6 keep their status meaning and are legible letters: title, play, over.
NAMED = dict(zip('TPO', (4, 5, 6)), **dict(zip('NEXSCRA', range(24, 31))))
NAMED.update({str(d): 10+d for d in range(10)})
WORD = 'STACKDROP'
RULE = (2, 5, 6)  # Ink offsets from a frame tile's outer edge: thin line, heavy bar.
FRAME = {1: 'T', 7: 'B', 8: 'L', 9: 'R', 20: 'TL', 21: 'TR', 22: 'BL', 23: 'BR'}
MARQUEE = 8  # First marquee column; centred over the frame and panels at 5..19.
TITLE_TILE = 49  # Six tiles per title letter: top, middle, foot; left, right.
FACE_TILE = TITLE_TILE+6*len(WORD)  # Locked faces for O, T, L, J, S, Z follow the title letters.
TILES = FACE_TILE+6
assert FACES == (0, 2)+tuple(range(FACE_TILE, TILES)), 'STACKDROP_FACE_TILES'
# Shade-1 motif inside the shade-2 face of each locked piece, on the 4x4
# interior at 2..5; the shade-3 outline at 1 and 6 is shared by all seven.
MOTIF = dict(zip(FACES[1:], (
    (),                                                          # I: plain
    ((3, 3), (4, 3), (3, 4), (4, 4)),                            # O: centre dot
    tuple((x, y) for y in (3, 4) for x in range(2, 6)),          # T: horizontal bar
    tuple((x, y) for y in range(2, 6) for x in (3, 4)),          # L: vertical bar
    ((2, 2), (5, 2), (2, 5), (5, 5)),                            # J: four corner dots
    ((2, 2), (3, 3), (4, 4), (5, 5)),                            # S: diagonal
    tuple((x, y) for y in range(2, 6) for x in range(2, 6) if (x+y) % 2 == 0),  # Z: checker
)))
# The title page: SCX/SCY the ROM stores before LCD enable. Screen cell (s, r)
# shows map cell ((20+s) % 32, (16+r) % 32). The two views intersect only at
# map rows 16..17, columns 0..7, which both keep zero; the play page's STATE
# box bottom (row 16, columns 15..19) and marquee (rows 0..1, columns 8..16)
# lie outside the title view.
TITLE_SCROLL = (160, 128)
PROMPT = 'PRESS START'
PREVIEW = ('....####........', '.##..##.........', '.#..###.........',
           '..#.###.........', '#...###.........', '.##.##..........',
           '##...##.........')


def tile(number):
    result = bytearray(64)
    def put(x, y, value):
        result[y*8+x] = value
    if number in MOTIF:  # Locked: dark outline around a grey face with the piece motif.
        for y in range(1, 7):
            for x in range(1, 7):
                put(x, y, 3 if x in (1, 6) or y in (1, 6) else 1 if (x, y) in MOTIF[number] else 2)
    elif number == 3:  # Active: solid block with a light top-left bevel.
        for y in range(1, 7):
            for x in range(1, 7):
                put(x, y, 1 if x == 1 or y == 1 else 3)
    elif number in FRAME:
        sides = FRAME[number]
        for y in range(8):
            for x in range(8):
                depth = {'T': y, 'B': 7-y, 'L': x, 'R': 7-x}
                # Each side contributes its rule; on a corner a rule starts only
                # where the other side's outermost rule crosses it.
                ink = any(depth[side] in RULE and all(depth[other] >= RULE[0]
                                                      for other in sides if other != side)
                          for side in sides)
                put(x, y, 3*int(ink))
    elif number in (4, 5, 6) or 10 <= number <= 19 or 24 <= number <= 30:
        rows = GLYPH[next(c for c, n in NAMED.items() if n == number)]
        for y in range(7):
            for x in range(5):
                put(1+x, y, 3*int(rows[y][x] == '#'))
    elif 31 <= number < TITLE_TILE:
        rows = LETTER[WORD[(number-31)//2]]
        top = (number-31) % 2 == 0
        for index in range(6 if top else 5):
            for x in range(7):
                put(x, (2+index) if top else index, 3*int(rows[index if top else 6+index][x] == '#'))
    elif TITLE_TILE <= number < TILES:
        letter, part = divmod(number-TITLE_TILE, 6)
        row, column = divmod(part, 2)
        shades = letterform(WORD[letter])
        for y in range(8):
            for x in range(8):
                put(x, y, shades[8*row+y][8*column+x])
    return bytes(result)


def letterform(letter):
    """Title letter: the 7x11 marquee form at 2x with a shade-1 bevel on each stroke's top/left edge."""
    rows = LETTER[letter]
    body = [[x < 14 and y < 22 and rows[y//2][x//2] == '#' for x in range(16)] for y in range(24)]
    return [[0 if not body[y][x] else
             1 if x == 0 or y == 0 or not body[y][x-1] or not body[y-1][x] else 3
             for x in range(16)] for y in range(24)]


def background():
    """The static map the ROM writes once: marquee, well frame and panel boxes."""
    cells = [[0]*20 for _ in range(18)]
    for index, letter in enumerate(WORD):
        cells[0][MARQUEE+index], cells[1][MARQUEE+index] = 31+2*index, 32+2*index
    for row in range(2, 16):
        for column in range(5, 15):
            edge = (row in (2, 15), column in (5, 14))
            if not any(edge):
                continue
            vertical = 22 if row == 15 else 20
            cells[row][column] = (vertical+int(column == 14) if all(edge)
                                  else (1 if row == 2 else 7) if edge[0]
                                  else 8 if column == 5 else 9)
    for label, row in (('NEXT', 2), ('SCORE', 9), ('STATE', 13)):
        for index, character in enumerate(label):
            cells[row][15+index] = NAMED[character]
    for top, height in ((3, 4), (10, 1), (14, 1)):  # Boxes hang off the well frame: open left.
        for column in range(15, 19):
            cells[top][column], cells[top+height+1][column] = 1, 7
        cells[top][19], cells[top+height+1][19] = 21, 23
        for row in range(top+1, top+1+height):
            cells[row][19] = 9
    return cells


def title():
    """The static title page: dividers, large lettering, prompt, a falling T over a stack."""
    cells = [[0]*20 for _ in range(18)]
    for column in range(1, 19):
        cells[3][column], cells[7][column] = 7, 1
        cells[14][column] = 0 if column in (8, 9, 10) else 2
        cells[15][column] = 2
    for index, letter in enumerate(WORD):
        for part in range(6):
            cells[4+part//2][1+2*index+part % 2] = TITLE_TILE+6*index+part
    for index, character in enumerate(PROMPT):
        if character != ' ':
            cells[10][4+index] = NAMED[character]
    for x, y in ((9, 12), (8, 13), (9, 13), (10, 13)):
        cells[y][x] = 3
    return cells


def page():
    """The whole 32x32 map the ROM copies once: play page at the origin, title where the scroll shows it."""
    cells = [[0]*32 for _ in range(32)]
    for row, values in enumerate(background()):
        cells[row][:20] = values
    for row, values in enumerate(title()):
        for column, value in enumerate(values):
            if value:
                target = cells[(TITLE_SCROLL[1]//8+row) % 32]
                index = (TITLE_SCROLL[0]//8+column) % 32
                assert not target[index], 'STACKDROP_PAGE_OVERLAP'
                target[index] = value
    return cells


def compose(layout):
    result = bytearray(23040)
    for y, row in enumerate(layout):
        for x, number in enumerate(row):
            values = tile(number)
            for line in range(8):
                offset = (8*y+line)*160+8*x
                result[offset:offset+8] = values[line*8:line*8+8]
    return bytes(result)


TITLE_IMAGE = compose(title())
TITLE_STATE = dict(status=0, rotation=0, board=[0]*96, active=[], next_piece=0, score=0)


def pack(pixels):
    """Snapshot packing: four shades per byte, the first pixel in the low bits."""
    return bytes(sum(pixels[i+j] << (2*j) for j in range(4)) for i in range(0, len(pixels), 4))


def unpack(packed):
    return bytes((b >> shift) & 3 for b in packed for shift in (0, 2, 4, 6))


def decode(pixels):
    if len(pixels) != 23040 or any(p > 3 for p in pixels):
        raise ValueError('STACKDROP_SCREEN_SIZE')
    # The title page is one static image; anything else must be the play page.
    if bytes(pixels) == TITLE_IMAGE:
        return dict(TITLE_STATE, board=[0]*96, active=[])
    def read(x, y, allowed):
        observed = bytes(pixels[(y+dy)*160+x+dx] for dy in range(8) for dx in range(8))
        matches = [n for n in allowed if observed == tile(n)]
        if len(matches) != 1:
            raise ValueError(f'STACKDROP_TILE x={x} y={y}')
        return matches[0]
    status = read(120, 120, (5, 6))-4
    rotation = read(128, 120, range(10, 14))-10
    board, active = [], []
    for y in range(12):
        for x in range(8):
            value = read(48+x*8, 24+y*8, FACES+(3,))
            board.append(FACES.index(value) if value != 3 else 0)
            if value == 3:
                active.append((x, y))
    preview = ''.join('#' if read(120+x*8, 32+y*8, (0, 3)) == 3 else '.'
                      for y in range(4) for x in range(4))
    if preview not in PREVIEW or len(active) != (4 if status == 1 else 0):
        raise ValueError('STACKDROP_PIECE')
    score = 0
    for x in range(4):
        score = 10*score+read(120+x*8, 88, range(10, 20))-10
    return dict(status=status, rotation=rotation, board=board, active=active,
                next_piece=PREVIEW.index(preview), score=score)


def image(game):
    """Independent full image from the specified state, for the frame oracle."""
    from cases import buffer
    if game.status == 0:
        return TITLE_IMAGE
    cells = buffer(game)
    layout = background()
    for i in range(96):
        layout[3+i//8][6+i % 8] = cells[i]
    for i in range(16):
        layout[4+i//4][15+i % 4] = cells[96+i]
    for i in range(4):
        layout[11][15+i] = cells[112+i]
    layout[15][15], layout[15][16] = cells[116:118]
    return compose(layout)


if __name__ == '__main__':
    import hashlib
    import json
    import sys
    import zlib
    if sys.argv[1:] != ['--write-title-fixture']:
        raise SystemExit('usage: screen.py --write-title-fixture')
    folder = Path(__file__).resolve().parent/'fixtures'
    packed = pack(TITLE_IMAGE)
    (folder/'title-frame.txt').write_text(''.join(packed[i:i+64].hex()+'\n' for i in range(0, len(packed), 64)))
    metadata = dict(schema_version=1, program='stackdrop', state='title', width=160, height=144,
                    packing='snapshot: four 2-bit shades per byte, first pixel in the low bits; title-frame.txt holds the bytes as hex text, 64 per line',
                    bytes=len(packed), crc32=f'{zlib.crc32(TITLE_IMAGE):08x}',
                    sha256=hashlib.sha256(packed).hexdigest(), scx=TITLE_SCROLL[0], scy=TITLE_SCROLL[1],
                    source='src/dv/stackdrop/screen.py TITLE_IMAGE; regenerate with python src/dv/stackdrop/screen.py --write-title-fixture')
    (folder/'title.json').write_text(json.dumps(metadata, indent=1)+'\n')
    print(metadata['crc32'])
