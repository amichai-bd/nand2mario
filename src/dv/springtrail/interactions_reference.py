"""Independent rules for Springtrail interactions; no observed state inputs."""
from dataclasses import dataclass, replace

from movement_reference import Player, step

TITLE, PLAYING, RETRY, PAUSED, WON = range(5)
ITEMS = ((96, 88), (264, 72), (464, 88), (656, 80))


@dataclass(frozen=True)
class Game:
    player: Player = Player()
    mode: int = TITLE
    enemy_x: int = 256 * 16
    enemy_vx: int = 8
    collected: int = 0
    score: int = 0
    timer: int = 0
    previous: int = 0


def overlap(player, x, y, height=8):
    """Half-open boxes in sixteenth-pixel units, including fractional Y."""
    return (player.x < x + 128 and player.x + 128 > x
            and player.y < y + height * 16 and player.y + 256 > y)


def world_update(game, buttons, step=step):
    player = step(game.player, buttons)
    x = game.enemy_x + game.enemy_vx
    vx = game.enemy_vx
    if x >= 296 * 16:
        x, vx = 296 * 16, -8
    elif x <= 240 * 16:
        x, vx = 240 * 16, 8
    updated = replace(game, player=player, enemy_x=x, enemy_vx=vx,
                      timer=(game.timer + 1) & 65535, previous=buttons)
    if player.fell or overlap(player, x, 120 * 16):
        return replace(updated, mode=RETRY)
    collected = game.collected
    for index, (item_x, item_y) in enumerate(ITEMS):
        if overlap(player, item_x * 16, item_y * 16):
            collected |= 1 << index
    mode = WON if overlap(player, 736 * 16, 112 * 16, 16) else PLAYING
    return replace(updated, mode=mode, collected=collected,
                   score=collected.bit_count())


def update(game, buttons, step=step):
    """Flow decisions precede world updates; resume never queues a jump.

    `step` selects the player model; a restart resets that model's player.
    """
    fresh = type(game.player)
    edges = buttons & ~game.previous
    if game.mode == PAUSED:
        if edges & 64:
            return Game(player=replace(fresh(), previous=buttons),
                        mode=PLAYING, previous=buttons)
        if edges & 128:
            return replace(game, mode=PLAYING, previous=buttons,
                           player=replace(game.player, previous=buttons))
        return replace(game, previous=buttons,
                       player=replace(game.player, previous=buttons))
    if game.mode in (RETRY, WON):
        if edges & 128:
            return Game(player=replace(fresh(), previous=buttons),
                        mode=PLAYING, previous=buttons)
        return replace(game, previous=buttons)
    if game.mode == TITLE:
        if not edges & 128:
            return replace(game, previous=buttons)
        # Retain #261's title Start+direction first movement update.
        game = replace(game, mode=PLAYING)
    elif edges & 128:
        return replace(game, mode=PAUSED, previous=buttons,
                       player=replace(game.player, previous=buttons))
    return world_update(game, buttons, step)
