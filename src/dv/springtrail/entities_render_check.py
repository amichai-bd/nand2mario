"""Independent fixed-scene pixels and complete public publication evidence."""
import json
from pathlib import Path
from hud_game_reference import Check as BaseCheck, PERIOD
from hud_reference import column, hud_tiles, progress_tiles, PROGRESS_ROW
from entities_frames import scene, image, tiles
from entities_render_program import SCENES
from entities_cases import ADDRESSES, state_bytes


def expected_tiles():
    out=bytearray()
    bank=tiles()
    # The raster bank omits unused legacy tiles; the upload still loads all42.
    source=Path(__file__).resolve().parents[3]/"src/sw/springtrail/tiles.json"
    pixels=json.loads(source.read_text())["pixels"]
    bank[:42]=[[row[t*8:(t+1)*8] for row in pixels] for t in range(42)]
    for tile in bank:
        for row in tile:
            out.extend((sum((v&1)<<(7-x) for x,v in enumerate(row)),
                        sum(((v>>1)&1)<<(7-x) for x,v in enumerate(row))))
    assert len(out)==174*16
    return bytes(out)


class Check(BaseCheck):
    def __init__(self, short=False, variant='normal', source_lcd=None):
        super().__init__(short)
        self.world=SCENES[variant]
        self.shadow=scene(self.world)
        self.images=[bytes(23040),image(self.world)]
        self.source_lcd=source_lcd
        self.terminal=None;self.halted=False;self.initial_columns=[]

    def line(self,text):
        kind,raw=text.strip().split(' ')
        if kind=='R' and self.terminal is not None:
            from n2m.interface_codec import decode_record
            row=decode_record(int(raw,16))
            assert not self.halted,'ENTITY_AFTER_HALT'
            if row['opcode']==0x76:self.halted=True
        if kind=='END' and not self.short:
            assert self.terminal is not None and self.halted,'ENTITY_RENDER_END'
        if kind!='W':
            assert kind!='I','ENTITY_RENDER_INPUT'
            return super().line(text)
        assert not self.ended,'ENTITY_AFTER_END'
        self.lines+=1
        value=int(raw,16);dot,address,data=value>>24,(value>>8)&65535,value&255
        self.memory[address]=data
        if 0x8000<=address<0x8ae0:
            assert self.lcd is None,'ENTITY_LATE_TILES'
            self.tiles.append((address,data))
        if address==0xff40:
            if data==0:assert self.lcd is None,'ENTITY_LCD_OFF'
            elif self.lcd is None:
                assert data==0x99 and dot==self.source_lcd,'ENTITY_STARTUP'
                self.lcd=dot
            else:assert data in (0x99,0x9b),'ENTITY_OBJECT_MODE'
        if 0xc100<=address<0xc1a0:
            assert self.lcd is None and not self.ready,'ENTITY_LATE_SHADOW'
            assert address==0xc100+len(self.partial),'ENTITY_SHADOW_ORDER'
            self.partial.append(data)
            if len(self.partial)==160:
                assert bytes(self.partial)==self.shadow,'ENTITY_SHADOW'
                assert bytes(self.memory[a] for a in ADDRESSES)==state_bytes(self.world),'ENTITY_RENDER_STATE'
                self.ready.append(dot);self.partial=[]
        if address==0xff46:
            n=len(self.triggers)
            assert n<2 and data==0xc1 and len(self.ready)==1,'ENTITY_DMA_TRIGGER'
            if n==0:assert self.lcd is None,'ENTITY_INITIAL_DMA'
            else:assert self.lcd+65664<=dot and dot+644<=self.lcd+65664+4480,'ENTITY_DMA_WINDOW'
            self.triggers.append(dot)
        if address==0xff0f:assert self.lcd is None,'ENTITY_PENDING_IRQ_CLEAR'
        if address==0xc019:assert self.lcd is None,'ENTITY_RENDER_SAMPLE'
        if address==0xc050 and data==1:
            n=len(self.tokens)
            assert self.lcd is not None and self.lcd+n*PERIOD+65662<=dot<=self.lcd+n*PERIOD+65852,'ENTITY_TOKEN_TIME'
            self.tokens.append(dot)
        if address==0xc0ff:
            assert data==0xa5 and self.terminal is None,'ENTITY_TERMINAL'
            self.terminal=dot
        if 0xc220<=address<=0xc226:
            assert not self.hud and address==0xc220+len(self.hud_partial),'ENTITY_HUD_ORDER'
            self.hud_partial.append(data)
            if len(self.hud_partial)==7:
                assert bytes(self.hud_partial)==hud_tiles(self.world),'ENTITY_HUD_DATA'
                self.hud.append(dot);self.hud_partial=[]
        if 0x9c40<=address<0x9e40 and self.lcd is None:
            self.initial_columns.append((address,data))
        if self.lcd is not None and dot>self.lcd:
            phase=(dot-self.lcd)%PERIOD
            if address in (0xff40,0xff43) and phase<65664:
                frame=(dot-self.lcd)//PERIOD
                assert 15*456+280<=phase<=15*456+384,'ENTITY_SPLIT_WINDOW'
                want=(0xff43,96) if len(self.split)%2==0 else (0xff40,0x9b)
                assert (address,data)==want,'ENTITY_SPLIT_ORDER'
                self.split.append((frame,dot,address,data))
            elif 0x8000<=address<0xa000 or 0xfe00<=address<0xfea0 or address in (0xff40,0xff42,0xff43,0xff46):
                assert 65664<=phase<65664+4480,'ENTITY_PUBLICATION_WINDOW'
                self.vb_writes.append((dot,address,data))

    def finish(self,pause,tile_bytes):
        assert self.ended and not self.partial and not self.hud_partial,'ENTITY_INCOMPLETE'
        assert tile_bytes==expected_tiles(),'ENTITY_TILE_EXPECTATION'
        assert self.tiles==list(enumerate(tile_bytes,0x8000)),'ENTITY_TILES'
        assert len(self.ready)==len(self.hud)==1 and self.bus_count>0 and self.records>100,'ENTITY_PROGRESS'
        wants=[(0x9c40+(x&31)+y*32,v) for x in range(12,44)
               for y,v in enumerate(column(x,self.world.blocks))]
        assert self.initial_columns==wants,'ENTITY_INITIAL_RING'
        publications=1 if self.short else 2
        assert len(self.triggers)==publications and len(self.dma)==160*publications,'ENTITY_DMA_COUNT'
        for i,value in enumerate(self.dma):
            pub,offset=divmod(i,160)
            assert (value>>18,(value>>8)&255,value&255)==(self.triggers[pub]+8+4*offset,offset,self.shadow[offset]),'ENTITY_DMA_BYTE'
        if self.short:
            assert 160<=self.pixels<640 and self.terminal is None,'ENTITY_SHORT_END'
        else:
            assert self.pixels==46080,'ENTITY_PIXELS'
            assert [v for _,v in self.irq]==[0x48,0x40,0x48,0x40] and len(self.tokens)==2,'ENTITY_IRQ_ORDER'
            assert [r[0] for r in self.split]==[0,0,1,1],'ENTITY_SPLIT_COUNT'
            assert self.sources==[(self.lcd+6838,2),(self.lcd+65662,1),
                                 (self.lcd+PERIOD+6838,2),(self.lcd+PERIOD+65662,1)],'ENTITY_IRQ_SOURCE'
            for (dot,_),(request,_) in zip(self.irq,self.sources):
                assert 20<=dot-request<=52,'ENTITY_IRQ_LATENCY'
            writes=[(a,d) for _,a,d in self.vb_writes]
            wanted=[]
            for base in (0x9800,0x9c00):
                wanted+=list(zip([base+i for i in range(1,7)]+[base+18],hud_tiles(self.world)))
            assert [(a,d) for a,d in writes if a in {a for a,_ in wanted}]==wanted,'ENTITY_HUD_PUBLICATION'
            progress=[(0x9c20+offset,tile) for (offset,source,_),tile in zip(PROGRESS_ROW,progress_tiles(self.world)) if source!='icon']
            assert [(a,d) for a,d in writes if a in {a for a,_ in progress}]==progress,'ENTITY_PROGRESS_PUBLICATION'
            assert self.terminal is not None and self.lcd+PERIOD+65664<self.terminal<pause<self.lcd+2*PERIOD,'ENTITY_FINAL_WINDOW'
        return dict(pixels=self.pixels,records=self.records,lcd=self.lcd,ready=self.ready,
                    dma_bytes=len(self.dma),pause=pause,irq=self.irq,split=self.split,
                    terminal=self.terminal,bus_count=self.bus_count)


async def run(dut,short=False,variant='normal'):
    """Use the primary renderer's unchanged transport, sampling and settled END."""
    from pathlib import Path
    from startup_anchor import derive
    from hud_game_check import run as renderer_run
    lcd=derive(Path('program.gb').read_bytes(),lcdc_on=0x99)['lcd']
    await renderer_run(dut,short=short,renderer=True,
                       checker=Check(short,variant,lcd),expected_tiles=expected_tiles(),
                       renderer_bound=lcd+2*PERIOD)
