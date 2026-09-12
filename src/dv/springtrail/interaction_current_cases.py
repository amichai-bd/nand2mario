"""Missing current interaction operands; expected state comes only from the model."""
from dataclasses import replace

from entities_cases import ADDRESSES, RANGES, state_bytes
from entities_reference import World, Entity, update
from motion_reference import Player
from power_reference import PLAYING, LARGE

TITLE = 'INTERACT UNIT'
SHORT = 1
SHORT_BOUND = 30000
FULL_BOUND = 160000
ROUTINE_BOUND = 24000


def operands():
    """Twenty ordinary UpdateGame inputs, without serialized expected outputs."""
    rows = []
    base = World(mode=PLAYING, alive=False)
    positions = ((96, 80), (264, 64), (464, 80), (656, 72))
    for index in range(1, 4):
        x, y = positions[index]
        rows.append((f'item-{index}-award', replace(base,
            player=Player(x=x*16, y=y*16), collected=(1 << index)-1,
            score=index), 0))
    for index, (x, y) in enumerate(positions):
        rows.append((f'item-{index}-once', replace(base,
            player=Player(x=x*16, y=y*16), collected=1 << index, score=1), 0))
    for name, x, vx in (('patrol-right-depart', 296*16, -8),
                         ('patrol-left-arrive', 240*16+8, -8),
                         ('patrol-left-depart', 240*16, 8)):
        rows.append((name, replace(base, alive=True, enemy_x=x, enemy_vx=vx), 0))
    for name, offset in (('patrol-edge-touch', 0), ('patrol-edge-overlap', 1)):
        rows.append((name, replace(base, alive=True,
            player=Player(x=248*16+8+offset, y=112*16)), 0))
    # Fell is authoritative even at these coordinates. These are precedence
    # operands, not a claim that falling and collection coincide on a live route.
    rows.append(('fell-before-item', replace(base,
        player=Player(x=96*16, y=80*16, fell=True)), 0))
    rows.append(('fell-before-goal', replace(base,
        player=Player(x=736*16, fell=True), collected=15, score=4), 0))
    rows.append(('select-ignored-playing', replace(base, timer=42), 64))
    # Relocated CURL records isolate dispatch priority, as in the existing
    # patrol/CURL overlap fixture; they do not change the stage's object layout.
    for subject, x, y, mask in (('item', 96, 80, 14), ('goal', 736, 112, 7)):
        contact = replace(base, player=Player(x=x*16, y=y*16),
            curl=Entity(x*16, (y+8)*16, 1, 20), collected=mask,
            score=mask.bit_count())
        rows.append((f'curl-fatal-before-{subject}', contact, 0))
        rows.append((f'curl-nonfatal-allows-{subject}', replace(contact, power=LARGE), 0))
    rows.append(('goal-frame-counter-wrap', replace(base,
        player=Player(x=736*16), collected=15, score=4, timer=65535), 0))
    return rows


def cases():
    result = []
    for name, before, buttons in operands():
        after = update(before, buttons)
        out = buttons & ~3 if after.crouch else buttons
        result.append(dict(name=name, kind='game', before=state_bytes(before, buttons),
                           after=state_bytes(after, out)))
    return result


def parts():
    rows = cases()
    return {chr(97+i): rows[start:start+5]
            for i, start in enumerate(range(0, len(rows), 5))}
