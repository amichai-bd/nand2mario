"""Independent per-update model of the approved contact/power contract."""
from dataclasses import dataclass, replace

import blocks_reference as blocks
from movement_reference import solid
from motion_reference import Player, step, UNIT, HEIGHT, TILE

TITLE, PLAYING, RETRY, PAUSED, WON = range(5)
SMALL, LARGE, THROWER = range(3)
NORMAL, GROW, HURT, SAFE = range(4)
ITEMS = ((96, 88), (264, 72), (464, 88), (656, 80))
ENEMY_Y = 120 * UNIT
GROW_UPDATES, HURT_UPDATES, SAFE_UPDATES = 32, 32, 96
STAR_UPDATES, THROW_UPDATES, SHOT_UPDATES = 248, 8, 64
BLOCK_RESET = blocks.reset()


@dataclass(frozen=True)
class Shot:
    x: int = 0
    y: int = 0
    vx: int = 0
    vy: int = 0
    ttl: int = 0


@dataclass(frozen=True)
class World:
    player: Player = Player()
    mode: int = TITLE
    enemy_x: int = 256 * UNIT
    enemy_vx: int = 8
    collected: int = 0
    score: int = 0
    timer: int = 0
    previous: int = 0
    power: int = SMALL
    phase: int = NORMAL
    phase_timer: int = 0
    invincible: int = 0
    throw: int = 0
    alive: bool = True
    crouch: bool = False
    shot: Shot = Shot()
    blocks: tuple = BLOCK_RESET
    coins: int = 0
    effect_tile: int = 0
    effect_x: int = 0
    effect_y: int = 0
    effect_timer: int = 0
    block_dirty: int = 0


def block_layer(world):
    """The solidity override #303 adds to terrain for one world state."""
    return lambda column, row, ascending: blocks.solid(world.blocks, column, row, ascending)


def contact_top(world):
    """Large and thrower raise the entity-contact box top by 2 pixels unless crouching."""
    if world.power != SMALL and not world.crouch:
        return world.player.y - 2 * UNIT
    return world.player.y


def overlap(world, x, y, height=8):
    """Half-open boxes in sixteenth-pixel units against the contact box."""
    p = world.player
    top = contact_top(world)
    return (p.x < x + 128 and p.x + 128 > x
            and top < y + height * UNIT and p.y + HEIGHT > y)


def power_up(world):
    """Entry point for #303 pickups; from small it always restarts GROW."""
    if world.power == SMALL:
        return replace(world, power=LARGE, phase=GROW, phase_timer=GROW_UPDATES)
    if world.power == LARGE:
        return replace(world, power=THROWER)
    return world


def grant_star(world):
    return replace(world, invincible=STAR_UPDATES)


def _timers(world):
    w = world
    if w.phase_timer:
        t = w.phase_timer - 1
        if t == 0:
            w = replace(w, phase_timer=SAFE_UPDATES if w.phase == HURT else 0,
                        phase=SAFE if w.phase == HURT else NORMAL)
        else:
            w = replace(w, phase_timer=t)
    if w.invincible:
        w = replace(w, invincible=w.invincible - 1)
    if w.throw:
        w = replace(w, throw=w.throw - 1)
    if w.effect_timer:
        left = w.effect_timer - 1
        w = replace(w, effect_timer=left, effect_y=w.effect_y - UNIT,
                    effect_tile=w.effect_tile if left else 0)
    return w


def _blocked(extra, column, row):
    return solid(column, row) or bool(extra and extra(column, row, False))


