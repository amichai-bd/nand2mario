"""Fixed input/frame schedule and public writes for the approved renderer."""
import zlib
from interactions_reference import Game, update
from interaction_cases import ADDRESSES, state_bytes
from scene_reference import image as oam
from flow_frames import image
from movement_reference import world_tile

LCD = 76964
PERIOD = 70224
CRC = (0xb15161f6, 0x6fc2f93a, 0xfa8827ff)
START_WINDOW = (LCD+60000, LCD+62000)


class Check:
    def __init__(self, short=False):
        self.short = short
        self.count = 2 if short else 3
        self.end = LCD+65664+(self.count-1)*PERIOD+(3000 if short else 3500)
        self.states = [Game()]
        for _ in range(1, self.count):
            self.states.append(update(self.states[-1], 0 if short else 129))
        self.expected = [bytes(23040)] + [image(g) for g in self.states[:-1]]
        assert tuple(zlib.crc32(f) for f in self.expected)==CRC[:self.count], "FLOW_GAME_LITERAL_CRC"
        self.frames = [bytearray() for _ in self.expected]
        self.pixels = self.lines = self.records = self.last_record = self.last_pixel = 0
        self.inputs = []
        self.memory = {}
        self.prepared = []
        self.partial = []
        self.publish = [[] for _ in self.expected]
        self.lcd = []
        self.ended = False

    def pixel(self, value):
        frame, index = divmod(self.pixels, 23040)
        assert frame < self.count, 'FLOW_GAME_EXTRA_PIXEL'
        y, x = divmod(index, 160)
        dot = value >> 53
        want = (2<<21)|(x<<13)|(y<<5)|(self.expected[frame][index]<<3)|(int(index==0)<<2)|int(frame!=0)
        assert value & ((1<<53)-1) == want, f'FLOW_GAME_PIXEL frame={frame} index={index} expected={want:x} actual={value&((1<<53)-1):x} dot={dot}'
        line = LCD+frame*PERIOD+y*456
        assert line <= dot < line+456 and dot > self.last_pixel, 'FLOW_GAME_PIXEL_TIME'
        self.last_pixel = dot
        self.pixels += 1
        self.frames[frame].append((value>>3)&3)

    def line(self, text):
        assert not self.ended, 'FLOW_GAME_AFTER_END'
        kind, raw = text.rstrip('\n').split(' ')
        if kind == 'END':
            assert int(raw) == self.lines, 'FLOW_GAME_END_COUNT'
            self.ended = True
            return
        widths = {'P':30, 'W':22, 'I':26, 'R':96}
        assert kind in widths and len(raw)==widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()), 'FLOW_GAME_TRACE'
        self.lines += 1
        value = int(raw,16)
        if kind == 'P':
            self.pixel(value)
        elif kind == 'I':
            epoch, dot, buttons = value>>72, (value>>8)&((1<<64)-1), value&255
            assert not self.short and not self.inputs and epoch==2 and START_WINDOW[0]<=dot<=START_WINDOW[1] and buttons==129, 'FLOW_GAME_INPUT'
            self.inputs.append((dot,buttons))
        elif kind == 'R':
            from test_integration import decode_record
            row = decode_record(value)
            assert row['seq']==self.records and row['epoch']==2 and row['dot']>self.last_record, 'FLOW_GAME_RETIRE'
            self.records += 1
            self.last_record = row['dot']
        else:
            dot, address, data = value>>24, (value>>8)&65535, value&255
            self.memory[address] = data
            if address == 0xff40:
                self.lcd.append((dot,data))
            if 0xc100 <= address < 0xc124:
                index = len(self.prepared)
                assert index < self.count and address==0xc100+len(self.partial), 'FLOW_GAME_SCENE_ORDER'
                if index == 0:
                    assert dot < LCD, 'FLOW_GAME_INITIAL_PREP'
                else:
                    assert LCD+index*PERIOD <= dot < LCD+index*PERIOD+20000, 'FLOW_GAME_VISIBLE_PREP'
                self.partial.append(data)
                if len(self.partial)==36:
                    game = self.states[index]
                    assert bytes(self.partial)==oam(game), 'FLOW_GAME_SCENE'
                    assert bytes(self.memory[a] for a in ADDRESSES)==state_bytes(game, 0 if self.short or index==0 else 129), 'FLOW_GAME_STATE'
                    self.prepared.append(dot)
                    self.partial = []
            if dot>LCD and (0x8000<=address<0xa000 or 0xfe00<=address<0xfea0 or address in (0xff40,0xff43)):
                frame, position = divmod(dot-LCD, PERIOD)
                assert frame < self.count and 65664<=position<PERIOD, 'FLOW_GAME_VBLANK_WRITE'
                self.publish[frame].append((address,data))

    def finish(self, pause):
        assert self.ended and not self.partial and len(self.prepared)==self.count, 'FLOW_GAME_PREP_MISSING'
        assert self.pixels==self.count*23040 and len(self.inputs)==(0 if self.short else 1), 'FLOW_GAME_MISSING'
        assert self.lcd[:2]==[(52,0),(LCD,151)], self.lcd
        assert len(self.lcd)==(2 if self.short else 3), self.lcd
        for frame in range(self.count):
            want = []
            if not self.short and frame>0:
                if frame==1:
                    want += [(a,0) for a in list(range(0x98a4,0x98af))+list(range(0x98e4,0x98ef))]
                    want += [(0xff43,0),(0xff40,151)]
                for column in (2*(frame-1),2*(frame-1)+1):
                    want += [(0x9c00+row*32+column,world_tile(column,row)) for row in range(18)]
            want += list(enumerate(oam(self.states[frame]),0xfe00))
            assert self.publish[frame]==want, f'FLOW_GAME_PUBLICATION frame={frame} expected={want} actual={self.publish[frame]}'
        assert self.end<=pause<=self.end+1000 and self.records>5000, 'FLOW_GAME_FINAL_PAUSE'
        return dict(pixels=self.pixels,records=self.records,inputs=self.inputs,prepared=self.prepared,pause_dot=pause,crc32=[f'{zlib.crc32(f):08x}' for f in self.frames])
