"""Independent approved entity artwork projection, with no gameplay/DUT inputs."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE_TILES = tuple(range(11)) + tuple(range(19, 33))
FIRST_TILE = 149
POSES = ('BEETLE WALK1', 'BEETLE WALK2', 'BEETLE STOMP1', 'BEETLE STOMP2',
         'CURL DORMANT', 'CURL ACTIVE', 'PLATFORM SOLID', 'PLATFORM CRACK1',
         'PLATFORM CRACK2')
ATLAS = json.loads((ROOT / 'src/sw/springtrail/assets/core/enemies-tiles.json').read_text())
MAPS = json.loads((ROOT / 'src/sw/springtrail/assets/core/enemies-maps.json').read_text())


def tiles():
    return tuple(bytes(ATLAS['pixels'][y][tile * 8 + x]
                       for y in range(8) for x in range(8)) for tile in SOURCE_TILES)


def pieces(name, facing=False):
    """Literal approved map projected to runtime IDs, whole-pose reflected."""
    if name not in POSES:
        raise ValueError('unsupported entity pose')
    pose = MAPS[name]
    return tuple((pose['width'] - 8 - p['x'] if facing else p['x'], p['y'],
                  FIRST_TILE + SOURCE_TILES.index(p['tile']),
                  bool(p.get('x_flip', False)) ^ bool(facing),
                  bool(p.get('y_flip', False))) for p in pose['pieces'])


def pixels(name, facing=False):
    pose = MAPS[name]
    result = bytearray(pose['width'] * pose['height'])
    bank = tiles()
    for ox, oy, tile, fx, fy in pieces(name, facing):
        source = bank[tile - FIRST_TILE]
        for y in range(8):
            for x in range(8):
                result[(oy+y)*pose['width']+ox+x] = source[(7-y if fy else y)*8+(7-x if fx else x)]
    return bytes(result)
