"""Read only original rendered tiles; no gameplay memory or predicted state."""
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
TILES = 49
PREVIEW = ('....####........', '.##..##.........', '.#..###.........',
           '..#.###.........', '#...###.........', '.##.##..........',
           '##...##.........')


def tile(number):
    result = bytearray(64)
    def put(x, y, value):
        result[y*8+x] = value
    if number == 2:  # Locked: dark outline around a grey face.
        for y in range(1, 7):
            for x in range(1, 7):
                put(x, y, 3 if x in (1, 6) or y in (1, 6) else 2)
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
    elif 31 <= number < TILES:
        rows = LETTER[WORD[(number-31)//2]]
        top = (number-31) % 2 == 0
        for index in range(6 if top else 5):
            for x in range(7):
                put(x, (2+index) if top else index, 3*int(rows[index if top else 6+index][x] == '#'))
    return bytes(result)


def background():
    """The static map the ROM writes once: marquee, well frame and panel boxes."""
    cells = [[0]*20 for _ in range(18)]
    for index, letter in enumerate(WORD):
        cells[0][5+index], cells[1][5+index] = 31+2*index, 32+2*index
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


def decode(pixels):
    if len(pixels) != 23040 or any(p > 3 for p in pixels):
        raise ValueError('STACKDROP_SCREEN_SIZE')
    def read(x, y, allowed):
        observed = bytes(pixels[(y+dy)*160+x+dx] for dy in range(8) for dx in range(8))
        matches = [n for n in allowed if observed == tile(n)]
        if len(matches) != 1:
            raise ValueError(f'STACKDROP_TILE x={x} y={y}')
        return matches[0]
    status = read(120, 120, (4, 5, 6))-4
    rotation = read(128, 120, range(10, 14))-10
    board, active = [], []
    for y in range(12):
        for x in range(8):
            value = read(48+x*8, 24+y*8, (0, 2, 3))
            board.append(int(value == 2))
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
    cells = buffer(game)
    layout = background()
    for i in range(96):
        layout[3+i//8][6+i % 8] = cells[i]
    for i in range(16):
        layout[4+i//4][15+i % 4] = cells[96+i]
    for i in range(4):
        layout[11][15+i] = cells[112+i]
    layout[15][15], layout[15][16] = cells[116:118]
    result = bytearray(23040)
    for y, row in enumerate(layout):
        for x, number in enumerate(row):
            values = tile(number)
            for line in range(8):
                offset = (8*y+line)*160+8*x
                result[offset:offset+8] = values[line*8:line*8+8]
    return bytes(result)
