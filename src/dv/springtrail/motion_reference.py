"""Independent per-update model of the approved original motion contract."""
from dataclasses import dataclass, replace

from movement_reference import solid, world_tile

UNIT = 16
WIDTH = 8 * UNIT
HEIGHT = 16 * UNIT
TILE = 8 * UNIT


def _solid(extra, column, row, ascending=False):
    """Terrain, then the optional block layer #303 supplies. Terrain always wins."""
    return solid(column, row) or bool(extra and extra(column, row, ascending))


@dataclass(frozen=True)
class Player:
    x: int = 24 * UNIT
    y: int = 112 * UNIT
    vx: int = 0
    vy: int = 0
    grounded: bool = True
    previous: int = 0
    camera: int = 0
    fell: bool = False
    counter: int = 0
    direction: int = 0
    speed: int = 0
    phase: int = 0
    animation: int = 1
    pose: int = 0
    jump: int = 0
    index: int = 0
    saved: int = 0
    facing: int = 0


def profile(index):
    """Original player binding of the approved piecewise displacement profile."""
    if not 0 <= index < 26:
        raise ValueError('profile index must be 0..25')
    if index < 2:
        return 4
    if index < 4:
        return 3
    if index < 13:
        return 2
    if index < 20:
        return 1
    return int(index in (21, 23))


def _select(player, buttons):
    p = player
    if buttons & 32:
        if p.jump == 0:
            p = replace(p, speed=2 if p.counter < 3 else 4)
    elif p.speed == 4:
        p = replace(p, speed=2)
    if buttons & 16 and not p.previous & 16 and p.jump == 0 and p.grounded:
        p = replace(p, grounded=False, jump=1, index=0 if p.speed == 4 else 2,
                    saved=0, speed=4 if p.speed == 4 else 2, counter=48, pose=4)
    if buttons & 32 and not p.previous & 32 and p.counter == 6:
        p = replace(p, counter=0)
    if p.grounded and p.animation % 4 == 0:
        p = replace(p, pose=1 if p.pose >= 3 else p.pose + 1)
    return p


def _horizontal(player, buttons, extra=None):
    p = replace(player, vx=0)
    if p.direction == 3:
        if p.counter:
            return replace(p, counter=(p.counter - 1) & 255)
        p = replace(p, direction=0)
        return replace(p, pose=0, animation=1, speed=0) if p.jump == 0 else p
    if p.counter == 6 and p.speed == 0:
        p = replace(p, speed=2)
    intent = 1 if buttons & 1 else 2 if buttons & 2 else 0
    if not intent:
        if p.counter:
            p = replace(p, counter=(p.counter - 1) & 255, speed=0)
            intent = p.direction
        else:
            p = replace(p, direction=0)
            return replace(p, pose=0, animation=1, speed=0) if p.jump == 0 else p
    if not intent:
        return p
    if p.direction in (1, 2) and intent != p.direction:
        return replace(p, direction=3, counter=8,
                       pose=5 if p.jump == 0 else p.pose,
                       animation=1 if p.jump == 0 else p.animation)
    p = replace(p, facing=0 if intent == 1 else 32)
    if buttons & (1 if intent == 1 else 2) and p.counter != 6:
        p = replace(p, counter=(p.counter + 1) & 255, direction=intent)
    phase = p.phase ^ 1
    distance = phase if p.speed == 0 else 1 if p.speed == 2 else 1 + phase
    dx = distance * UNIT * (1 if intent == 1 else -1)
    x = max(0, min(760 * UNIT, p.x + dx))
    blocked = x != p.x + dx
    if dx:
        column = (x + WIDTH - 1) // TILE if dx > 0 else x // TILE
        if any(_solid(extra, column, row) for row in range(p.y // TILE, (p.y + HEIGHT - 1) // TILE + 1)):
            x = column * TILE - WIDTH if dx > 0 else (column + 1) * TILE
            blocked = True
    return replace(p, x=x, vx=0 if blocked else dx, phase=phase,
                   animation=(p.animation + (1 if intent == 1 else -1)) & 255)


def _vertical(player, buttons, extra=None, report=None):
    p = player
    if p.jump == 1 and not buttons & 16 and p.index < 15:
        p = replace(p, saved=max(0, p.index - 1), index=15)
    if p.jump in (1, 2) and p.saved and p.index < 15:
        p = replace(p, index=p.saved, saved=0)
    if p.jump == 0:
        support = p.y + HEIGHT
        if support % TILE == 0 and any(_solid(extra, column, support // TILE)
                for column in range(p.x // TILE, (p.x + WIDTH - 1) // TILE + 1)):
            return replace(p, vy=0, grounded=True)
        p = replace(p, jump=3, grounded=False, pose=4)
    if p.jump == 1 and p.index < 26:
        dy = -profile(p.index) * UNIT
        p = replace(p, index=p.index + 1)
    elif p.jump in (1, 2):
        index = 25 if p.jump == 1 else p.index
        dy = profile(index) * UNIT
        p = replace(p, jump=2 if index else 3, index=max(0, index - 1))
    else:
        dy = 4 * UNIT
    y = p.y + dy
    if dy:
        row = (y + HEIGHT - 1) // TILE if dy > 0 else y // TILE
        columns = range(p.x // TILE, (p.x + WIDTH - 1) // TILE + 1)
        hit = next((c for c in columns if _solid(extra, c, row, dy < 0)), None)
        if hit is not None:
            if dy > 0:
                return replace(p, y=row * TILE - HEIGHT, vy=0, grounded=True,
                               jump=0, index=0, saved=0)
            # The ascending scan reports the first solid cell so #303 can resolve it.
            if report is not None:
                report.append((hit, row))
            return replace(p, y=(row + 1) * TILE, vy=0, grounded=False,
                           jump=2, index=0, saved=0)
    return replace(p, y=y, vy=dy, grounded=False)


def step(player, buttons, blocked=None, report=None):
    """One PLAY update. Mode pause/restart is owned by the interaction caller.

    `blocked(column, row, ascending)` adds solid cells outside the terrain map;
    `report` collects the ascending scan's first solid cell as (column, row).
    """
    if not isinstance(buttons, int) or not 0 <= buttons <= 255:
        raise ValueError('buttons must be a byte')
    if player.fell:
        return replace(player, previous=buttons)
    p = _vertical(_horizontal(_select(player, buttons), buttons, blocked),
                  buttons, blocked, report)
    return replace(p, previous=buttons, camera=max(0, min(608, p.x // UNIT - 72)),
                   fell=p.y >= 144 * UNIT)
