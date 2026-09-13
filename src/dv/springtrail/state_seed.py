"""Current fixture state layout and ordinary CPU seed initialization.

Packing serializes independent input worlds; it does not predict behavior.
Reserved entity bytes are explicit zeros in the current 123-byte contract.
"""
from blocks_cases import ADDRESSES as OLD_ADDRESSES, RANGES as OLD_RANGES, state_bytes as old_bytes

ADDRESSES = OLD_ADDRESSES + list(range(0xc090,0xc097)) + list(range(0xc300,0xc338))
RANGES = OLD_RANGES + ((0xc090,7),(0xc300,56))

def state_bytes(w, buttons=0, new_level=0):
    data = bytearray(old_bytes(w,buttons,new_level))
    data += bytes((w.lives,w.pending,w.timer_sub,w.timer_low,w.timer_high,w.expiring,w.stage))
    for e in (w.curl,w.moving,w.falling):
        data += e.x.to_bytes(2,'little',signed=True) + e.y.to_bytes(2,'little',signed=True)
        data += bytes((e.state,e.timer,e.vx&255)) + bytes(9)
    data += bytes((w.patrol_frame,w.stomp,w.rider)) + bytes(5)
    assert len(data)==len(ADDRESSES)
    return bytes(data)


def seed_copy():
    """Copy SeedValues into current WRAM ranges using ordinary CPU writes."""
    lines = ['LD HL,SeedValues']
    for index, (address, count) in enumerate(RANGES):
        lines += [f'LD DE,${address:04X}', f'LD B,{count}', f'Seed{index}:',
                  'LD A,[HL+]', 'LD [DE],A', 'INC DE', 'DEC B', f'JR NZ,Seed{index}']
    return lines
