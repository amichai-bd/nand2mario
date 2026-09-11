"""Fixed title/Start composition; public LCD write supplies only phase origin."""
from dataclasses import replace
from motion_frames import scene, image
from hud_reference import hud_tiles, column
from motion_reference import Player, step
from interactions_reference import Game
from interaction_cases import ADDRESSES as OLD_ADDRESSES, state_bytes as old_bytes

ADDRESSES = OLD_ADDRESSES + list(range(0xc060, 0xc06a))


def state_bytes(game, buttons=0):
    p = game.player
    return old_bytes(game, buttons) + bytes((p.counter, p.direction, p.speed,
        p.phase, p.animation, p.pose, p.jump, p.index, p.saved, p.facing))


def initial_states():
    title = Game(player=Player())
    # One Start+Right update at the initial scene: no contact/pickup/goal.
    moved = replace(title, mode=1, previous=129, player=step(title.player, 129),
                    enemy_x=256*16+8, timer=1)
    return [title, moved]

PERIOD=70224


class Check:
    def __init__(self,short=False):
        self.short=short;self.lcd=None;self.memory={};self.partial=[];self.ready=[]
        self.states=initial_states()
        self.images=[bytes(23040),image(self.states[0])]
        self.pixels=0;self.frames=[bytearray(),bytearray()];self.triggers=[];self.dma=[]
        self.ended=False;self.records=0;self.last_record=0;self.input_dot=None
        self.tiles=[];self.lines=0;self.inputs=[]
        self.tokens=[];self.irq=[];self.sources=[];self.split=[];self.vb_writes=[];self.hud=[]
        self.hud_partial=[];self.cache=[];self.bus_trigger=None;self.bus_count=0;self.samples=[]

    def pixel(self,value):
        frame,index=divmod(self.pixels,23040)
        assert self.lcd is not None and frame<2,'MOTION_EXTRA_PIXEL'
        y,x=divmod(index,160)
        want=(2<<21)|(x<<13)|(y<<5)|(self.images[frame][index]<<3)|(int(index==0)<<2)|int(frame!=0)
        assert value&((1<<53)-1)==want,f'MOTION_PIXEL frame={frame} index={index}'
        dot=value>>53
        assert self.lcd+frame*PERIOD+y*456<=dot<self.lcd+frame*PERIOD+(y+1)*456,'MOTION_ROW'
        self.frames[frame].append((value>>3)&3);self.pixels+=1

    def line(self,text):
        assert not self.ended,'MOTION_AFTER_END'
        kind,raw=text.strip().split(' ')
        if kind=='END':
            assert int(raw)==self.lines and not self.partial,'MOTION_END'
            self.ended=True;return
        self.lines+=1
        value=int(raw,16)
        if kind=='P':self.pixel(value);return
        if kind=='I':
            epoch,dot,buttons=value>>72,(value>>8)&((1<<64)-1),value&255
            assert not self.short and not self.inputs and epoch==2 and buttons==129,'MOTION_INPUT'
            assert self.lcd is not None and self.lcd+60000<=dot<=self.lcd+62000,'MOTION_INPUT_WINDOW'
            self.inputs.append(dot);return
        if kind=='R':
            from test_integration import decode_record
            row=decode_record(value)
            assert row['seq']==self.records and row['epoch']==2 and row['dot']>self.last_record,'MOTION_RETIRE'
            assert not row['halt_bug'],'MOTION_HALT_BUG'
            if row['kind']==1:
                assert row['pc_after'] in (0x40,0x48),'MOTION_IRQ_VECTOR'
                self.irq.append((row['dot'],row['pc_after']))
            if self.triggers and self.triggers[-1]+8<=row['dot']<=self.triggers[-1]+644:
                assert row['kind']==0 and 0xff80<=row['pc_before']<=0xfffe and row['ime']==0,'MOTION_DMA_IRQ'
            self.records+=1;self.last_record=row['dot'];return
        assert kind=='W','MOTION_TRACE_KIND'
        dot,address,data=value>>24,(value>>8)&65535,value&255
        self.memory[address]=data
        if 0x8000<=address<0x8620:
            assert self.lcd is None,'MOTION_LATE_TILES'
            self.tiles.append((address,data))
        if address==0xff40:
            if data==0:
                assert self.lcd is None,'MOTION_LCD_OFF'
            elif self.lcd is None:
                assert data==0x91 and dot==139388,'MOTION_STARTUP_BOUND'
                self.lcd=dot
            else:
                assert data in (0x91,0x93),'MOTION_OBJECT_MODE'
        if 0xc100<=address<0xc1a0:
            index=len(self.ready)
            assert index<2 and address==0xc100+len(self.partial),'MOTION_SHADOW_ORDER'
            self.partial.append(data)
            if len(self.partial)==160:
                assert bytes(self.partial)==scene(self.states[index]),'MOTION_SHADOW'
                assert bytes(self.memory[a] for a in ADDRESSES)==state_bytes(self.states[index],0 if index==0 else 129),'MOTION_STATE'
                if index==0:assert self.lcd is None,'MOTION_INITIAL_READY'
                else:assert self.lcd+PERIOD<=dot<self.lcd+PERIOD+49280,'MOTION_VISIBLE_READY'
                self.ready.append(dot);self.partial=[]
        if address==0xff46:
            n=len(self.triggers)
            assert n<3 and data==0xc1,'MOTION_DMA_TRIGGER'
            if n==0:assert len(self.ready)==1 and self.lcd is None,'MOTION_INIT_DMA'
            else:
                assert len(self.ready)==n,'MOTION_PUBLISH_READY'
                assert self.lcd+(n-1)*PERIOD+65664<=dot<self.lcd+n*PERIOD-644,'MOTION_VBLANK_DMA'
                assert dot+644<=self.lcd+(n-1)*PERIOD+65664+4480,'MOTION_DMA_COMPLETION_BOUND'
            self.triggers.append(dot)
        if address==0xff0f:assert self.lcd is None,'MOTION_PENDING_IRQ_CLEAR'
        if address==0xc019 and self.lcd is not None:
            assert 65664<=(dot-self.lcd)%PERIOD<70224 and data==129,'MOTION_JOYP_SAMPLE'
            self.samples.append(dot)
        if address==0xc050 and data==1:
            assert self.lcd is not None,'MOTION_TOKEN_STARTUP'
            n=len(self.tokens)
            assert self.lcd+n*PERIOD+65662<=dot<=self.lcd+n*PERIOD+65852,'MOTION_TOKEN_TIME'
            self.tokens.append(dot)
        if 0xc220<=address<=0xc226:
            index=len(self.hud)
            assert index<2 and address==0xc220+len(self.hud_partial),'MOTION_CACHE_ORDER'
            self.hud_partial.append(data)
            if len(self.hud_partial)==7:
                assert bytes(self.hud_partial)==hud_tiles(self.states[index]),'MOTION_CACHE_DATA'
                self.hud.append(dot);self.hud_partial=[]
        if 0xc200<=address<0xc220:
            assert len(self.cache)<32 and address==0xc200+len(self.cache),'MOTION_COLUMN_CACHE_ORDER'
            self.cache.append(data)
            assert data==(column(0)+column(1))[len(self.cache)-1],'MOTION_COLUMN_CACHE_DATA'
            assert self.lcd+PERIOD<=dot<self.lcd+PERIOD+49280,'MOTION_COLUMN_CACHE_READY'
        if self.lcd is not None and dot>self.lcd:
            phase=(dot-self.lcd)%PERIOD
            if address in (0xff40,0xff43) and phase<65664:
                frame=(dot-self.lcd)//PERIOD
                assert 15*456+280<=phase<=15*456+384,'MOTION_SPLIT_WINDOW'
                expected=(0xff43,0) if len(self.split)%2==0 else (0xff40,0x93)
                assert (address,data)==expected,'MOTION_SPLIT_ORDER'
                self.split.append((frame,dot,address,data))
            elif 0x8000<=address<0xa000 or 0xfe00<=address<0xfea0 or address in (0xff40,0xff42,0xff43,0xff46):
                assert 65664<=phase<PERIOD,'MOTION_DISPLAY_WINDOW'
                assert phase<65664+4480,'MOTION_PUBLICATION_BOUND'
                self.vb_writes.append((dot,address,data))

    def bus(self,raw):
        dot,address,write,data=raw>>25,(raw>>9)&65535,(raw>>8)&1,raw&255
        if write and address==0xff46:self.bus_trigger=dot
        if self.bus_trigger is not None and self.bus_trigger+8<=dot<=self.bus_trigger+644:
            assert 0xff80<=address<=0xfffe,'MOTION_DMA_BUS'
            self.bus_count+=1

    def finish(self,pause,tile_bytes):
        assert self.ended and not self.partial and not self.hud_partial,'MOTION_INCOMPLETE'
        assert self.tiles==list(enumerate(tile_bytes,0x8000)),'MOTION_TILES'
        assert self.bus_count>0 and self.records>100,'MOTION_MISSING_PROGRESS'
        publications=1 if self.short else 3
        assert len(self.triggers)==publications and len(self.dma)==160*publications,'MOTION_DMA_COUNT'
        for i,value in enumerate(self.dma):
            publication,offset=divmod(i,160)
            want=scene(self.states[max(0,publication-1)])[offset]
            assert (value>>18,(value>>8)&255,value&255)==(self.triggers[publication]+8+4*offset,offset,want),'MOTION_DMA_BYTE'
        if self.short:
            assert 160<=self.pixels<640 and len(self.ready)==1 and self.input_dot is None,'MOTION_SHORT_END'
        else:
            assert self.pixels==46080 and len(self.ready)==2 and len(self.hud)==2,'MOTION_FRAME_COUNT'
            assert len(self.cache)==32 and len(self.tokens)==2 and len(self.samples)==2,'MOTION_UPDATE_COUNT'
            assert [vector for _,vector in self.irq]==[0x48,0x40,0x48,0x40],'MOTION_IRQ_ORDER'
            assert [row[0] for row in self.split]==[0,0,1,1],'MOTION_SPLIT_COUNT'
            expected_sources=[(self.lcd+6838,2),(self.lcd+65662,1),(self.lcd+PERIOD+6838,2),(self.lcd+PERIOD+65662,1)]
            assert self.sources==expected_sources,'MOTION_IRQ_SOURCES'
            for (dot,vector),(request,source) in zip(self.irq,self.sources):
                assert 20<=dot-request<=52,'MOTION_IRQ_LATENCY'
            # Both maps receive the same prior-state HUD before each DMA.
            for publication in (1,2):
                writes=[(address,data) for dot,address,data in self.vb_writes if self.lcd+(publication-1)*PERIOD+65664<=dot<self.lcd+publication*PERIOD]
                expected=[]
                for base in (0x9800,0x9c00):
                    expected += list(zip([base+i for i in range(1,7)]+[base+18],hud_tiles(self.states[publication-1])))
                assert [(a,d) for a,d in writes if a in {a for a,_ in expected}]==expected,'MOTION_DUAL_MAP'
            columns=[(a,d) for _,a,d in self.vb_writes if 0x9c40<=a<0x9e40]
            assert columns==[(0x9c40+x+y*32,v) for x in (0,1) for y,v in enumerate(column(x))],'MOTION_RESTORE_WRITES'
            assert self.lcd+60000<=self.input_dot<=self.lcd+62000,'MOTION_INPUT_WINDOW'
            assert self.inputs==[self.input_dot],'MOTION_APPLIED_INPUT'
            assert self.triggers[-1]+644<pause<self.lcd+2*PERIOD,'MOTION_FINAL_WINDOW'
        return dict(pixels=self.pixels,records=self.records,lcd=self.lcd,ready=self.ready,
                    dma_bytes=len(self.dma),input_dot=self.input_dot,pause=pause,irq=self.irq,split=self.split,tokens=self.tokens,hud=self.hud,samples=self.samples,bus_count=self.bus_count)
