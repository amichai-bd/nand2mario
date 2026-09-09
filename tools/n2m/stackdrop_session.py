"""Bounded screen/action loop using ordinary Stackdrop UART commands."""
import time

from . import generated_interfaces as abi
from .host_play import decode_frame
from .stackdrop_player import choose

FRAME = 70224


def play(client, image, prior, mode, decode, retain, *, sleep=time.sleep,
         clock=time.monotonic, ready=lambda: None):
    """One frozen comparison run; prior binds a known certain paused session."""
    def reg(name):
        return client.read_host(getattr(abi, 'HOST_REG_'+name))

    def dot():
        high, low = reg('DOT_HI'), reg('DOT_LO')
        if high != reg('DOT_HI'):
            raise ValueError('STACKDROP_DOT_ROLLOVER')
        return high*2**32+low

    def safe():
        if (reg('STATE') != abi.STATE_PAUSED or
                reg('INPUT_SOURCE') != abi.INPUT_SOURCE_UART or
                reg('INPUT') != 0 or reg('INPUT_EFFECTIVE') != 0 or
                reg('IMAGE_VALID') != 1):
            raise ValueError('STACKDROP_INITIAL_STATE')

    def advance(ticks):
        begin = dot()
        client.control('RUN')
        deadline = clock()+2
        while True:
            sleep(.015)
            current = dot()
            if current-begin >= ticks:
                break
            if clock() >= deadline:
                raise ValueError('STACKDROP_PROGRESS_TIMEOUT')
        client.control('HALT')
        end = dot()
        if not ticks <= end-begin < 4194304:
            raise ValueError('STACKDROP_PROGRESS_BOUND')
        return dict(begin=begin, end=end)

    if mode not in ('baseline', 'strategy'):
        raise ValueError('STACKDROP_MODE')
    if client.sequence != prior['sequence']:
        raise ValueError('STACKDROP_SESSION_CHANGED')
    identity = client.identify()
    if identity['build_id'] != prior['build_id']:
        raise ValueError('STACKDROP_BUILD_CHANGED')
    safe()
    if dot() != prior['halt_dot']:
        raise ValueError('STACKDROP_PAUSED_DOT_CHANGED')
    old, _ = client.snapshot()
    if (old['epoch'] != prior['frame']['epoch'] or
            old['seq'] != prior['frame']['sequence'] or
            old['dot'] != prior['frame']['dot']):
        raise ValueError('STACKDROP_OLD_FRAME_CHANGED')
    ready()
    loaded = client.load(image)
    epoch = (old['epoch']+2) % 2**32
    client.control('INPUT', 0)
    retain('load', dict(identity=identity, loaded=loaded, epoch=epoch,
                        startup=advance(6*FRAME)))
    previous = None

    def observe():
        nonlocal previous
        metadata, packed = client.snapshot()
        pixels, current = decode_frame(metadata, packed, previous, epoch=epoch)
        screen = decode(pixels)
        if current['dot'] > dot():
            raise ValueError('STACKDROP_FUTURE_FRAME')
        previous = current
        retain('frame', dict(metadata=metadata, packed=packed.hex(), screen=screen))
        return screen

    def action(mask):
        neutral = advance(2*FRAME)
        applied = client.control('INPUT', mask)
        pressed = advance(3*FRAME)
        client.control('INPUT', 0)
        retain('action', dict(mask=mask, neutral=neutral, applied=applied,
                              pressed=pressed))
        return observe()

    screen = observe()
    if screen['status'] != 0 or screen['score'] != 0 or any(screen['board']):
        raise ValueError('STACKDROP_FRESH_TITLE')
    screen = action(128)
    if screen['status'] != 1 or screen['score'] != 0:
        raise ValueError('STACKDROP_FRESH_PLAY')
    drops, actions = 0, 1  # Start counts toward the same action ceiling.
    while drops < 8 and screen['status'] == 1:
        if actions >= 64:
            raise ValueError('STACKDROP_ACTION_LIMIT')
        decision = choose(screen, mode)
        retain('decision', dict(frame=previous, **decision))
        screen = action(decision['mask'])
        drops += decision['mask'] == 32
        actions += 1
    if screen['status'] not in (1, 2):
        raise ValueError('STACKDROP_FINAL_STATUS')
    safe()
    return dict(mode=mode, score=screen['score'], drops=drops, actions=actions,
                status=screen['status'], frame=previous, halt_dot=dot(),
                build_id=identity['build_id'])
