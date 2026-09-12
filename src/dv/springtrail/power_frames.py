"""Contact/power poses, shot and world objects from approved sources only."""
from composition_reference import courier as approved_courier, raster
from hud_reference import MAPS, image as hud_image
from motion_frames import tiles
from power_reference import selected_pose, hidden as player_hidden, STAGE_ITEMS, STAGE_GOAL_X, ENEMY_Y

# Pose index to approved core map; six-piece maps share the small pose's feet.
CORE_POSES = {12: 'small-skid', 13: 'large-skid', 14: 'small-hurt', 15: 'large-hurt',
              16: 'large-crouch', 17: 'large-throw'}
SHOT_TILE = 107


def vram(tile):
    """VRAM id of one approved core tile after the startup copies."""
    if tile < 16:
        return 42 + tile
    if 16 <= tile <= 19:
        return 94 + tile - 16
    if 21 <= tile <= 26:
        return 98 + tile - 21
    if 27 <= tile <= 42:
        return 42 + tile - 11
    if 43 <= tile <= 45:
        return 104 + tile - 43
    if tile == 54:
        return SHOT_TILE
    raise ValueError(f'core tile {tile} is not loaded')


def pieces(pose):
    """(x, y, vram, x_flip) per piece; the blank crouch row is not composed."""
    source = MAPS[CORE_POSES[pose]]
    parts = [p for p in source['pieces'] if p['tile'] != 46]
    lift = 8 if source['height'] == 24 else 0
    return [(p['x'], p['y'] - lift, vram(p['tile']), p['x_flip']) for p in parts]


def courier(pose, left=False, x=0, y=0, hidden=False):
    if pose < 12:
        return approved_courier(pose, left, x, y, hidden)
    result = bytearray()
    for px, py, tile, flip in pieces(pose):
        sx = x + (8-px if left else px)
        sy = y + py
        visible = not hidden and -7 <= sx < 160 and -7 <= sy < 144
        result.extend(((sy+16)&255 if visible else 0, (sx+8)&255, tile, 32*(flip != left)))
    return bytes(result)


def entry(x, y, tile, hidden=False):
    visible = not hidden and -7 <= x < 160 and -7 <= y < 144
    return bytes(((y+16)&255 if visible else 0, (x+8)&255, tile, 0))


def scene(world, extra=b''):
    """`extra` is the block layer's release effect, appended after the shot."""
    p = world.player
    data = bytearray(courier(selected_pose(world), bool(p.facing),
                             p.x//16-p.camera-4, p.y//16, player_hidden(world)))
    objects = [(world.enemy_x//16, ENEMY_Y//16, 16, not world.alive)]
    objects += [(x, y, 18, bool(world.collected & (1 << i))) for i, (x, y) in enumerate(STAGE_ITEMS[world.stage])]
    objects += [(STAGE_GOAL_X[world.stage], 112, 20, False)]
    for x, y, tile, hide in objects:
        for half in (0, 1):
            data += entry(x-p.camera, y+8*half, tile+half, hide)
    if world.shot.ttl:
        data += entry(world.shot.x//16-p.camera, world.shot.y//16, SHOT_TILE)
    data += extra
    assert len(data) <= 160
    return bytes(data) + bytes(160-len(data))


def image(world):
    return hud_image(world, object_pixels=raster(scene(world), tiles()))
