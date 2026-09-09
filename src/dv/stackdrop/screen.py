"""Read only original rendered tiles; no gameplay memory or predicted state."""
DIGITS = ('111101101101111', '010110010010111', '111001111100111',
          '111001111001111', '101101111001001', '111100111001111',
          '111100111101111', '111001010010010', '111101111101111',
          '111101111001111')
PREVIEW = ('....####........', '.##..##.........', '.#..###.........',
           '..#.###.........', '#...###.........', '.##.##..........',
           '##...##.........')


def tile(number):
    result = bytearray(64)
    for y in range(8):
        for x in range(8):
            value = 0
            if number == 1:
                value = 1
            elif number in (2, 3) and 1 <= x <= 6 and 1 <= y <= 6:
                value = number
            elif number in (4, 5, 6) and 1 <= x <= 6 and 1 <= y <= 6:
                visible = (number == 4 and (x in (1, 6) or y in (1, 6))) or (number == 5 and (x == 3 or y == 3)) or (number == 6 and (x == y or x+y == 7))
                value = 3 if visible else 0
            elif 10 <= number <= 19 and 1 <= y <= 5 and 2 <= x <= 4:
                value = 3*int(DIGITS[number-10][(y-1)*3+x-2])
            result[y*8+x] = value
    return bytes(result)


def decode(pixels):
    if len(pixels) != 23040 or any(p > 3 for p in pixels):
        raise ValueError('STACKDROP_SCREEN_SIZE')
    def read(x, y, allowed):
        observed = bytes(pixels[(y+dy)*160+x+dx] for dy in range(8) for dx in range(8))
        matches = [n for n in allowed if observed == tile(n)]
        if len(matches) != 1:
            raise ValueError(f'STACKDROP_TILE x={x} y={y}')
        return matches[0]
    status = read(32, 16, (4, 5, 6))-4
    rotation = read(32, 24, range(10, 14))-10
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
        score = 10*score+read(64+x*8, 128, range(10, 20))-10
    return dict(status=status, rotation=rotation, board=board, active=active,
                next_piece=PREVIEW.index(preview), score=score)


def image(game):
    """Independent full image from the specified state, for the frame oracle."""
    from cases import buffer
    cells = buffer(game)
    layout = {(x, y): 1 for y in range(2, 16) for x in range(5, 15)
              if x in (5, 14) or y in (2, 15)}
    for i in range(96):
        layout[6+i % 8, 3+i//8] = cells[i]
    for i in range(16):
        layout[15+i % 4, 4+i//4] = cells[96+i]
    for i in range(4):
        layout[8+i, 16] = cells[112+i]
    layout[4, 2], layout[4, 3] = cells[116:118]
    result = bytearray(23040)
    for (x, y), number in layout.items():
        values = tile(number)
        for row in range(8):
            offset = (8*y+row)*160+8*x
            result[offset:offset+8] = values[row*8:row*8+8]
    return bytes(result)
