"""Current motion poses with approved pixels and unchanged HUD/world artwork."""
from composition_reference import BANK, courier as original_courier, raster
from composition_reference import scene as original_scene
from hud_reference import CORE, MAPS, glyph, CHARS, image as hud_image
from scene_art import PAIRS

import json
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[3] / 'src/sw/springtrail/assets/core'
TERRAIN = json.loads((SOURCE / 'terrain-tiles.json').read_text())['pixels']

CORE_TILES = (16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 43, 44, 45, 54)
from blocks_reference import ATLAS_TILES as BLOCK_TILES


def courier(pose, left=False, x=0, y=0, hidden=False):
    if pose != 12:
        return original_courier(pose, left, x, y, hidden)
    result = bytearray()
    for part in MAPS['small-skid']['pieces']:
        px = x + (8-part['x'] if left else part['x'])
        py = y + part['y']
        visible = not hidden and -7 <= px < 160 and -7 <= py < 144
        flags = 32*(part['x_flip'] != left)+64*part['y_flip']
        result.extend(((py+16)&255 if visible else 0, (px+8)&255,
                       94+part['tile']-16, flags))
    return bytes(result)


def selected_pose(game):
    return (0 if game.mode == 0 else 5 if game.mode == 2 else
            12 if game.player.pose == 5 else game.player.pose)


def scene(game):
    p = game.player
    player = courier(selected_pose(game), bool(p.facing),
                     p.x//16-p.camera-4, p.y//16, p.fell)
    # These unchanged original world objects remain independent of new physics.
    return player + original_scene(game)[16:64] + bytes(96)


def tiles():
    result = [[[0]*8 for _ in range(8)] for _ in range(140)]
    for tile, rows in PAIRS.items():
        for half in range(2):
            result[tile+half] = [list(map(int, row)) for row in rows[half*8:half*8+8]]
    for tile in range(32):
        result[42+tile] = [row[tile*8:tile*8+8] for row in BANK]
    for index, char in enumerate(CHARS):
        pixels = glyph(char)
        result[74+index] = [list(pixels[y*8:y*8+8]) for y in range(8)]
    # VRAM 94..107 hold approved core tiles 16..19, 21..26, 43..45 and 54.
    for index, tile in enumerate(CORE_TILES):
        result[94+index] = [row[tile*8:(tile+1)*8] for row in CORE]
    for index, tile in enumerate(BLOCK_TILES):
        result[108+index] = [row[tile*8:(tile+1)*8] for row in TERRAIN]
    return result


def image(game):
    return hud_image(game, object_pixels=raster(scene(game), tiles()))
