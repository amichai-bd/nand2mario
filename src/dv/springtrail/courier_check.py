"""Ordered current courier output; shared trace/completion checks remain unchanged."""
from motion_unit_check import Check as TraceCheck, run as run_trace
from courier_cases import cases, parts, expected

# Shared composer/position scratch only. Camera and all gameplay state are read-only.
SCRATCH = {0xc03c, 0xc03d, *range(0xc042, 0xc04c)}
INITIALIZED = (*range(0xc000, 0xc0f0), *range(0xc300, 0xc338))
PRESERVED = tuple(a for a in INITIALIZED if a not in SCRATCH)


class Check(TraceCheck):
    def __init__(self, short=False, part='a'):
        self.selected = cases()[:1] if short else parts()[part]
        self.short_bound = 40000
        self.full_bound = 330000
        self.memory = {}; self.active = None; self.reports = []; self.durations = []
        self.lines = 0; self.records = 0; self.last_dot = -1
        self.terminal = False; self.halted = False; self.ended = False
        self.writes = []; self.before = None

    def write(self, dot, address, data):
        assert not self.terminal, 'COURIER_AFTER_TERMINAL'
        assert not (0x8000 <= address < 0xa000 or 0xfe00 <= address < 0xfea0
                    or address in (0xff42, 0xff43, 0xff46)), 'COURIER_DISPLAY_WRITE'
        if address == 0xff40:
            assert not data and self.active is None and not self.reports, 'COURIER_LCD'
        if address == 0xc0fc:
            assert self.active is None and data == len(self.reports)+1 and data <= len(self.selected), 'COURIER_BEGIN'
            assert all(a in self.memory for a in INITIALIZED), 'COURIER_UNINITIALIZED'
            case = self.selected[data-1]
            fields = {0xc041:case['pose'], 0xc040:32*case['left'],
                      0xc03b:int(case['hidden']), 0xc0f3:int(case['project'])}
            for address0, value in ((0xc042,case['x']),(0xc044,case['y']),
                                    (0xc034,case['x']),(0xc036,case['y']),
                                    (0xc01b,case['camera'])):
                fields.update({address0:value&255, address0+1:(value>>8)&255})
            assert all(self.memory.get(a) == v for a,v in fields.items()), 'COURIER_OPERANDS'
            self.before = bytes(self.memory[a] for a in PRESERVED)
            self.active = dot; self.writes = []
        elif address == 0xc0fd:
            assert self.active is not None and data == len(self.reports)+1, 'COURIER_REPORT'
            case = self.selected[data-1]
            wants = list(enumerate(expected(case)))
            assert self.writes == wants, f'COURIER_OAM {case["name"]} actual={self.writes} expected={wants}'
            assert bytes(self.memory[a] for a in PRESERVED) == self.before, 'COURIER_PRESERVATION'
            duration = dot-self.active
            assert 0 < duration <= 16000, 'COURIER_ROUTINE_BOUND'
            self.durations.append(duration)
            self.reports.append(dict(name=case['name'], dot=dot, bytes=160))
            self.active = None
        elif address == 0xc0ff:
            assert data == 0xa5 and self.active is None and len(self.reports) == len(self.selected), 'COURIER_TERMINAL'
            self.terminal = True
        elif self.active is not None:
            if 0xc100 <= address < 0xc1a0:
                self.writes.append((address-0xc100,data))
            else:
                assert address in SCRATCH or 0xdff0 <= address < 0xdffe, 'COURIER_UNRELATED_WRITE'
        self.memory[address] = data


async def run(dut, short=False, part="a"):
    await run_trace(dut, short=short, checker=Check(short, part))
