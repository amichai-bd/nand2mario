"""Source-derived Springtrail startup anchor: the dot of the first LCDC 0x91 write.

`derive(image)` executes the built image with an independent SM83 timing
model, from the direct profile's reset PC 0x0100 until the program writes
0x91 to LCDC, and returns that write's dot with every term of the count.
The rules are the instruction manual's M-cycle table as MAS_cpu freezes it:
startup is one initial opcode fetch, each instruction then costs its listed
M-cycles with the final fetch overlapping the next instruction, and a write
commits at T4 of its M-cycle, so its dot is four times the M-cycles completed
through that cycle. IME stays clear (DI) until after the write, so the path
is straight-line code with data-dependent loops only.

The model is the derivation, not the DUT: it knows no RTL and reads nothing
from a run. `motion_game_reference.LCD` freezes the result the current image
gives; `python-mgs` proves the RTL commits at that exact dot, and
`test_startup_anchor` proves the image the repository builds still derives
it, so a moved anchor fails at level 0 before any board session.
"""
import bisect
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'src/sw/springtrail'
LCDC, LCDC_ON = 0xff40, 0x91
RESET_PC = 0x0100  # cfg/interfaces.json PC: first opcode after reset/resume
LIMIT = 1_000_000  # M-cycles; the anchor is far below and a runaway must stop


def build():
    """The packaged current image and its symbols, built in process."""
    prior = sys.path[:]
    try:
        sys.path.insert(0, str(ROOT / 'tools'))
        from sw.assembler import assemble
        from sw.assets import encode_shades, load_shades
        from sw.linker import link
        from sw.package import package
    finally:
        sys.path[:] = prior
    target = json.loads((ROOT / 'src/sw/targets.json').read_text())['targets']['springtrail']
    assets = {name: encode_shades(load_shades(SOURCE / spec['source'], spec['source']), spec['source'])
              for name, spec in target['assets'].items()}
    obj = assemble(SOURCE / 'main.asm', SOURCE, ROOT / 'src/sw/generated/interfaces.inc', assets)
    linked = link([('main.asm', obj)], json.loads((SOURCE / target.get('layout', 'layout.json')).read_text()),
                  target['entry'])
    image = package(linked, target['title'], target['version'], target['profile'])
    return image, symbol_table(linked['symbols'])


def symbol_table(symbols):
    """{address: name} for every ROM symbol; the lowest name wins a shared address."""
    table = {}
    for row in sorted(symbols['symbols'], key=lambda r: (r['value'], r['symbol'])):
        table.setdefault(row['value'], row['symbol'])
    return table


# M-cycles per unprefixed opcode; conditional forms list (taken, not taken).
def _cycles():
    t = [0] * 256
    for op in range(0x40, 0x80):
        t[op] = 2 if (op & 7) == 6 or (op >> 3 & 7) == 6 else 1
    for op in range(0x80, 0xc0):
        t[op] = 2 if (op & 7) == 6 else 1
    fixed = {0x00: 1, 0x01: 3, 0x02: 2, 0x03: 2, 0x04: 1, 0x05: 1, 0x06: 2, 0x07: 1, 0x08: 5, 0x09: 2,
             0x0a: 2, 0x0b: 2, 0x0c: 1, 0x0d: 1, 0x0e: 2, 0x0f: 1, 0x10: 1, 0x11: 3, 0x12: 2, 0x13: 2,
             0x14: 1, 0x15: 1, 0x16: 2, 0x17: 1, 0x18: 3, 0x19: 2, 0x1a: 2, 0x1b: 2, 0x1c: 1, 0x1d: 1,
             0x1e: 2, 0x1f: 1, 0x21: 3, 0x22: 2, 0x23: 2, 0x24: 1, 0x25: 1, 0x26: 2, 0x27: 1, 0x29: 2,
             0x2a: 2, 0x2b: 2, 0x2c: 1, 0x2d: 1, 0x2e: 2, 0x2f: 1, 0x31: 3, 0x32: 2, 0x33: 2, 0x34: 3,
             0x35: 3, 0x36: 3, 0x37: 1, 0x39: 2, 0x3a: 2, 0x3b: 2, 0x3c: 1, 0x3d: 1, 0x3e: 2, 0x3f: 1,
             0xc1: 3, 0xc3: 4, 0xc5: 4, 0xc6: 2, 0xc7: 4, 0xc9: 4, 0xcd: 6, 0xce: 2, 0xcf: 4,
             0xd1: 3, 0xd5: 4, 0xd6: 2, 0xd7: 4, 0xd9: 4, 0xde: 2, 0xdf: 4,
             0xe0: 3, 0xe1: 3, 0xe2: 2, 0xe5: 4, 0xe6: 2, 0xe7: 4, 0xe8: 4, 0xe9: 1, 0xea: 4, 0xee: 2, 0xef: 4,
             0xf0: 3, 0xf1: 3, 0xf2: 2, 0xf3: 1, 0xf5: 4, 0xf6: 2, 0xf7: 4, 0xf8: 3, 0xf9: 2, 0xfa: 4, 0xfb: 1,
             0xfe: 2, 0xff: 4}
    for op, cost in fixed.items():
        t[op] = cost
    conditional = {0x20: (3, 2), 0x28: (3, 2), 0x30: (3, 2), 0x38: (3, 2),
                   0xc0: (5, 2), 0xc8: (5, 2), 0xd0: (5, 2), 0xd8: (5, 2),
                   0xc2: (4, 3), 0xca: (4, 3), 0xd2: (4, 3), 0xda: (4, 3),
                   0xc4: (6, 3), 0xcc: (6, 3), 0xd4: (6, 3), 0xdc: (6, 3)}
    return t, conditional


