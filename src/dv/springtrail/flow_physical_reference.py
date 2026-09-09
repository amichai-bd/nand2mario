"""One-frame-lag flow predictions from frozen timing and public input dots."""
from interactions_reference import Game, update
from interaction_routes import SUCCESS, DEATH_RETRY

PERIOD = 70224
VISIBLE = 65664

HELD_SUCCESS = (
    (161, 9), (49, 10), (33, 24), (49, 10), (33, 40), (49, 10),
    (33, 52), (49, 10), (33, 32), (49, 10), (33, 24), (49, 10),
    (33, 40), (49, 10), (33, 21), (49, 10), (33, 37), (0, 1),
)
HELD_DEATH_RETRY = (
    (161, 9), (49, 10), (33, 24), (49, 10), (33, 40), (49, 10),
    (33, 84), (128, 1),
)

SUCCESS_FLOW = HELD_SUCCESS + (
    (128, 1), (0, 2), (128, 3), (16, 1), (144, 1), (16, 1),
    (128, 1), (192, 2), (64, 1), (128, 1), (0, 1), (64, 2),
    (0, 1), (33, 16),
)
CAPTURES = {
    'feasibility': (8,),
    'success': (80, 117, 180, 270, 313, 360, 361, 363, 364, 366,
                367, 368, 369, 370, 371, 373, 374, 376, 391, 392, 394),
    'death-retry': (117, 180, 187, 188),
}


def plan(mode):
    assert mode in CAPTURES, 'FLOW_MODE'
    segments = ((0, 8),) if mode == 'feasibility' else (
        SUCCESS_FLOW if mode == 'success' else HELD_DEATH_RETRY)
    return segments, CAPTURES[mode]


def visible_boundary(dot, lcd):
    return type(dot) is int and dot >= lcd and (dot-lcd) % PERIOD < VISIBLE


def predict(frame, events, lcd):
    """Source frame n publishes state after n-1 sampled updates (n>=1)."""
    assert type(lcd) is int and lcd > 0, 'FLOW_LCD_ANCHOR'
    assert type(frame) is int and frame >= 1, 'FLOW_FRAME_NUMBER'
    assert all(events[i][0] < events[i+1][0] for i in range(len(events)-1)), 'FLOW_INPUT_ORDER'
    assert all(visible_boundary(dot, lcd) and type(mask) is int and 0 <= mask <= 255
               for dot, mask in events), 'FLOW_INPUT_WINDOW'
    state, mask, index = Game(), 0, 0
    for number in range(frame-1):
        sample = lcd+number*PERIOD+VISIBLE
        while index < len(events) and events[index][0] < sample:
            mask = events[index][1]
            index += 1
        state = update(state, mask)
    return state


def expected_snapshot(metadata, frame, events, epoch, lcd, renderer=None):
    """The planned frame chooses expectation; metadata only confirms it."""
    assert metadata['epoch'] == epoch and metadata['seq'] == frame, 'FLOW_SNAPSHOT_IDENTITY'
    dot = metadata['dot']
    assert lcd+frame*PERIOD+143*456 <= dot < lcd+frame*PERIOD+144*456, 'FLOW_SNAPSHOT_COMPLETION'
    state = predict(frame, events, lcd)
    if renderer is None:
        from flow_frames import image
        renderer = image
    return state, renderer(state)


def schedule(segments):
    """Return exact visible-frame input windows and logical update count."""
    changes, count = [], 0
    for buttons, duration in segments:
        assert type(duration) is int and duration > 0, 'FLOW_DURATION'
        assert type(buttons) is int and 0 <= buttons <= 255, 'FLOW_BUTTONS'
        if not changes or changes[-1][1] != buttons:
            changes.append((count, buttons))
        count += duration
    return changes, count
