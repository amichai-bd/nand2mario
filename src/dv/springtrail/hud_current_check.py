"""Ordered public writes for current cache, HUD and column publication."""
from motion_unit_check import Check as TraceCheck, run as run_trace
from n2m.interface_codec import decode_record
from hud_current_cases import cases,parts,operands,expected,world,CANARIES
from entities_frames import scene

OUTPUTS={0xc023,0xc02f,0xc052,0xc053,0xc083,0xc08f,0xff40,0xff46}


def observed(address):
    return (address in OUTPUTS or 0xc097<=address<0xc09d or 0xc100<=address<0xc1a0
            or 0xc200<=address<0xc227 or 0xc400<=address<0xc4a0
            or 0x8000<=address<0xa000 or 0xfe00<=address<0xfea0)


class Check(TraceCheck):
    def __init__(self,short=False,part='a'):
        self.selected=cases()[:1] if short else parts()[part]
        self.short_bound=30000;self.full_bound=160000
        self.memory={};self.active=None;self.reports=[];self.durations=[]
        self.lines=0;self.records=0;self.last_dot=-1
        self.terminal=False;self.halted=False;self.ended=False
        self.writes=[];self.wants=[];self.triggers=[];self.dma=[]

    def write(self,dot,address,data):
        assert not self.terminal,'HUD_CURRENT_AFTER_TERMINAL'
        if address==0xc0fc:
            assert self.active is None and data==len(self.reports)+1 and data<=len(self.selected),'HUD_CURRENT_BEGIN'
            case=self.selected[data-1]
            self.before=operands(case)|{a:0xa5 for a in CANARIES}
            assert all(self.memory.get(a)==v for a,v in self.before.items()),'HUD_CURRENT_OPERANDS'
            self.wants=expected(case);self.writes=[];self.active=dot
        elif address==0xc0fd:
            assert self.active is not None and data==len(self.reports)+1,'HUD_CURRENT_REPORT'
            assert self.writes==self.wants,'HUD_CURRENT_MISSING_WRITE'
            after=self.before|dict(self.wants)
            assert all(self.memory.get(a)==v for a,v in after.items()),'HUD_CURRENT_PRESERVATION'
            duration=dot-self.active
            assert 0<duration<=(55000 if self.selected[data-1]['kind']=='scene' else 20000),'HUD_CURRENT_ROUTINE'
            self.durations.append(duration);self.reports.append(dict(name=self.selected[data-1]['name'],writes=len(self.writes),dot=dot))
            self.active=None
        elif address==0xc0ff:
            assert data==0xa5 and self.active is None and len(self.reports)==len(self.selected),'HUD_CURRENT_TERMINAL'
            self.terminal=True
        elif self.active is not None:
            if observed(address):
                i=len(self.writes)
                assert i<len(self.wants) and self.wants[i]==(address,data),f'HUD_CURRENT_WRITE case={self.selected[len(self.reports)]["name"]} index={i} actual={(address,data)} expected={self.wants[i:i+1]}'
                self.writes.append((address,data))
                if address==0xff46:self.triggers.append(dot)
            else:
                scratch=0xc08b<=address<=0xc08e or 0xdfe0<=address<0xdffe
                if self.selected[len(self.reports)]['kind']=='scene':
                    scratch|=0xc034<=address<0xc04c or 0xc338<=address<0xc350
                assert scratch,'HUD_CURRENT_UNRELATED_WRITE'
        self.memory[address]=data

    def line(self,text):
        if text.startswith('R ') and self.triggers:
            row=decode_record(int(text.split()[1],16))
            if self.triggers[-1]<=row['dot']<=self.triggers[-1]+644:
                assert 0xff80<=row['pc_before']<0xff89,'HUD_CURRENT_HRAM'
        super().line(text)

    def sample_dma(self,raw):
        assert not self.terminal,'HUD_CURRENT_LATE_DMA'
        self.dma.append(raw)

    def finish(self,pause):
        result=super().finish(pause)
        scenes=[c for c in self.selected if c['kind']=='scene']
        assert len(self.triggers)==len(scenes) and len(self.dma)==160*len(scenes),'HUD_CURRENT_DMA_COUNT'
        if scenes:
            wants=scene(world(scenes[0]))
            for i,raw in enumerate(self.dma):
                assert (raw>>18,(raw>>8)&255,raw&255)==(self.triggers[0]+8+4*i,i,wants[i]),'HUD_CURRENT_DMA_BYTE'
            assert pause>self.triggers[0]+644,'HUD_CURRENT_DMA_PENDING'
        return result|dict(dma_bytes=len(self.dma))


async def run(dut,short=False,part='a'):
    import cocotb
    from cocotb.triggers import ValueChange,ReadOnly
    check=Check(short,part)
    async def dma():
        while True:
            await ValueChange(dut.dma_event);await ReadOnly()
            raw=int(dut.dma_sample.value)
            if raw>>16&1:check.sample_dma(raw)
    task=cocotb.start_soon(dma())
    try:
        await run_trace(dut,short=short,checker=check)
        if task.done():task.result()
    finally:task.cancel()
