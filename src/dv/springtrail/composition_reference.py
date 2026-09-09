"""Approved-source pixel and OAM oracle, independent of SM83 tables/code."""
import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2]/'sw/springtrail'
POSES = json.loads((SOURCE/'assets/courier/poses.json').read_text())
BANK = json.loads((SOURCE/'assets/courier/unique-tiles.json').read_text())['pixels']
NAMES = ('STAND', 'WALK1', 'WALK2', 'WALK3', 'JUMP', 'RETRY')


def approved(pose, left=False):
    size = 'large' if pose >= 6 else 'small'
    rows = [[0]*16 for _ in range(24 if pose >= 6 else 16)]
    for part in POSES[size][NAMES[pose%6]]:
        for y in range(8):
            for x in range(8):
                sx = 7-x if part['x_flip'] else x
                sy = 7-y if part['y_flip'] else y
                rows[part['y']+y][part['x']+x] = BANK[sy][part['tile']*8+sx]
    return bytes(v for row in rows for v in (row[::-1] if left else row))


def courier(pose, left=False, x=0, y=0, hidden=False):
    """x/y are art's small top-left; large retains the same feet."""
    result = bytearray()
    for part in POSES['large' if pose >= 6 else 'small'][NAMES[pose%6]]:
        px = x + (8-part['x'] if left else part['x'])
        py = y + part['y'] - (8 if pose >= 6 else 0)
        flags = 32*(part['x_flip'] != left) + 64*part['y_flip']
        visible = not hidden and -7 <= px < 160 and -7 <= py < 144
        result.extend(((py+16)&255 if visible else 0, (px+8)&255,42+part['tile'],flags))
    return bytes(result)


def raster(data, tiles, width=160, height=144):
    """DMG selects first ten by Y, then smaller X/earlier OAM pixel priority."""
    out = bytearray(width*height)
    entries = [tuple(data[i:i+4]) for i in range(0,len(data),4)]
    for y in range(height):
        selected = [i for i,e in enumerate(entries) if e[0]-16 <= y < e[0]-8][:10]
        for x in range(width):
            for i in sorted(selected,key=lambda i:(entries[i][1],i)):
                oy,ox,tile,flags = entries[i]
                sx,sy = x-(ox-8),y-(oy-16)
                if not 0 <= sx < 8: continue
                if flags&32: sx=7-sx
                if flags&64: sy=7-sy
                value=tiles[tile][sy][sx]
                if value:
                    out[y*width+x]=value
                    break
    return bytes(out)
