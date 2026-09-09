"""Original literal pixels selected by the independently predicted game state."""
from movement_reference import Player,world_tile
from reference import ART,GLYPHS


def image(player=Player(),title=False):
    pixels=bytearray()
    left=player.x//16-player.camera
    top=player.y//16
    for y in range(144):
        for x in range(160):
            wx=x+player.camera
            column,row=wx//8,y//8
            px,py=wx%8,y%8
            tile=world_tile(column,row)
            name={11:'ground',14:'seed',15:'zero'}.get(tile)
            shade=int(ART[name][py][px]) if name else 0
            if title and row in (5,7) and 4<=column<15:
                letter=('SPRINGTRAIL' if row==5 else 'PRESS START')[column-4]
                shade=3 if letter!=' ' and py<7 and 1<=px<=5 and GLYPHS[letter][py]&(1<<(5-px)) else 0
            if not player.fell and left<=x<left+8 and top<=y<top+16:
                sy=y-top
                object_shade=int(ART['head' if sy<8 else 'feet'][sy%8][x-left])
                if object_shade:shade=object_shade
            pixels.append(shade)
    return bytes(pixels)
