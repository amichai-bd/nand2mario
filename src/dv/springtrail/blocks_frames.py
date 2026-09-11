"""Approved terrain sources and the block layer's rendered background/objects."""
import json

import blocks_reference as B
from hud_reference import column as hud_column, image as hud_image
from composition_reference import raster
from motion_frames import SOURCE, TERRAIN, tiles
from power_frames import scene as power_scene, entry

TERRAIN_MAPS = json.loads((SOURCE / 'terrain-maps.json').read_text())
# Approved 16 by 16 map per tile base, as the contract's artwork table states.
DESIGNS = {B.SEALED: 'sealed', B.USED_TILE: 'used', B.CRACK: 'crack',
           B.REVEAL: 'reveal', B.SHARDS: 'shards', B.COIN_TILE: 'coin1',
           B.LEAF: 'leaf', B.GEM: 'gem'}


def atlas(base):
    """The four approved atlas tile indices behind one VRAM tile base."""
    return [piece['tile'] for piece in TERRAIN_MAPS[DESIGNS[base]]['pieces']]


def effect(world):
    """The four OAM entries of a live release effect, or nothing."""
    if not world.effect_tile:
        return b''
    x = world.effect_x // 16 - world.player.camera
    y = world.effect_y // 16
    return b''.join(entry(x + 8 * (index & 1), y + 8 * (index >> 1),
                          world.effect_tile + index) for index in range(4))


def scene(world):
    return power_scene(world, effect(world))


def column(world, index):
    """The sixteen tiles `DecodeColumn` publishes for one column.

    `hud_reference.column` defaults to the terrain-only table `columns.asm`
    encodes; the block layer is the explicit override this applies.
    """
    return hud_column(index, world.blocks)


def background(world):
    """Block pixels under the object layer; every block sits over blank sky."""
    pixels = bytearray(23040)
    for bx, _by, _kind, _content in B.BLOCKS:
        for half in (0, 1):
            for row, tile in B.column_tiles(world.blocks, bx + half).items():
                sx, sy = (bx + half) * 8 - world.player.camera, row * 8
                source = B.ATLAS_TILES[tile - B.FIRST_TILE]
                for y in range(8):
                    for x in range(8):
                        if 0 <= sx + x < 160 and 16 <= sy + y < 144:
                            pixels[(sy + y) * 160 + sx + x] = TERRAIN[y][source * 8 + x]
    for index, value in enumerate(raster(scene(world), tiles())):
        if value:
            pixels[index] = value
    return bytes(pixels)


def image(world):
    return hud_image(world, object_pixels=background(world))
