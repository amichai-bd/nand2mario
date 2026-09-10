"""Original HUD/terrain pixels and column expectations, independent of assembly."""
import json
from pathlib import Path

from composition_reference import BANK, raster, scene
from interactions_reference import Game
from movement_reference import world_tile
from reference import ART, GLYPHS
from scene_art import PAIRS

SOURCE = Path(__file__).resolve().parents[2] / 'sw/springtrail/assets/core'
CORE = json.loads((SOURCE / 'core-tiles.json').read_text())['pixels']
MAPS = json.loads((SOURCE / 'core-maps.json').read_text())
WORDS = ('TITLE', 'PLAY', 'RETRY', 'PAUSED', 'WON')
CHARS = tuple(sorted(set('TITLEPLAYRETRYPAUSEDWONSCORE01234')))
IDS = {char: 74 + index for index, char in enumerate(CHARS)}


def glyph(char):
    """Reconstruct approved glyph pixels; map IDs are local review-bank IDs."""
    spec = MAPS['glyph-' + char]
    assert (spec['width'], spec['height']) == (8, 8)
    out = bytearray(64)
    for piece in spec['pieces']:
        for y in range(8):
            for x in range(8):
                sx = 7-x if piece.get('x_flip', False) else x
                sy = 7-y if piece.get('y_flip', False) else y
                out[(piece['y']+y)*8+piece['x']+x] = CORE[sy][piece['tile']*8+sx]
    return bytes(out)


def column(index):
    if type(index) is not int or not 0 <= index < 96:
        raise ValueError('display column outside 0..95')
    return bytes(world_tile(index, row) for row in range(2, 18))


def entering(oldcamera, newcamera):
    """Only the entering margin changes; the final right margin is offscreen."""
    if any(type(n) is not int or not 0 <= n <= 608 for n in (oldcamera, newcamera)):
        raise ValueError('camera outside 0..608')
    old, new = oldcamera//8, newcamera//8
    if old == new:
        return None
    index = new+20 if new > old else new
    return index if index < 96 else None


def hud_tiles(game):
    if not 0 <= game.mode < 5 or not 0 <= game.score <= 4:
        raise ValueError('HUD mode/score outside game rules')
    return bytes([IDS[c] if c != ' ' else 0 for c in WORDS[game.mode].ljust(6)]
                 + [IDS[str(game.score)]])


def image(game=Game(), facing=False, *, object_pixels=None):
    """One prepared state: fixed HUD, world-coordinate playfield and clipped OBJ."""
    tiles = [[[0]*8 for _ in range(8)] for _ in range(74)]
    for tile, rows in PAIRS.items():
        for half in range(2):
            tiles[tile+half] = [list(map(int, row)) for row in rows[half*8:half*8+8]]
    for tile in range(32):
        tiles[42+tile] = [row[tile*8:tile*8+8] for row in BANK]
    # The former score/mode pairs are the last four entries. They no longer
    # consume OAM; the first sixteen retain their independent scene model.
    objects = (raster(scene(game, facing)[:64] + bytes(96), tiles)
               if object_pixels is None else object_pixels)
    assert len(objects) == 23040
    pixels = bytearray(23040)
    for y in range(16, 144):
        for x in range(160):
            wx = x + game.player.camera
            if world_tile(wx//8, y//8):
                pixels[y*160+x] = int(ART['ground'][y%8][wx%8])
            if game.mode == 0 and y//8 in (5, 7) and 4 <= x//8 < 15:
                letter = ('SPRINGTRAIL' if y//8 == 5 else 'PRESS START')[x//8-4]
                if letter != ' ' and y%8 < 7 and 1 <= x%8 <= 5:
                    pixels[y*160+x] = 3 if GLYPHS[letter][y%8] & (1 << (5-x%8)) else 0
            if objects[y*160+x]:
                pixels[y*160+x] = objects[y*160+x]
    for start, text in ((1, WORDS[game.mode].ljust(6)), (12, 'SCORE'), (18, str(game.score))):
        for offset, char in enumerate(text):
            if char == ' ':
                continue
            rows = glyph(char)
            for y in range(8):
                left = y*160+(start+offset)*8
                pixels[left:left+8] = rows[y*8:y*8+8]
    return bytes(pixels)