CYCLES, CONDITIONAL = _cycles()
ILLEGAL = {0xd3, 0xdb, 0xdd, 0xe3, 0xe4, 0xeb, 0xec, 0xed, 0xf4, 0xfc, 0xfd}


class Model:
    """SM83 instruction timing over a flat 64 KiB memory; ROM is read-only."""

    def __init__(self, image, lcdc_on=LCDC_ON):
        assert len(image) == 32768, 'ANCHOR_IMAGE_SIZE'
        self.lcdc_on = lcdc_on
        self.memory = bytearray(65536)
        self.memory[:32768] = image
        self.pc, self.sp = RESET_PC, 0xfffe
        self.a = self.f = self.b = self.c = self.d = self.e = self.h = self.l = 0
        self.mcycles = 1  # the initial opcode fetch; MAS_cpu "Time, bus and retirement"
        self.depth = 0
        self.lcd = None

    # Memory. Stores below 0x8000 have no effect (no mapper). Reads of I/O
    # return the stored byte, zero unless written: LY is 0 while the LCD is off.
    def read(self, address):
        return self.memory[address & 0xffff]

    def write(self, address, value, cycle):
        address &= 0xffff
        if address >= 0x8000:
            self.memory[address] = value & 255
        if address == LCDC and value == self.lcdc_on and self.lcd is None:
            self.lcd = 4 * (self.mcycles + cycle)

    def fetch(self):
        value = self.read(self.pc)
        self.pc = (self.pc + 1) & 0xffff
        return value

    def fetch16(self):
        low = self.fetch()
        return low | (self.fetch() << 8)

    # Register file helpers.
    def reg(self, index):
        if index == 6:
            return self.read(self.hl)
        return (self.b, self.c, self.d, self.e, self.h, self.l, None, self.a)[index]

    def set_reg(self, index, value, cycle=1):
        value &= 255
        if index == 6:
            self.write(self.hl, value, cycle)
        else:
            setattr(self, 'bcdehl_a'[index], value)

    @property
    def hl(self):
        return (self.h << 8) | self.l

    @hl.setter
    def hl(self, value):
        self.h, self.l = (value >> 8) & 255, value & 255

    def pair(self, index):
        return ((self.b << 8) | self.c, (self.d << 8) | self.e, self.hl, self.sp)[index]

    def set_pair(self, index, value):
        value &= 0xffff
        if index == 0:
            self.b, self.c = value >> 8, value & 255
        elif index == 1:
            self.d, self.e = value >> 8, value & 255
        elif index == 2:
            self.hl = value
        else:
            self.sp = value

    def flags(self, z=None, n=None, h=None, c=None):
        for bit, value in ((7, z), (6, n), (5, h), (4, c)):
            if value is not None:
                self.f = (self.f | (1 << bit)) if value else (self.f & ~(1 << bit) & 255)

    def condition(self, index):
        z, c = self.f >> 7 & 1, self.f >> 4 & 1
        return ((not z), z, (not c), c)[index]

    def push(self, value, cycle):
        self.sp = (self.sp - 1) & 0xffff
        self.write(self.sp, value >> 8, cycle)
        self.sp = (self.sp - 1) & 0xffff
        self.write(self.sp, value & 255, cycle + 1)

    def pop(self):
        low = self.read(self.sp)
        self.sp = (self.sp + 1) & 0xffff
        high = self.read(self.sp)
        self.sp = (self.sp + 1) & 0xffff
        return low | (high << 8)

    def alu(self, op, value):
        a, c = self.a, self.f >> 4 & 1
        if op == 0:  # ADD
            r = a + value
            self.flags(z=(r & 255) == 0, n=0, h=(a & 15) + (value & 15) > 15, c=r > 255)
        elif op == 1:  # ADC
            r = a + value + c
            self.flags(z=(r & 255) == 0, n=0, h=(a & 15) + (value & 15) + c > 15, c=r > 255)
        elif op == 2:  # SUB
            r = a - value
            self.flags(z=(r & 255) == 0, n=1, h=(a & 15) < (value & 15), c=r < 0)
        elif op == 3:  # SBC
            r = a - value - c
            self.flags(z=(r & 255) == 0, n=1, h=(a & 15) < (value & 15) + c, c=r < 0)
        elif op == 4:  # AND
            r = a & value
            self.flags(z=r == 0, n=0, h=1, c=0)
        elif op == 5:  # XOR
            r = a ^ value
            self.flags(z=r == 0, n=0, h=0, c=0)
        elif op == 6:  # OR
            r = a | value
            self.flags(z=r == 0, n=0, h=0, c=0)
        else:  # CP
            r = a - value
            self.flags(z=(r & 255) == 0, n=1, h=(a & 15) < (value & 15), c=r < 0)
            return
        self.a = r & 255

    def rotate(self, op, value):
        """CB rotate/shift group 0..7 and the four accumulator forms."""
        c = self.f >> 4 & 1
        if op == 0:
            r, carry = ((value << 1) | (value >> 7)) & 255, value >> 7
        elif op == 1:
            r, carry = ((value >> 1) | (value << 7)) & 255, value & 1
        elif op == 2:
            r, carry = ((value << 1) | c) & 255, value >> 7
        elif op == 3:
            r, carry = ((value >> 1) | (c << 7)) & 255, value & 1
        elif op == 4:
            r, carry = (value << 1) & 255, value >> 7
        elif op == 5:
            r, carry = (value >> 1) | (value & 128), value & 1
        elif op == 6:
            r, carry = ((value << 4) | (value >> 4)) & 255, 0
        else:
            r, carry = value >> 1, value & 1
        self.flags(z=r == 0, n=0, h=0, c=carry)
        return r

    def step(self):
        """Execute one instruction; return its M-cycle cost."""
        op = self.fetch()
        assert op not in ILLEGAL, f'ANCHOR_ILLEGAL_OPCODE {op:02x}'
        assert op not in (0x76, 0x10), f'ANCHOR_HALT_BEFORE_LCD {op:02x}'
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        cost = CYCLES[op]
        if x == 1:  # LD r,r'
            self.set_reg(y, self.reg(z))
        elif x == 2:  # ALU A,r
            self.alu(y, self.reg(z))
        elif x == 0:
            if z == 0:
                if op == 0x00:
                    pass
                elif op == 0x08:
                    address = self.fetch16()
                    self.write(address, self.sp & 255, 3)
                    self.write(address + 1, self.sp >> 8, 4)
                elif op == 0x18:
                    offset = self.signed(self.fetch())
                    self.pc = (self.pc + offset) & 0xffff
                else:  # JR cc
                    offset = self.signed(self.fetch())
                    taken = self.condition(y - 4)
                    cost = CONDITIONAL[op][0 if taken else 1]
                    if taken:
                        self.pc = (self.pc + offset) & 0xffff
            elif z == 1:
                if y & 1:  # ADD HL,rr
                    hl, rr = self.hl, self.pair(y >> 1)
                    r = hl + rr
                    self.flags(n=0, h=(hl & 0xfff) + (rr & 0xfff) > 0xfff, c=r > 0xffff)
                    self.hl = r & 0xffff
                else:
                    self.set_pair(y >> 1, self.fetch16())
            elif z == 2:
                if y == 0:
                    self.write(self.pair(0), self.a, 1)
                elif y == 1:
                    self.a = self.read(self.pair(0))
                elif y == 2:
                    self.write(self.pair(1), self.a, 1)
                elif y == 3:
                    self.a = self.read(self.pair(1))
                elif y == 4:
                    self.write(self.hl, self.a, 1)
                    self.hl = (self.hl + 1) & 0xffff
                elif y == 5:
                    self.a = self.read(self.hl)
                    self.hl = (self.hl + 1) & 0xffff
                elif y == 6:
                    self.write(self.hl, self.a, 1)
                    self.hl = (self.hl - 1) & 0xffff
                else:
                    self.a = self.read(self.hl)
                    self.hl = (self.hl - 1) & 0xffff
            elif z == 3:
                self.set_pair(y >> 1, self.pair(y >> 1) + (-1 if y & 1 else 1))
            elif z == 4:  # INC r
                v = (self.reg(y) + 1) & 255
                self.flags(z=v == 0, n=0, h=(v & 15) == 0)
                self.set_reg(y, v, 2)
            elif z == 5:  # DEC r
                v = (self.reg(y) - 1) & 255
                self.flags(z=v == 0, n=1, h=(v & 15) == 15)
                self.set_reg(y, v, 2)
            elif z == 6:  # LD r,d8
                self.set_reg(y, self.fetch(), 2)
            else:
                if y < 4:
                    self.a = self.rotate(y, self.a)
                    self.flags(z=0)
                elif y == 4:  # DAA
                    a, n, h, c = self.a, self.f >> 6 & 1, self.f >> 5 & 1, self.f >> 4 & 1
                    if n:
                        if c:
                            a -= 0x60
                        if h:
                            a -= 6
                    else:
                        if c or a > 0x99:
                            a += 0x60
                            c = 1
                        if h or (a & 15) > 9:
                            a += 6
                    self.a = a & 255
                    self.flags(z=self.a == 0, h=0, c=c)
                elif y == 5:
                    self.a ^= 255
                    self.flags(n=1, h=1)
                elif y == 6:
                    self.flags(n=0, h=0, c=1)
                else:
                    self.flags(n=0, h=0, c=not (self.f >> 4 & 1))
        else:  # x == 3
            if z == 0:
                if y < 4:  # RET cc
                    taken = self.condition(y)
                    cost = CONDITIONAL[op][0 if taken else 1]
                    if taken:
                        self.pc = self.pop()
                        self.depth -= 1
                elif y == 4:
                    self.write(0xff00 | self.fetch(), self.a, 2)
                elif y == 5:  # ADD SP,r8
                    offset = self.signed(self.fetch())
                    sp = self.sp
                    self.flags(z=0, n=0, h=(sp & 15) + (offset & 15) > 15, c=(sp & 255) + (offset & 255) > 255)
                    self.sp = (sp + offset) & 0xffff
                elif y == 6:
                    self.a = self.read(0xff00 | self.fetch())
                else:  # LD HL,SP+r8
                    offset = self.signed(self.fetch())
                    sp = self.sp
                    self.flags(z=0, n=0, h=(sp & 15) + (offset & 15) > 15, c=(sp & 255) + (offset & 255) > 255)
                    self.hl = (sp + offset) & 0xffff
            elif z == 1:
                if y & 1:
                    if y == 1:  # RET
                        self.pc = self.pop()
                        self.depth -= 1
                    elif y == 3:  # RETI
                        self.pc = self.pop()
                        self.depth -= 1
                    elif y == 5:  # JP HL
                        self.pc = self.hl
                    else:  # LD SP,HL
                        self.sp = self.hl
                else:  # POP
                    value = self.pop()
                    if y >> 1 == 3:
                        self.a, self.f = value >> 8, value & 0xf0
                    else:
                        self.set_pair(y >> 1, value)
            elif z == 2:
                if y < 4:  # JP cc
                    target = self.fetch16()
                    taken = self.condition(y)
                    cost = CONDITIONAL[op][0 if taken else 1]
                    if taken:
                        self.pc = target
                elif y == 4:
                    self.write(0xff00 | self.c, self.a, 1)
                elif y == 5:
                    self.write(self.fetch16(), self.a, 3)
                elif y == 6:
                    self.a = self.read(0xff00 | self.c)
                else:
                    self.a = self.read(self.fetch16())
            elif z == 3:
                if y == 0:
                    self.pc = self.fetch16()
                elif y == 1:
                    cost = self.prefixed()
                elif y == 6:
                    pass  # DI
                elif y == 7:
                    pass  # EI: no interrupt is enabled before the anchor
                else:
                    raise AssertionError(f'ANCHOR_ILLEGAL_OPCODE {op:02x}')
            elif z == 4:  # CALL cc
                target = self.fetch16()
                taken = self.condition(y)
                cost = CONDITIONAL[op][0 if taken else 1]
                if taken:
                    self.push(self.pc, 4)
                    self.pc = target
                    self.depth += 1
            elif z == 5:
                if y & 1:  # CALL
                    target = self.fetch16()
                    self.push(self.pc, 4)
                    self.pc = target
                    self.depth += 1
                else:  # PUSH
                    value = ((self.a << 8) | self.f) if y >> 1 == 3 else self.pair(y >> 1)
                    self.push(value, 2)
            elif z == 6:
                self.alu(y, self.fetch())
            else:  # RST
                self.push(self.pc, 2)
                self.pc = y * 8
                self.depth += 1
        return cost

    def prefixed(self):
        op = self.fetch()
        x, y, z = op >> 6, op >> 3 & 7, op & 7
        value = self.reg(z)
        if x == 0:
            self.set_reg(z, self.rotate(y, value), 3)
        elif x == 1:
            self.flags(z=not (value >> y & 1), n=0, h=1)
        elif x == 2:
            self.set_reg(z, value & ~(1 << y), 3)
        else:
            self.set_reg(z, value | (1 << y), 3)
        if z != 6:
            return 2
        return 3 if x == 1 else 4

    @staticmethod
    def signed(value):
        return value - 256 if value & 128 else value


