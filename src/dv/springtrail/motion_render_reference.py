"""Fixed renderer operands; no gameplay or expected-image selection from DUT state."""
from motion_game_reference import Check as GameCheck, PERIOD
from motion_frames import scene, courier, tiles
from composition_reference import raster
from hud_reference import image, hud_tiles, column
from interactions_reference import Game
from motion_reference import Player

class Check(GameCheck):
    def __init__(self, short=False):
        super().__init__(short)
        self.game=Game(mode=1,player=Player(x=120*16,y=12*16,camera=97,pose=2))
        self.base=scene(self.game)
        self.extra=courier(12,True,60,32)
        self.secondary_base=0xc140
        self.shadow=self.base[:64]+self.extra+bytes(80)
        self.images=[bytes(23040),image(self.game,object_pixels=raster(self.shadow,tiles()))]
        self.secondary=[];self.secondary_ready=None
        self.initial_columns=[];self.terminal=None;self.published=[];self.halted=False

    def line(self,text):
        kind,raw=text.strip().split(' ')
        if kind=='R' and self.terminal is not None:
            from test_integration import decode_record
            row=decode_record(int(raw,16))
            assert not self.halted,'HUD_AFTER_HALT'
            if row['opcode']==0x76:self.halted=True
        if kind=='END':assert self.terminal is not None and self.halted,'HUD_RENDER_END'
        if kind!='W':
            assert kind!='I','HUD_RENDER_INPUT'
            return super().line(text)
        assert not self.ended,'HUD_AFTER_END'
        self.lines+=1
        value=int(raw,16);dot,address,data=value>>24,(value>>8)&65535,value&255
        self.memory[address]=data
        if 0x8000<=address<0x88c0:
            assert self.lcd is None,'HUD_LATE_TILES'
            self.tiles.append((address,data))
        if address==0xff40:
            if data==0:assert self.lcd is None,'HUD_LCD_OFF'
            elif self.lcd is None:
                assert data==0x99 and 0<dot<200000,'HUD_STARTUP_BOUND'
                self.lcd=dot
            else:assert data in (0x99,0x9b),'HUD_OBJECT_MODE'
        if 0xc100<=address<0xc1a0:
            assert self.lcd is None,'MOTION_LATE_SHADOW'
            if not self.ready:
                assert address==0xc100+len(self.partial),'MOTION_BASE_ORDER'
                self.partial.append(data)
                if len(self.partial)==160:
                    assert bytes(self.partial)==self.base,'MOTION_BASE_SHADOW'
                    self.ready.append(dot);self.partial=[]
            else:
                assert self.secondary_ready is None and address==self.secondary_base+len(self.secondary),'MOTION_SECONDARY_ORDER'
                self.secondary.append(data)
                if len(self.secondary)==len(self.extra):
                    assert bytes(self.secondary)==self.extra,'MOTION_SECONDARY_SHADOW'
                    self.secondary_ready=dot
        if address==0xff46:
            n=len(self.triggers)
            assert n<2 and data==0xc1 and len(self.ready)==1 and self.secondary_ready is not None,'HUD_DMA_TRIGGER'
            if n==0:assert self.lcd is None,'HUD_INIT_DMA'
            else:
                assert self.lcd+65664<=dot and dot+644<=self.lcd+65664+4480,'HUD_DMA_COMPLETION_BOUND'
            self.triggers.append(dot)
        if address==0xff0f:assert self.lcd is None,'HUD_PENDING_IRQ_CLEAR'
        if address==0xc019:assert self.lcd is None,'HUD_RENDER_SAMPLE'
        if address==0xc050 and data==1:
            n=len(self.tokens)
            assert self.lcd is not None and self.lcd+n*PERIOD+65662<=dot<=self.lcd+n*PERIOD+65852,'HUD_TOKEN_TIME'
            self.tokens.append(dot)
        if address==0xc051:self.published.append((dot,data))
        if address==0xc0ff:
            assert data==0xa5 and self.terminal is None,'HUD_RENDER_TERMINAL'
            self.terminal=dot
        if 0xc220<=address<=0xc226:
            assert not self.hud and address==0xc220+len(self.hud_partial),'HUD_CACHE_ORDER'
            self.hud_partial.append(data)
            if len(self.hud_partial)==7:
                assert bytes(self.hud_partial)==hud_tiles(self.game),'HUD_CACHE_DATA'
                self.hud.append(dot);self.hud_partial=[]
        if 0xc200<=address<0xc220:
            index=len(self.cache);col,offset=divmod(index,16)
            assert col<=32 and address==0xc200+offset and data==column(col)[offset],'HUD_RENDER_CACHE'
            assert self.lcd is None,'HUD_RENDER_READY'
            self.cache.append(data)
        if 0x9c40<=address<0x9e40 and self.lcd is None:self.initial_columns.append((address,data))
        if self.lcd is not None and dot>self.lcd:
            phase=(dot-self.lcd)%PERIOD
            if address in (0xff40,0xff43) and phase<65664:
                frame=(dot-self.lcd)//PERIOD
                assert 15*456+280<=phase<=15*456+384,'HUD_SPLIT_WINDOW'
                expected=(0xff43,95 if frame==0 else 97) if len(self.split)%2==0 else (0xff40,0x9b)
                assert (address,data)==expected,'HUD_SPLIT_ORDER'
                self.split.append((frame,dot,address,data))
            elif 0x8000<=address<0xa000 or 0xfe00<=address<0xfea0 or address in (0xff40,0xff42,0xff43,0xff46):
                assert 65664<=phase<65664+4480,'HUD_PUBLICATION_BOUND'
                self.vb_writes.append((dot,address,data))

    def finish(self,pause,tile_bytes):
        assert self.ended and not self.partial and not self.hud_partial,'HUD_INCOMPLETE'
        assert len(self.secondary)==len(self.extra) and self.ready[0]<self.secondary_ready<self.triggers[0],'MOTION_SECONDARY_COMPLETE'
        assert self.tiles==list(enumerate(tile_bytes,0x8000)),'HUD_TILES'
        assert len(self.ready)==len(self.hud)==1 and self.bus_count>0 and self.records>100,'HUD_MISSING_PROGRESS'
        assert self.initial_columns==[(0x9c40+x+y*32,v) for x in range(32) for y,v in enumerate(column(x))],'HUD_INITIAL_RING'
        assert len(self.cache)==528,'HUD_RENDER_CACHE_COUNT'
        assert len(self.triggers)==2 and len(self.dma)==320,'HUD_DMA_COUNT'
        for i,value in enumerate(self.dma):
            pub,offset=divmod(i,160)
            assert (value>>18,(value>>8)&255,value&255)==(self.triggers[pub]+8+4*offset,offset,self.shadow[offset]),'HUD_DMA_BYTE'
        assert self.pixels==46080 and self.frames[1][80*160+159]==1,'HUD_RENDER_PIXELS'
        assert len(self.published)==2 and [v for _,v in self.published]==[95,97],'HUD_PUBLISHED_CAMERA'
        assert self.published[0][0]<self.lcd<self.published[1][0]<self.triggers[1],'HUD_CAMERA_OWNERSHIP'
        assert [v for _,v in self.irq]==[0x48,0x40,0x48,0x40] and len(self.tokens)==2,'HUD_IRQ_ORDER'
        assert [r[0] for r in self.split]==[0,0,1,1],'HUD_SPLIT_COUNT'
        assert self.sources==[(self.lcd+6838,2),(self.lcd+65662,1),(self.lcd+PERIOD+6838,2),(self.lcd+PERIOD+65662,1)],'HUD_IRQ_SOURCES'
        for (dot,_),(request,_) in zip(self.irq,self.sources):assert 20<=dot-request<=52,'HUD_IRQ_LATENCY'
        writes=[(a,d) for _,a,d in self.vb_writes]
        expected=[(0x9c40+y*32,v) for y,v in enumerate(column(32))]
        assert [(a,d) for a,d in writes if 0x9c40<=a<0x9e40]==expected,'HUD_ENTERING_COLUMN'
        expected=[]
        for base in (0x9800,0x9c00):expected+=list(zip([base+i for i in range(1,7)]+[base+18],hud_tiles(self.game)))
        assert [(a,d) for a,d in writes if a in {a for a,_ in expected}]==expected,'HUD_DUAL_MAP'
        assert self.terminal is not None and self.lcd+PERIOD+65664<self.terminal<pause<self.lcd+2*PERIOD,'HUD_FINAL_WINDOW'
        return dict(pixels=self.pixels,records=self.records,lcd=self.lcd,ready=self.ready,secondary_ready=self.secondary_ready,dma_bytes=len(self.dma),pause=pause,irq=self.irq,split=self.split,terminal=self.terminal,bus_count=self.bus_count)
