"""Complete selected frames, with sprite-variable timing inside fixed lines."""
import zlib
from movement_frames import image
from movement_reference import Player,step

# Instruction-derived LCD commit; inputs precede the second VBlank.
LCD=48528
START_WINDOW=(178528,180528)
END=254436
FIRST_WORLD=step(Player(),129)
FRAMES=(bytes(23040),image(title=True),image(FIRST_WORLD))
CRC=(0xb15161f6,0x5324bc1f,0xae96d493)


class Check:
    def __init__(self):
        self.frames=[bytearray(),bytearray(),bytearray()]
        self.pixels=0;self.last_pixel_dot=0;self.lines=0;self.ended=False
        self.inputs=[];self.states=[];self.lcd=[];self.clears=[];self.objects=[]
        self.records=0;self.last_record_dot=0

    def pixel(self,value):
        frame,index=divmod(self.pixels,23040)
        assert frame<3,'SPRINGTRAIL_EXTRA_FRAME'
        y,x=divmod(index,160)
        dot=value>>53
        expected=(2<<21)|(x<<13)|(y<<5)|(FRAMES[frame][index]<<3)|(int(index==0)<<2)|int(frame!=0)
        assert value&((1<<53)-1)==expected,f'SPRINGTRAIL_PIXEL frame={frame} index={index} expected={expected:014x} actual={value&((1<<53)-1):014x} dot={dot}'
        # Object fetches can delay pixels. Every output must remain in its own
        # independently numbered line; no observed frame/bank selects the image.
        start=LCD+frame*70224+y*456
        assert start<=dot<start+456 and dot>self.last_pixel_dot,'SPRINGTRAIL_PIXEL_TIME'
        self.last_pixel_dot=dot;self.pixels+=1
        self.frames[frame].append((value>>3)&3)

    def line(self,line):
        assert not self.ended,'SPRINGTRAIL_AFTER_END'
        kind,raw=line.rstrip('\n').split(' ')
        if kind=='END':
            assert int(raw)==self.lines,'SPRINGTRAIL_TRACE_COUNT'
            self.ended=True;return
        widths={'P':30,'W':22,'I':26,'R':96}
        assert kind in widths and len(raw)==widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()),'SPRINGTRAIL_TRACE_UNKNOWN'
        value=int(raw,16);self.lines+=1
        if kind=='P':self.pixel(value)
        elif kind=='I':
            epoch=value>>72;dot=(value>>8)&((1<<64)-1);buttons=value&255
            assert not self.inputs and epoch==2 and START_WINDOW[0]<=dot<=START_WINDOW[1] and buttons==129,'SPRINGTRAIL_START'
            self.inputs.append((dot,buttons))
        elif kind=='W':
            dot=value>>24;address=(value>>8)&65535;data=value&255
            if address==0xc000:self.states.append((dot,data))
            if address==0xff40:self.lcd.append((dot,data))
            if dot>LCD and (0x8000<=address<0xa000 or 0xfe00<=address<0xfea0 or address==0xff43):
                # First VBlank occurs before Start. The second updates the
                # title and courier. Both use the normal 4560-dot interval.
                assert any(LCD+65664+70224*n<=dot<LCD+70224*(n+1) for n in (0,1)),'SPRINGTRAIL_VBLANK_WRITE'
                if 0x8000<=address<0xa000:
                    assert data==0,'SPRINGTRAIL_TITLE_DATA'
                    self.clears.append(address)
                else:self.objects.append((address,data))
        else:
            from test_integration import decode_record
            record=decode_record(value)
            assert record['seq']==self.records and record['epoch']==2 and record['dot']>self.last_record_dot,'SPRINGTRAIL_RECORD_ORDER'
            self.records+=1;self.last_record_dot=record['dot']

    def finish(self,pause):
        assert self.ended and self.pixels==69120 and len(self.inputs)==1,'SPRINGTRAIL_MISSING'
        assert self.lcd==[(52,0),(LCD,151)],self.lcd
        assert len(self.states)==2 and self.states[0]==(120,0),self.states
        assert LCD+135888<=self.states[1][0]<LCD+140448 and self.states[1][1]==1,self.states
        assert self.clears==list(range(0x98a4,0x98af))+list(range(0x98e4,0x98ef)),'SPRINGTRAIL_TITLE_CLEAR'
        assert self.objects==[(0xff43,0),(0xfe00,128),(0xfe01,33),(0xfe02,12),(0xfe03,0)],self.objects
        assert END<=pause<=END+2000 and self.records>5800,'SPRINGTRAIL_COMPLETION'
        for number,frame in enumerate(self.frames):
            assert bytes(frame)==FRAMES[number] and zlib.crc32(frame)==CRC[number],'SPRINGTRAIL_FRAME_BYTES'
        return dict(pixels=self.pixels,records=self.records,states=self.states,inputs=self.inputs,
                    pause_dot=pause,crc32=[f'{zlib.crc32(frame):08x}' for frame in self.frames])
