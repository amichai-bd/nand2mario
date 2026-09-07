"""Independent instruction recipe for the original v0.5 program only."""
import json
from pathlib import Path

FRAME_DOTS = 70224
LCD_COMMIT = 41984
FIRST_IMAGE_END = 177667
WINDOW_END = FIRST_IMAGE_END + 600 * FRAME_DOTS


def selected_lines(select, buttons):
    lines = 15
    if not select & 0x10:
        lines &= ~(buttons & 15)
    if not select & 0x20:
        lines &= ~(buttons >> 4)
    return lines & 15


class Reference:
    """Advance literal instructions, never DUT decoded fields or actual PC."""

    def __init__(self, input_events=()):
        rows = json.loads(Path(__file__).with_name('program.json').read_text())['instructions']
        self.instructions = {r['pc']: r for r in rows}
        self.reg = dict.fromkeys('afbcdehl', 0)
        self.sp = 0xfffe
        self.pc = 0x100
        self.dot = 4  # The direct-profile frontend precedes the first NOP.
        self.ie = self.iflags = self.buttons = 0
        self.select = 0x30
        self.halted = False
        self.seq = 0
        self.lcd_commit = None
        self.next_vblank = None
        self.inputs = iter(input_events)
        self.next_input = next(self.inputs, None)
        self.writes = []

    def advance(self, dot):
        # Input application is off-tick. Its effects follow a retirement on
        # that same completed dot; the frozen windows place it during HALT.
        while True:
            input_dot = self.next_input[0] if self.next_input else float('inf')
            vb_dot = self.next_vblank if self.next_vblank is not None else float('inf')
            if input_dot < vb_dot and input_dot < dot:
                old = selected_lines(self.select, self.buttons)
                self.buttons = self.next_input[1]
                if old & ~selected_lines(self.select, self.buttons):
                    self.iflags |= 0x10
                self.next_input = next(self.inputs, None)
            elif vb_dot <= dot:
                self.iflags |= 1
                self.next_vblank += FRAME_DOTS
            else:
                break

    def pair(self, name):
        return (self.reg[name[0]] << 8) | self.reg[name[1]]

    def set_pair(self, name, value):
        self.reg[name[0]] = value >> 8
        self.reg[name[1]] = value & 255

    def write(self, dot, address, value):
        self.writes.append((dot, address, value))
        if address == 0xffff:
            self.ie = value
        elif address == 0xff0f:
            self.iflags = value & 31
        elif address == 0xff00:
            old = selected_lines(self.select, self.buttons)
            self.select = value & 0x30
            if old & ~selected_lines(self.select, self.buttons):
                self.iflags |= 0x10
        elif address == 0xff40 and value & 0x80:
            if self.lcd_commit is not None:
                raise AssertionError('original program enables LCD once')
            self.lcd_commit = dot
            self.next_vblank = dot + 65662

    def step(self, end_dot):
        if self.halted:
            # IE1/IME0: JOYP cannot wake; VBlank reaches IF before the next T3.
            wake = ((self.next_vblank + 3) // 4) * 4
            if wake > end_dot:
                return None
            self.advance(wake)
            self.dot = wake
            self.halted = False
        ins = self.instructions[self.pc]
        op = ins['operation']
        code = bytes.fromhex(ins['bytes'])
        cycles = ins['mcycles']
        taken = not self.reg['f'] & 0x80
        if op == 'jr_nz' and not taken:
            cycles = 2
        finish = self.dot + 4 * cycles
        if finish > end_dot:
            return None
        before = self.pc
        self.pc += len(code)
        access = finish - 4
        self.advance(access)
        a = self.reg['a']
        if op.startswith('a_') and op[2:] in ('b', 'e'):
            self.reg['a'] = self.reg[op[2:]]
        elif op.startswith('a_'):
            self.reg['a'] = int(op[2:], 16)
        elif op in ('b_a', 'c_a', 'e_a'):
            self.reg[op[0]] = a
        elif op.startswith('b_'):
            self.reg['b'] = int(op[2:], 16)
        elif op.startswith('hl_') or op.startswith('bc_'):
            self.set_pair(op[:2], int(op[3:], 16))
        elif op == 'sp_dffe':
            self.sp = 0xdffe
        elif op == 'xor_a':
            self.reg['a'], self.reg['f'] = 0, 0x80
        elif op == 'dec_bc':
            self.set_pair('bc', (self.pair('bc') - 1) & 65535)
        elif op == 'dec_b':
            old = self.reg['b']
            self.reg['b'] = (old - 1) & 255
            self.reg['f'] = (self.reg['f'] & 0x10) | 0x40 | (0x20 if old & 15 == 0 else 0) | (0x80 if old == 1 else 0)
        elif op in ('or_b', 'or_c'):
            self.reg['a'] |= self.reg[op[-1]]
            self.reg['f'] = 0x80 if self.reg['a'] == 0 else 0
        elif op.startswith('and_'):
            self.reg['a'] &= int(op[4:], 16)
            self.reg['f'] = 0x20 | (0x80 if self.reg['a'] == 0 else 0)
        elif op == 'cpl':
            self.reg['a'] ^= 255
            self.reg['f'] |= 0x60
        elif op == 'swap_a':
            self.reg['a'] = ((a & 15) << 4) | (a >> 4)
            self.reg['f'] = 0x80 if a == 0 else 0
        elif op == 'rrca':
            self.reg['a'] = (a >> 1) | ((a & 1) << 7)
            self.reg['f'] = (a & 1) << 4
        elif op == 'write_hli':
            self.write(access, self.pair('hl'), a)
            self.set_pair('hl', (self.pair('hl') + 1) & 65535)
        elif op.endswith('_write'):
            addresses = {'lcdc': 0xff40, 'if': 0xff0f, 'ie': 0xffff, 'scy': 0xff42,
                         'scx': 0xff43, 'marker': 0x9800, 'bgp': 0xff47, 'joyp': 0xff00}
            self.write(access, addresses[op[:-6]], a)
        elif op == 'joyp_read':
            self.reg['a'] = 0xc0 | self.select | selected_lines(self.select, self.buttons)
        elif op in ('jr', 'jr_nz'):
            if op == 'jr' or taken:
                self.pc += code[1] - 256 if code[1] & 128 else code[1]
        elif op == 'jp_0200':
            self.pc = 0x200
        elif op == 'halt':
            if self.ie & self.iflags:
                raise AssertionError('original HALT must have no enabled pending request')
            self.halted = True
        elif op not in ('nop', 'di'):
            raise AssertionError(op)
        self.advance(finish)
        self.dot = finish
        result = dict(version=1, kind=0, epoch=2, seq=self.seq, dot=finish,
                      pc_before=before, pc_after=self.pc, opcode=int.from_bytes(code, 'little'),
                      opcode_length=len(code), **self.reg, sp=self.sp, ime=0, ime_delay=0,
                      halted=int(self.halted), stopped=0, halt_bug=0, ie=self.ie,
                      iflags=self.iflags, buttons=self.buttons)
        self.seq += 1
        return result

    def records(self, end_dot):
        while (record := self.step(end_dot)) is not None:
            yield record

INPUT_MASKS = (1, 0, 2, 0, 4, 0, 8, 0, 16, 0, 32, 0, 64, 0, 128, 0, 17, 0)


def input_window(transition, *, short=False):
    if not 1 <= transition <= (2 if short else 18):
        raise ValueError('input transition outside original schedule')
    first = FIRST_IMAGE_END + (1 if short else 20) * transition * FRAME_DOTS + 20000
    return first, first + 2000


def frame_mask(frame, *, short=False):
    mask = 0
    for j, value in enumerate(INPUT_MASKS[:2] if short else INPUT_MASKS, 1):
        if frame >= (1 if short else 20) * j + 3:
            mask = value
    return mask


def pixel_shade(frame, x, y, *, short=False):
    if frame == 0:
        return 0
    marker = x < 8 and y < 8
    cell = x < 64 and 64 <= y < 72 and bool(frame_mask(frame, short=short) & (1 << (x // 8)))
    return int(marker or cell)


def unpack_retirement(hex_value):
    from n2m.generated_interfaces import RECORDS
    value = int(hex_value, 16)
    result = {}
    for field in RECORDS['retirement']:
        bits = field['bits']
        result[field['name']] = value & ((1 << bits) - 1)
        value >>= bits
    if value:
        raise ValueError('retirement exceeds ABI width')
    return result


def compare_record(expected, actual):
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError(f"V05_RETIRE seq={expected['seq']} field={key} expected={value} actual={actual.get(key)}")
    if actual.keys() != expected.keys():
        raise ValueError('V05_RETIRE_FIELDS')
