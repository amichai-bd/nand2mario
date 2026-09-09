"""Normal software operands and independent outcomes for the interaction unit."""
from dataclasses import replace

from interactions_reference import Game, Player, PLAYING, PAUSED, RETRY, WON, update


def groups():
    return [
        ('start-direction', Game(), [129]),
        ('right-turn', Game(mode=PLAYING, enemy_x=296*16-8), [0, 0]),
        ('left-turn', Game(mode=PLAYING, enemy_x=240*16+8, enemy_vx=-8), [0, 0]),
        ('contact-retry', Game(mode=PLAYING, player=Player(x=256*16)), [0, 64, 128]),
        ('enemy-edge', Game(mode=PLAYING, player=Player(x=248*16+8)), [0]),
        ('first-once', Game(mode=PLAYING, player=Player(x=96*16, y=80*16)), [0, 0]),
        ('second', Game(mode=PLAYING, player=Player(x=264*16, y=64*16), collected=1, score=1), [0]),
        ('third', Game(mode=PLAYING, player=Player(x=464*16, y=80*16), collected=3, score=2), [0]),
        ('fourth', Game(mode=PLAYING, player=Player(x=656*16, y=72*16), collected=7, score=3), [0, 0]),
        ('death-before-item', Game(mode=PLAYING, player=Player(x=96*16, y=80*16, fell=True)), [0]),
        ('goal-retry', Game(mode=PLAYING, player=Player(x=736*16), collected=15, score=4, timer=65535), [0, 64, 128]),
        ('death-before-goal', Game(mode=PLAYING, player=Player(x=736*16, fell=True)), [0]),
        ('pause-resume', Game(mode=PLAYING, timer=123), [128, 16, 16, 144, 16]),
        ('pause-restart', Game(mode=PAUSED, player=Player(x=760*16, camera=608), collected=15, score=4, timer=42), [192]),
        ('select-ignored', Game(mode=PLAYING, timer=42), [64]),
    ]


ADDRESSES = [0xc000] + list(range(0xc010, 0xc01e)) + [0xc024] + list(range(0xc026, 0xc02d))


def state_bytes(game, buttons=0):
    p = game.player
    def word(value):
        return (value & 65535).to_bytes(2, 'little')
    return (bytes([game.mode]) + word(p.x) + word(p.y) + word(p.vx) + word(p.vy)
            + bytes([p.grounded, buttons, p.previous]) + word(p.camera) + bytes([p.fell, game.previous])
            + word(game.enemy_x) + bytes([game.enemy_vx & 255, game.score]) + word(game.timer)
            + bytes([game.collected]))


def expected():
    records = []
    for name, initial, inputs in groups():
        game = initial
        for buttons in inputs:
            game = update(game, buttons)
            records.append(dict(group=name, buttons=buttons, state=state_bytes(game, buttons).hex()))
    return records
