"""Ordered public intent plus actual OAM/map/read-register observations."""
from renderer_cases import cases, maps, ADDRESSES
from scene_reference import image


class Check:
    def __init__(self, count):
        self.cases = cases()[:count]
        self.final_map, self.map_writes = maps(count)
        self.reports = []
        self.initial = []
        self.prepared = []
        self.publish = []
        self.objects = []
        self.map_read = []
        self.registers = []
        self.prep = self.begin = self.prep_dots = self.call_dots = None
        self.terminal = False

    def write(self, dot, address, data):
        assert not self.terminal, 'RENDER_AFTER_TERMINAL'
        index = len(self.reports)
        if address in ADDRESSES and (self.prep is not None or self.begin is not None):
            raise AssertionError('RENDER_GAME_STATE_WRITE')
        if address == 0xc0eb:
            assert data == index < len(self.cases) and self.prep is None and self.prep_dots is None and self.begin is None, 'RENDER_PREP_BEGIN'
            assert len(self.initial) == 576, 'RENDER_INITIAL_MAP'
            self.prep = dot
        elif address == 0xc0ec:
            assert data == index and self.prep is not None, 'RENDER_PREP_END'
            self.prep_dots = dot-self.prep
            assert 0 < self.prep_dots < 12000, 'RENDER_PREP_BUDGET'
            assert self.prepared == list(enumerate(image(self.cases[index]['game']), 0xc100)), 'RENDER_PREPARED'
            self.prep = None
        elif 0xc100 <= address < 0xc124:
            assert self.prep is not None, 'RENDER_PREP_OUTSIDE'
            self.prepared.append((address, data))
        elif address == 0xc0ee:
            assert data == index and self.begin is None and self.prep is None and self.prep_dots is not None and self.call_dots is None, 'RENDER_BEGIN'
            self.begin = dot
        elif address == 0xc0ef:
            assert data == index and self.begin is not None, 'RENDER_END'
            self.call_dots = dot-self.begin
            assert 0 < self.call_dots < 4200, 'RENDER_VBLANK_BUDGET'
            want = []
            if self.cases[index]['restart']:
                want += [(0xff43, 0), (0xff40, 0x17)]
            want += self.map_writes[index]
            if index == 17:
                want += [(0xff40, 0x1f)]
            want += list(enumerate(image(self.cases[index]['game']), 0xfe00))
            assert self.publish == want, f'RENDER_PUBLISH index={index} expected={want} actual={self.publish}'
            self.begin = None
        elif address == 0xc0e0:
            assert self.call_dots is not None, 'RENDER_READ_BEFORE_PUBLISH'
            self.objects.append(data)
        elif address in (0xc0e2, 0xc0e3):
            assert self.call_dots is not None and self.begin is None and self.prep is None, 'RENDER_REGISTER_OUTSIDE'
            self.registers.append((address, data))
        elif address == 0xc0e1:
            assert index == len(self.cases), 'RENDER_EARLY_MAP_READ'
            self.map_read.append(data)
        elif address == 0xc0fe:
            assert data == index < len(self.cases) and self.begin is None and self.prep is None and self.call_dots is not None, 'RENDER_REPORT'
            assert bytes(self.objects) == image(self.cases[index]['game']), 'RENDER_OAM_READBACK'
            assert self.registers == [(0xc0e2, 0x1f if index == 17 else 0x17), (0xc0e3, 0)], 'RENDER_REGISTER_READBACK'
            self.reports.append(dict(index=index, prep_dots=self.prep_dots, publish_dots=self.call_dots))
            self.prep_dots = self.call_dots = None
            self.prepared, self.publish, self.objects, self.registers = [], [], [], []
        elif address == 0xc0ff:
            assert data == 165 and index == len(self.cases) and self.begin is None and self.prep is None and self.prep_dots is None and self.call_dots is None, 'RENDER_TERMINAL'
            assert not any((self.prepared, self.publish, self.objects, self.registers)), 'RENDER_TERMINAL_PENDING'
            assert bytes(self.map_read) == self.final_map, 'RENDER_MAP_READBACK'
            self.terminal = True
        elif 0x8000 <= address <= 0x9fff or 0xfe00 <= address <= 0xfe9f or address in (0xff40, 0xff43):
            if self.begin is not None:
                self.publish.append((address, data))
            elif address == 0xff40 and data == 0x17 and not self.initial:
                pass
            else:
                assert self.prep is None and not self.reports and self.prep_dots is None, 'RENDER_DISPLAY_OUTSIDE'
                assert (address, data) == (0x9c00+len(self.initial), 0) and len(self.initial) < 576, 'RENDER_INITIAL_WRITE'
                self.initial.append(data)
