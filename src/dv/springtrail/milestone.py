"""Fixed milestone input and capture indices, chosen before DUT observations."""
from interaction_routes import SUCCESS, DEATH_RETRY

LCD = 76964
PERIOD = 70224
PHASE = 4096
ROM_SHA256 = 'b551c56252761d953bcf3b64270d819e3342b710299c3bff6866d4dcae8ba667'


def checkpoint(n):
    return LCD + n * PERIOD + PHASE


def masks(short=False):
    if short:
        return [129, 1, 1, 1]
    success = [mask for mask, count in SUCCESS for _ in range(count)]
    death = [mask for mask, count in DEATH_RETRY for _ in range(count)]
    # After the first win, exercise the existing fall/retry route, then pause,
    # resume and Select restart. Resume with Start held restores the route's
    # initial edge history without advancing the freshly reset world.
    result = success + [128] + death + [0,128,0,128,0,128,0,64,128,0,128] + success
    # Start resets WON to PLAYING; the following held Start in the original
    # route has no new edge. Its first moving update restores the route phase.
    while len(result) < 3600:
        result += [128] + success
    return result[:3600]


def plan(short=False):
    buttons = masks(short)
    inputs = [dict(dot=checkpoint(i+2), buttons=mask)
              for i, mask in enumerate(buttons + [0, 0])]
    count = len(buttons) + 4
    captures = [dict(seq=f, pause_dot=checkpoint(f+1),
                     reference_offset=(f+2)*23040,
                     input_after=inputs[f-1]['buttons'] if 1 <= f < count-1 else None)
                for f in range(count)]
    return dict(inputs=inputs, captures=captures, normal_frames=count,
                end_dot=checkpoint(count), scripted_updates=len(buttons))
