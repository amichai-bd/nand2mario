"""Independent original image rules; no DUT state or program imports."""
OBJECTS = ((20,16,4,0), (20,20,5,0), (20,20,6,0),
           (20,32,5,0x80), (20,56,6,0x60))


def object_color(tile, x, y):
    if tile == 4:
        return 1 if x % 2 == 0 else 0
    if tile == 5:
        return 2
    if tile == 6:
        return 3 if x == 0 and y < 3 else 2
    raise ValueError(tile)


def shade(x, y, *, blank=False):
    if blank:
        return 0
    background = (x//8 + y//8 + (2 if y >= 16 else 0)) % 4
    candidates = []
    for index, (top,left,tile,flags) in enumerate(OBJECTS):
        if not (left <= x < left+8 and top <= y < top+8):
            continue
        dx,dy=x-left,y-top
        color=object_color(tile,7-dx if flags&0x20 else dx,
                           7-dy if flags&0x40 else dy)
        if color:
            candidates.append((left,index,color,flags))
    if not candidates:
        return background
    _,_,color,flags=min(candidates)
    return background if flags&0x80 and background else color


def image(rows=32):
    return bytes(shade(x,y) for y in range(rows) for x in range(160))
