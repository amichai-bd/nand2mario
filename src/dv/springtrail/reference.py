"""Literal artwork and fixed schedule, independent of assembled ROM and DUT."""
import zlib

LCD = 43512
START_WINDOW = (173512, 175512)
END = 249420
FRAME_CRC = (0, 0x5324bc1f, 0x33421002)
GLYPHS = {
    'S': (14,16,16,14,1,1,30), 'P': (30,17,17,30,16,16,16),
    'R': (30,17,17,30,20,18,17), 'I': (31,4,4,4,4,4,31),
    'N': (17,25,25,21,19,19,17), 'G': (14,17,16,23,17,17,14),
    'T': (31,4,4,4,4,4,4), 'A': (14,17,17,31,17,17,17),
    'L': (16,16,16,16,16,16,31), 'E': (31,16,16,30,16,16,31)}
ART = {
    'ground': ('11111111','22222222','20222022','22222222','22220222','22022222','22222202','22222222'),
    'head': ('00033000','00333300','00311300','00333300','00033000','00333300','03333330','03033030'),
    'feet': ('03033030','00033000','00033000','00333300','00300300','00300300','03300330','00000000'),
    'seed': ('00000000','00030000','00323000','03212300','00323000','00030000','00000000','00000000'),
    'zero': ('00000000','00333000','03003300','03030300','03300300','00333000','00000000','00000000')}


def shade(frame, x, y):
    if frame == 0:
        return 0
    column, row = x//8, y//8
    px, py = x%8, y%8
    if frame == 1 and row in (5,7) and 4 <= column < 15:
        letter = ('SPRINGTRAIL' if row == 5 else 'PRESS START')[column-4]
        return 3 if letter != ' ' and py < 7 and 1 <= px <= 5 and GLYPHS[letter][py] & (1 << (5-px)) else 0
    name = ('ground' if row in (16,17) or (row == 12 and 10 <= column <= 14)
            else 'head' if (column,row)==(3,14) else 'feet' if (column,row)==(3,15)
            else 'seed' if (column,row)==(12,11) else 'zero' if (column,row)==(1,0) else None)
    return int(ART[name][py][px]) if name else 0


def image(frame):
    return bytes(shade(frame,x,y) for y in range(144) for x in range(160))


class Check:
    def __init__(self):
        self.pixels=0
        self.frames=[bytearray(),bytearray(),bytearray()]
        self.inputs=[]
        self.states=[]
        self.lcd=[]
        self.clears=[]
        self.records=0
        self.last_record_dot=0
        self.lines=0
        self.ended=False

    def pixel(self, value):
        frame,index=divmod(self.pixels,23040)
        assert frame < 3, 'SPRINGTRAIL_EXTRA_FRAME'
        y,x=divmod(index,160)
        dot=LCD+(93 if y==0 else 92+y*456)+x if frame==0 else LCD+70316+(frame-1)*70224+y*456+x
        expected=(dot<<53)|(2<<21)|(x<<13)|(y<<5)|(shade(frame,x,y)<<3)|(int(index==0)<<2)|int(frame!=0)
        assert value==expected, f'SPRINGTRAIL_PIXEL frame={frame} index={index} expected={expected:030x} actual={value:030x}'
        self.frames[frame].append((value>>3)&3)
        self.pixels+=1

    def line(self, line):
        assert not self.ended, 'SPRINGTRAIL_AFTER_END'
        kind,raw=line.rstrip('\n').split(' ')
        if kind=='END':
            assert int(raw)==self.lines, 'SPRINGTRAIL_TRACE_COUNT'
            self.ended=True
            return
        widths={'P':30,'W':22,'I':26,'R':96}
        assert kind in widths and len(raw)==widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()), 'SPRINGTRAIL_TRACE_UNKNOWN'
        value=int(raw,16)
        self.lines+=1
        if kind=='P':self.pixel(value)
        elif kind=='I':
            epoch=value>>72;dot=(value>>8)&((1<<64)-1);buttons=value&255
            assert not self.inputs and epoch==2 and START_WINDOW[0]<=dot<=START_WINDOW[1] and buttons==128, 'SPRINGTRAIL_START'
            self.inputs.append((dot,buttons))
        elif kind=='W':
            dot=value>>24;address=(value>>8)&65535;data=value&255
            if address==0xc000:self.states.append((dot,data))
            if address==0xff40:self.lcd.append((dot,data))
            if dot>LCD and 0x8000<=address<0xa000:
                assert LCD+135888<=dot<LCD+140448 and data==0, 'SPRINGTRAIL_VBLANK_WRITE'
                self.clears.append(address)
        else:
            # Full records are retained. This foundation claims ordering, epoch,
            # continuity and output/state anchors, not a full SM83 register oracle.
            from test_integration import decode_record
            record=decode_record(value)
            assert record['seq']==self.records and record['epoch']==2 and record['dot']>self.last_record_dot, 'SPRINGTRAIL_RECORD_ORDER'
            self.records+=1;self.last_record_dot=record['dot']

    def finish(self, pause):
        assert self.ended and self.pixels==69120 and len(self.inputs)==1, 'SPRINGTRAIL_MISSING'
        assert self.lcd==[(52,0),(LCD,145)], self.lcd
        assert len(self.states)==2 and self.states[0]==(120,0), self.states
        assert LCD+135888<=self.states[1][0]<LCD+140448 and self.states[1][1]==1, self.states
        assert self.clears==list(range(0x98a4,0x98af))+list(range(0x98e4,0x98ef)), 'SPRINGTRAIL_TITLE_CLEAR'
        assert END<=pause<=END+2000 and self.records>5800, 'SPRINGTRAIL_COMPLETION'
        for frame in range(3):
            assert bytes(self.frames[frame])==image(frame), 'SPRINGTRAIL_FRAME_BYTES'
            if frame:assert zlib.crc32(self.frames[frame])==FRAME_CRC[frame], 'SPRINGTRAIL_CRC'
        return dict(pixels=self.pixels,records=self.records,states=self.states,inputs=self.inputs,pause_dot=pause,
                    crc32=[f'{zlib.crc32(frame):08x}' for frame in self.frames])