def _move_x(x, y, vx, extra=None):
    """One shot axis; a solid tile at the leading edge cancels and reverses."""
    nx = x + vx
    column = (nx + 127) // TILE if vx > 0 else nx // TILE
    if any(_blocked(extra, column, row) for row in range(y // TILE, (y + 127) // TILE + 1)):
        return x, -vx
    return nx, vx


def _move_y(x, y, vy, extra=None):
    ny = y + vy
    row = (ny + 127) // TILE if vy > 0 else ny // TILE
    if any(_blocked(extra, column, row) for column in range(x // TILE, (x + 127) // TILE + 1)):
        return y, -vy
    return ny, vy


def _shot(world):
    s = world.shot
    if not s.ttl:
        return world
    extra = block_layer(world)
    x, vx = _move_x(s.x, s.y, s.vx, extra)
    y, vy = _move_y(x, s.y, s.vy, extra)
    ttl = s.ttl - 1
    if x < 0 or x >= 760 * UNIT or y < 0 or y >= 144 * UNIT:
        ttl = 0
    alive = world.alive
    if ttl and alive and 0 < x - world.enemy_x + 128 < 256 and 0 < y - ENEMY_Y + 128 < 256:
        alive, ttl = False, 0
    return replace(world, shot=Shot(x, y, vx, vy, ttl) if ttl else Shot(), alive=alive)


def world_update(world, buttons):
    w = _timers(world)
    p = w.player
    crouch = w.power != SMALL and p.grounded and p.jump == 0 and bool(buttons & 8)
    w = replace(w, crouch=crouch)
    shot = w.shot
    if (w.power == THROWER and not crouch and not shot.ttl
            and buttons & 32 and not world.previous & 32):
        shot = Shot(p.x, p.y + 4 * UNIT, 2 * UNIT if p.facing == 0 else -2 * UNIT,
                    2 * UNIT, SHOT_UPDATES)
        w = replace(w, shot=shot, throw=THROW_UPDATES)
    masked = buttons & ~3 if crouch else buttons
    report = []
    p = step(p, masked, block_layer(w), report)
    w = _resolve_block(replace(w, player=p), report[0] if report else None)
    p = w.player
    x, vx = w.enemy_x, w.enemy_vx
    if w.alive:
        x = x + vx
        if x >= 296 * UNIT:
            x, vx = 296 * UNIT, -8
        elif x <= 240 * UNIT:
            x, vx = 240 * UNIT, 8
    w = replace(w, player=p, enemy_x=x, enemy_vx=vx, timer=(w.timer + 1) & 65535,
                previous=buttons)
    w = _shot(w)
    if p.fell:
        return replace(w, mode=RETRY)
    if w.alive and overlap(w, w.enemy_x, ENEMY_Y):
        if w.invincible:
            w = replace(w, alive=False)
        elif (p.y + HEIGHT) // UNIT - ENEMY_Y // UNIT <= 4:
            w = replace(w, alive=False, player=replace(
                p, grounded=False, jump=1, index=13, saved=0, pose=4))
        elif w.phase in (HURT, SAFE):
            pass
        elif w.power != SMALL:
            w = replace(w, power=SMALL, phase=HURT, phase_timer=HURT_UPDATES, throw=0)
        else:
            return replace(w, mode=RETRY)
    collected = w.collected
    for index, (item_x, item_y) in enumerate(ITEMS):
        if overlap(w, item_x * UNIT, item_y * UNIT):
            collected |= 1 << index
    mode = WON if overlap(w, 736 * UNIT, 112 * UNIT, 16) else PLAYING
    return replace(w, mode=mode, collected=collected, score=collected.bit_count())


def _resolve_block(world, hit):
    """One head hit, before the enemy step and every other contact."""
    states, coins, tile, x, y, grant = blocks.resolve(
        world.blocks, world.coins, world.power, hit)
    if tile:
        # The changed block's display columns are republished by the streamer,
        # which runs outside this update, so the mark survives it.
        world = replace(world, effect_tile=tile, effect_x=x * UNIT,
                        effect_y=y * UNIT, effect_timer=blocks.EFFECT_UPDATES,
                        block_dirty=x // 8 + 1)
    world = replace(world, blocks=states, coins=coins)
    if grant == 'power':
        return power_up(world)
    if grant == 'star':
        return grant_star(world)
    return world


def update(world, buttons):
    """Flow decisions precede world updates; resume never queues a jump."""
    if not isinstance(buttons, int) or not 0 <= buttons <= 255:
        raise ValueError('buttons must be a byte')
    edges = buttons & ~world.previous
    fresh = World(player=replace(Player(), previous=buttons), mode=PLAYING, previous=buttons)
    if world.mode == PAUSED:
        if edges & 64:
            return fresh
        return replace(world, mode=PLAYING if edges & 128 else PAUSED, previous=buttons,
                       player=replace(world.player, previous=buttons))
    if world.mode in (RETRY, WON):
        return fresh if edges & 128 else replace(world, previous=buttons)
    if world.mode == TITLE:
        if not edges & 128:
            return replace(world, previous=buttons)
        world = replace(world, mode=PLAYING)
    elif edges & 128:
        return replace(world, mode=PAUSED, previous=buttons,
                       player=replace(world.player, previous=buttons))
    return world_update(world, buttons)


def selected_pose(world):
    """Displayed pose index; scene preparation never advances state."""
    large = world.power != SMALL
    if world.mode == TITLE:
        return 0
    if world.mode == RETRY:
        return 11 if large else 5
    if world.phase == HURT:
        return 15 if (world.phase_timer - 1) & 4 else 14
    if world.throw:
        return 17
    if world.crouch:
        return 16
    if world.phase == GROW:
        large = not (world.phase_timer - 1) & 4
    pose = world.player.pose
    if pose == 5:
        return 13 if large else 12
    return pose + (6 if large else 0)


def hidden(world):
    """Blink parity uses timer-1 so every 4-update block is aligned and the window ends visible."""
    return (world.player.fell or (world.phase == SAFE and bool((world.phase_timer - 1) & 4))
            or (world.invincible > 0 and bool((world.invincible - 1) & 4)))
