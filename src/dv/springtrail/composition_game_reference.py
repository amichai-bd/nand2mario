"""Fixed title/Start composition; public LCD write supplies only phase origin."""
from composition_reference import scene,title_image
from interactions_reference import Game,update
from interaction_cases import ADDRESSES,state_bytes

PERIOD=70224


class Check:
    def __init__(self,short=False):
        self.short=short;self.lcd=None;self.memory={};self.partial=[];self.ready=[]
        self.states=[Game(),update(Game(),129)]
        self.images=[bytes(23040),title_image()]
        self.pixels=0;self.frames=[bytearray(),bytearray()];self.triggers=[];self.dma=[]
        self.ended=False;self.records=0;self.last_record=0;self.input_dot=None
        self.tiles=[]

    def pixel(self,value):
        frame,index=divmod(self.pixels,23040)
        assert self.lcd is not None and frame<2,'COMPOSITION_EXTRA_PIXEL'
        y,x=divmod(index,160)
        want=(2<<21)|(x<<13)|(y<<5)|(self.images[frame][index]<<3)|(int(index==0)<<2)|int(frame!=0)
        assert value&((1<<53)-1)==want,f'COMPOSITION_PIXEL frame={frame} index={index}'
        dot=value>>53
        assert self.lcd+frame*PERIOD+y*456<=dot<self.lcd+frame*PERIOD+(y+1)*456,'COMPOSITION_ROW'
        self.frames[frame].append((value>>3)&3);self.pixels+=1

    def line(self,text):
        assert not self.ended,'COMPOSITION_AFTER_END'
        kind,raw=text.strip().split(' ')
        if kind=='END':
            assert int(raw)==0 and not self.partial,'COMPOSITION_END'
            self.ended=True;return
        value=int(raw,16)
        if kind=='P':self.pixel(value);return
        if kind=='R':
            from test_integration import decode_record
            row=decode_record(value)
            assert row['seq']==self.records and row['epoch']==2 and row['dot']>self.last_record,'COMPOSITION_RETIRE'
            self.records+=1;self.last_record=row['dot'];return
        assert kind=='W','COMPOSITION_TRACE_KIND'
        dot,address,data=value>>24,(value>>8)&65535,value&255
        self.memory[address]=data
        if 0x8000<=address<0x84a0:
            assert self.lcd is None,'COMPOSITION_LATE_TILES'
            self.tiles.append((address,data))
        if address==0xff40:
            if data==0:
                assert self.lcd is None,'COMPOSITION_LCD_OFF'
            elif self.lcd is None:
                assert data==0x93 and 100000<dot<130000,'COMPOSITION_STARTUP_BOUND'
                self.lcd=dot
            else:
                assert data==0x93,'COMPOSITION_OBJECT_MODE'
        if 0xc100<=address<0xc1a0:
            index=len(self.ready)
            assert index<2 and address==0xc100+len(self.partial),'COMPOSITION_SHADOW_ORDER'
            self.partial.append(data)
            if len(self.partial)==160:
                assert bytes(self.partial)==scene(self.states[index]),'COMPOSITION_SHADOW'
                assert bytes(self.memory[a] for a in ADDRESSES)==state_bytes(self.states[index],0 if index==0 else 129),'COMPOSITION_STATE'
                if index==0:assert self.lcd is None,'COMPOSITION_INITIAL_READY'
                else:assert self.lcd+PERIOD<=dot<self.lcd+PERIOD+46000,'COMPOSITION_VISIBLE_READY'
                self.ready.append(dot);self.partial=[]
        if address==0xff46:
            n=len(self.triggers)
            assert n<3 and data==0xc1,'COMPOSITION_DMA_TRIGGER'
            if n==0:assert len(self.ready)==1 and self.lcd is None,'COMPOSITION_INIT_DMA'
            else:
                assert len(self.ready)==n,'COMPOSITION_PUBLISH_READY'
                assert self.lcd+(n-1)*PERIOD+65664<=dot<self.lcd+n*PERIOD-644,'COMPOSITION_VBLANK_DMA'
            self.triggers.append(dot)
        if self.lcd is not None and dot>self.lcd and (0x8000<=address<0xa000 or 0xfe00<=address<0xfea0 or address in (0xff40,0xff43,0xff46)):
            assert 65664<=(dot-self.lcd)%PERIOD<PERIOD,'COMPOSITION_DISPLAY_WINDOW'

    def finish(self,pause,tile_bytes):
        assert self.ended and not self.partial,'COMPOSITION_INCOMPLETE'
        assert self.tiles==list(enumerate(tile_bytes,0x8000)),'COMPOSITION_TILES'
        publications=1 if self.short else 3
        assert len(self.triggers)==publications and len(self.dma)==160*publications,'COMPOSITION_DMA_COUNT'
        for i,value in enumerate(self.dma):
            publication,offset=divmod(i,160)
            want=scene(self.states[max(0,publication-1)])[offset]
            assert (value>>18,(value>>8)&255,value&255)==(self.triggers[publication]+8+4*offset,offset,want),'COMPOSITION_DMA_BYTE'
        if self.short:
            assert 160<=self.pixels<640 and len(self.ready)==1 and self.input_dot is None,'COMPOSITION_SHORT_END'
        else:
            assert self.pixels==46080 and len(self.ready)==2,'COMPOSITION_FRAME_COUNT'
            assert self.lcd+60000<=self.input_dot<=self.lcd+62000,'COMPOSITION_INPUT_WINDOW'
            assert self.triggers[-1]+644<pause<self.lcd+2*PERIOD,'COMPOSITION_FINAL_WINDOW'
        return dict(pixels=self.pixels,records=self.records,lcd=self.lcd,ready=self.ready,
                    dma_bytes=len(self.dma),input_dot=self.input_dot,pause=pause)
