"""Original complete frames selected solely by independently modeled game state."""
from interactions_reference import Game
from movement_reference import solid
from reference import ART, GLYPHS
from scene_art import PAIRS
from scene_reference import image as oam


def image(game=Game()):
    pixels = bytearray(23040)
    for y in range(144):
        for x in range(160):
            wx = x + game.player.camera
            if solid(wx//8, y//8):
                pixels[y*160+x] = int(ART['ground'][y%8][wx%8])
            if game.mode == 0 and y//8 in (5, 7) and 4 <= x//8 < 15:
                letter = ('SPRINGTRAIL' if y//8 == 5 else 'PRESS START')[x//8-4]
                if letter != ' ' and y%8 < 7 and 1 <= x%8 <= 5:
                    pixels[y*160+x] = 3 if GLYPHS[letter][y%8] & (1 << (5-x%8)) else 0
    entries = [tuple(oam(game)[i:i+4]) for i in range(0, 36, 4)]
    # DMG priority is smaller X, then earlier OAM index. Draw low priority first.
    for index in sorted(range(9), key=lambda i: (entries[i][1], i), reverse=True):
        oy, ox, tile, flags = entries[index]
        assert flags == 0
        rows = tuple(ART['head'])+tuple(ART['feet']) if tile == 12 else PAIRS[tile]
        for sy, row in enumerate(rows):
            y = oy-16+sy
            if not 0 <= y < 144:
                continue
            for sx, value in enumerate(row):
                x = ox-8+sx
                if 0 <= x < 160 and value != '0':
                    pixels[y*160+x] = int(value)
    return bytes(pixels)
