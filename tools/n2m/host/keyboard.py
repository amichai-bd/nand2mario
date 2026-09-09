"""Map focused console edges to complete ordinary UART button masks."""
from .. import generated_interfaces as abi

KEYS = {0x27: abi.BUTTON_RIGHT, 0x25: abi.BUTTON_LEFT,
        0x26: abi.BUTTON_UP, 0x28: abi.BUTTON_DOWN,
        0x5a: abi.BUTTON_A, 0x58: abi.BUTTON_B,
        0xa1: abi.BUTTON_SELECT, 0x0d: abi.BUTTON_START}


def run(client, console):
    values = {name: client.read_host(getattr(abi, 'HOST_REG_' + name))
              for name in ('IMAGE_VALID', 'INPUT_SOURCE', 'INPUT', 'INPUT_EFFECTIVE')}
    if values != dict(IMAGE_VALID=1, INPUT_SOURCE=0, INPUT=0, INPUT_EFFECTIVE=0):
        raise ValueError('keyboard requires valid image, UART ownership and neutral input')
    held = set()
    changes = 0
    reason = 'exit'
    # Once preflight passes, this command owns its input mask. It never changes
    # run/pause or source ownership. A failed preflight must not release another owner.
    try:
        while True:
            event = console.next_event()
            if event is None:
                continue
            if event[0] == 'focus-lost':
                reason = 'focus-lost'
                break
            _, code, down, modifiers = event
            if down and (code == 0x1b or code in (0x5b, 0x5c) or (code == 0x43 and modifiers & 0x0c)):
                reason = 'exit-key'
                break
            if code not in KEYS or (down and modifiers & 0x0f):
                continue
            before = set(held)
            if down:
                held.add(code)
            else:
                held.discard(code)
            if held != before:
                mask = sum(KEYS[key] for key in held)
                applied = client.control('INPUT', mask)
                client.record(dict(event='keyboard-mask', mask=mask, dot=applied['dot']))
                changes += 1
    finally:
        if not client.uncertain:
            released = client.control('INPUT', 0)
            client.record(dict(event='keyboard-release', mask=0, dot=released['dot']))
    return dict(changes=changes, exit_reason=reason, released=True)
