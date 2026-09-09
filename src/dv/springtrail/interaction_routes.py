"""Frozen ordinary-input routes derived before DUT execution.

Counts are logical game updates, not host sleeps or display-frame identities.
The caller owns the separately reviewed JOYP/visibility schedule.
"""
from interactions_reference import Game, update

# Start+B+Right, then B+Right with isolated A edges. The final neutral update
# descends into the goal's half-open box; no state or expected data enters ROM.
SUCCESS = (
    (161, 1), (33, 8), (49, 1), (33, 33), (49, 1), (33, 49),
    (49, 1), (33, 61), (49, 1), (33, 41), (49, 1), (33, 33),
    (49, 1), (33, 49), (49, 1), (33, 30), (49, 1), (33, 46), (0, 1),
)

# The same first three jumps collect item1. Omitting the next jump falls into
# the second gap. A new Start edge restores all modeled logical state.
DEATH_RETRY = (
    (161, 1), (33, 8), (49, 1), (33, 33), (49, 1), (33, 49),
    (49, 1), (33, 93), (128, 1),
)

# mode,x,y,vy,camera,enemy_x,enemy_vx,collected,score,timer. Coordinates/velocities
# use sixteenths of a pixel; camera is whole pixels. These literal checkpoints
# include all three gaps, patrol reversal, pickups and the alive goal contact.
SUCCESS_ANCHORS = {
    1: (1, 416, 1792, 0, 0, 4104, 8, 0, 0, 1),
    10: (1, 704, 1712, -80, 0, 4176, 8, 0, 0, 10),
    44: (1, 1792, 1200, -80, 40, 4448, 8, 0, 0, 44),
    80: (1, 2944, 984, 64, 112, 4736, -8, 0, 0, 80),
    94: (1, 3392, 1712, -80, 140, 4624, -8, 0, 0, 94),
    117: (1, 4128, 976, 12, 186, 4440, -8, 2, 1, 117),
    130: (1, 4544, 1024, 0, 212, 4336, -8, 2, 1, 130),
    156: (1, 5376, 1712, -80, 264, 4128, -8, 2, 1, 156),
    180: (1, 6144, 992, 16, 312, 3936, -8, 2, 1, 180),
    198: (1, 6720, 1712, -80, 348, 3888, 8, 2, 1, 198),
    232: (1, 7808, 1200, -80, 416, 4160, 8, 2, 1, 232),
    270: (1, 9024, 1112, 64, 492, 4464, 8, 2, 1, 270),
    282: (1, 9408, 1712, -80, 516, 4560, 8, 2, 1, 282),
    313: (1, 10400, 1072, -80, 578, 4664, -8, 10, 2, 313),
    340: (1, 11264, 424, 28, 608, 4448, -8, 10, 2, 340),
    360: (4, 11872, 1560, 64, 608, 4288, -8, 10, 2, 360),
}
DEATH_ANCHORS = {
    187: (2, 6272, 2336, 64, 320, 3880, -8, 2, 1, 187),
    188: (1, 384, 1792, 0, 0, 4096, 8, 0, 0, 0),
}


def expected(segments):
    """Complete expected logical states, without choosing DUT addresses."""
    state = Game()
    rows = []
    for buttons, count in segments:
        for _ in range(count):
            state = update(state, buttons)
            rows.append(dict(update=len(rows)+1, buttons=buttons, state=state))
    return rows


def anchor(game):
    p = game.player
    return (game.mode, p.x, p.y, p.vy, p.camera, game.enemy_x,
            game.enemy_vx, game.collected, game.score, game.timer)