def derive(image, symbols=None, limit=LIMIT, lcdc_on=LCDC_ON):
    """Run the image to its LCDC 0x91 write; {lcd, mcycles, terms, instructions}.

    Terms attribute dots to the routine executing them: the nearest symbol at
    or below the current PC while the call depth is zero (the header stub and
    `Start`'s inline loops), or the callee's symbol while inside a `CALL` from
    that level. Their values sum to `lcd` exactly.
    """
    symbols = symbols or {}
    addresses = sorted(symbols)
    model = Model(image, lcdc_on)
    terms, order = {}, []
    instructions = 0

    def label(pc):
        if pc < 0x150:
            return 'header'  # NOP; JP Start, written by tools/sw/package.py
        if not addresses:
            return f'{pc:04x}'
        index = bisect.bisect_right(addresses, pc) - 1
        return symbols[addresses[index]] if index >= 0 else f'{pc:04x}'

    current = 'reset fetch'
    terms[current] = 4
    order.append(current)
    routine = None
    while model.lcd is None:
        assert model.mcycles < limit, 'ANCHOR_RUNAWAY'
        pc = model.pc
        depth = model.depth
        cost = model.step()
        instructions += 1
        if depth == 0:
            name = label(pc)
            if model.depth == 1:
                routine = label(model.pc)  # the CALL itself is charged to its callee
                name = routine
        else:
            name = routine
        if name not in terms:
            terms[name] = 0
            order.append(name)
        terms[name] += 4 * cost
        model.mcycles += cost
    # The LCDC write commits inside its instruction; its final fetch is not counted.
    terms[name] -= 4 * model.mcycles - model.lcd
    assert sum(terms.values()) == model.lcd, 'ANCHOR_TERMS'
    return dict(lcd=model.lcd, mcycles=model.lcd // 4, instructions=instructions,
                terms=[(name, terms[name]) for name in order])


def main():
    image, symbols = build()
    result = derive(image, symbols)
    print('image', hashlib.sha256(image).hexdigest())
    for name, dots in result['terms']:
        print(f'{dots:8d}  {name}')
    print(f'{result["lcd"]:8d}  LCD ({result["mcycles"]} M-cycles, {result["instructions"]} instructions)')


if __name__ == '__main__':
    main()
