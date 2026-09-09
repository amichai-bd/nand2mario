"""Continuous composed display proof using fixed source coordinates and owners."""
import json
from pathlib import Path
import sys
import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import FallingEdge, ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from test_integration import decode_record, known
from n2m.preload import adopt, verify
from scene import OBJECTS, shade


async def run(dut,short=False):
    plan=json.loads(Path('display308.json').read_text())
    rom=Path('program.gb').read_bytes(); lcd=plan['lcd_commit']
    oam=[value for top,left,tile,flags in OBJECTS for value in (top+16,left+8,tile,flags)]+[0]*140
    assert plan['expected_oam']==oam and lcd==11640,'DISPLAY308_FIXTURE'
    stop=plan['short_end' if short else 'end']
    source_requests=[(lcd+6839,2),(lcd+65662,1),(lcd+70224+6839,2)]
    received=Queue();entries=[];tasks=[];counts={'pixels':0,'records':0}
    requests=[];interrupts=[];writes=[];dma=[];stores=[];halts=[];returns=[]
    trigger=None;armed=False
    with Path('transactions.jsonl').open('w') as log_file, Path('pixels.csv').open('w') as pixels:
        pixels.write('index,dot,shade\n')
        def log(kind,**fields):
            log_file.write(json.dumps(dict(kind=kind,time_ps=int(get_sim_time(unit='ps')),**fields))+'\n')
            log_file.flush()
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        async def source():
            while True:
                await ValueChange(dut.pixel_event);await ReadOnly()
                raw=known(dut.pixel_sample);index=counts['pixels'];frame,offset=divmod(index,23040)
                y,x=divmod(offset,160)
                actual=dict(dot=raw>>53,epoch=(raw>>21)&0xffffffff,x=(raw>>13)&255,y=(raw>>5)&255,
                    shade=(raw>>3)&3,start=(raw>>2)&1,abort=(raw>>1)&1,eligible=raw&1)
                expected=dict(epoch=2,x=x,y=y,shade=shade(x,y,blank=frame==0),start=int(offset==0),abort=0,eligible=int(frame>0))
                assert armed and frame<=1 and {k:actual[k] for k in expected}==expected, f'DISPLAY308_PIXEL index={index} expected={expected} actual={actual}'
                pixels.write(f'{index},{actual["dot"]},{actual["shade"]}\n')
                counts['pixels']+=1
        async def irq():
            while True:
                await ValueChange(dut.irq_source_event);await ReadOnly()
                raw=known(dut.irq_source_sample);actual=(raw>>2,raw&3)
                expected=source_requests[len(requests)] if len(requests)<3 else None
                log('irq_source',expected=expected,actual=actual)
                assert actual==expected,f'DISPLAY308_IRQ_BOUNDARY expected={expected} actual={actual}'
                requests.append(actual)
        async def records():
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                r=decode_record(known(dut.record_sample));counts['records']+=1
                assert armed and r['epoch']==2 and not r['stopped'],'DISPLAY308_RECORD_STATE'
                if r['kind']==1:
                    i=len(interrupts);vector=(0x48,0x40,0x48)[i] if i<3 else -1
                    request=source_requests[i][0] if i<3 else -100
                    assert r['pc_after']==vector and 20<=r['dot']-request<=28, f'DISPLAY308_IRQ_ENTRY {r}'
                    assert halts and (not interrupts or halts[-1]>interrupts[-1]['dot']),'DISPLAY308_IRQ_NOT_HALTED'
                    interrupts.append(r);log('irq_entry',actual=r)
                else:
                    pc=r['pc_before'];length=r['opcode_length']
                    image=bytes.fromhex(plan['hram_hex']) if 0xff80<=pc<0xff89 else rom
                    offset=pc-0xff80 if image is not rom else pc
                    expected=int.from_bytes(image[offset:offset+length],'little')
                    assert r['opcode']==expected,f'DISPLAY308_OPCODE pc={pc:04x} expected={expected} actual={r}'
                    if trigger is not None and trigger<=r['dot']<=trigger+644:
                        assert 0xff80<=pc<0xff89,'DISPLAY308_DMA_CPU_NOT_HRAM'
                    if r['halted']:
                        assert pc==plan['halt_pc'],'DISPLAY308_HALT_PC'
                        halts.append(r['dot'])
                    if r['opcode']==0xd9:
                        assert r['sp']==0xfffe and r['ime']==1,'DISPLAY308_RETI_STATE'
                        returns.append(r);log('reti',actual=r)
        async def bus():
            nonlocal trigger
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);data=raw&255;write=(raw>>8)&1;address=(raw>>9)&65535;dot=raw>>25
                if address in (0xff40,0xff41,0xff42,0xff43,0xff45,0xff46):
                    log('bus',dot=dot,address=address,write=write,data=data)
                if write and address==0xff40 and data==0x93:
                    assert dot==lcd,'DISPLAY308_LCD_ORIGIN'
                if dot>lcd and write and address in (0xff42,0xff43):
                    writes.append((dot,address,data))
                    if data==8:
                        frame=0 if dot<lcd+70224 else 1
                        base=lcd+frame*70224+15*456
                        assert base+280<=dot<=base+352,f'DISPLAY308_SCROLL_BOUNDARY dot={dot} base={base}'
                    else:
                        assert data==0 and lcd+65662<dot<lcd+70224,'DISPLAY308_SCROLL_RESET'
                if write and address==0xff46:
                    assert trigger is None and data==0xc0 and lcd+65662<dot<lcd+67000,'DISPLAY308_DMA_TRIGGER'
                    trigger=dot;log('dma_trigger',dot=dot)
                if trigger is not None and trigger+8<=dot<=trigger+644:
                    assert 0xff80<=address<=0xfffe,'DISPLAY308_DMA_BUS_NOT_HRAM'
        async def transfer():
            while True:
                await ValueChange(dut.dma_event);await ReadOnly()
                raw=known(dut.dma_sample)
                if not (raw>>16)&1:continue
                index=len(dma);actual=(raw>>18,(raw>>8)&255,raw&255)
                expected=(trigger+8+4*index,index,oam[index]) if trigger is not None and index<160 else None
                assert actual==expected,f'DISPLAY308_DMA_BYTE expected={expected} actual={actual}'
                dma.append(actual);log('dma_byte',expected=expected,actual=actual)
        async def physical():
            while True:
                await ValueChange(dut.oam_store_event);await ReadOnly()
                raw=known(dut.oam_store_sample);i=len(stores)
                actual=(raw>>25,(raw>>18)&127,(raw>>16)&3,raw&65535)
                expected=(trigger+10+4*i,i//2,2 if i&1 else 1,oam[i]*257) if trigger is not None and i<160 else None
                assert actual==expected,f'DISPLAY308_DMA_STORE expected={expected} actual={actual}'
                stores.append(actual);log('dma_store',expected=expected,actual=actual)
        async def progress():
            await FallingEdge(dut.paused);prior=0
            while not known(dut.paused):
                await Timer(10,unit='us');await ReadOnly()
                current=known(dut.dot_count)
                assert current>prior and not known(dut.fault) and not known(dut.core_reset),'DISPLAY308_PROGRESS'
                if current//4096!=prior//4096:log('progress',dot=current,pixels=counts['pixels'])
                # A missing request fails near its boundary, not the wall watchdog.
                for i,(dot,_) in enumerate(source_requests):
                    if current>dot+32:assert len(requests)>i,f'DISPLAY308_IRQ_BOUNDARY missing={dot} actual={requests}'
                prior=current
        def check_tasks():
            for task in tasks:
                if task.done():task.result()
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (receiver,source,irq,records,bus,transfer,physical,progress)]
        try:
            await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
            client=connect(dut,received,log,entries)
            @bridge
            def load():
                identity=client.identify();prepared=verify(Path.cwd())
                assert prepared['image_sha256']==plan['sha256'],'DISPLAY308_ROM'
                return identity,adopt(client,prepared)
            identity,loaded=await load();log('adopted',identity=identity,loaded=loaded)
            assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
            armed=True
            @bridge
            def command(action):return client.control(action)
            refresh_clock(client);await command('RUN')
            while known(dut.dot_count)<stop:
                await Timer(1,unit='us');check_tasks()
            refresh_clock(client);await command('HALT')
            await Timer(1,unit='ns');await ReadOnly();check_tasks()
            final=known(dut.dot_count)
            assert known(dut.paused) and stop<=final<=stop+1024 and not known(dut.fault),'DISPLAY308_PAUSE'
            await Timer(1,unit='us');await ReadOnly();check_tasks()
            assert known(dut.dot_count)==final,'DISPLAY308_PAUSED_HOLD'
            if short:
                assert not requests and not dma and counts['pixels']>=320 and len(halts)==1,'DISPLAY308_SHORT_COMPLETION'
            else:
                assert len(requests)==len(interrupts)==len(returns)==3 and len(dma)==len(stores)==160,'DISPLAY308_COMPLETION'
                assert counts['pixels']>=23040+5120,'DISPLAY308_PIXEL_COUNT'
                assert [(a,d) for _,a,d in writes]==[(0xff43,8),(0xff42,8),(0xff43,0),(0xff42,0),(0xff43,8),(0xff42,8)],'DISPLAY308_WRITE_ORDER'
            summary=dict(status='PASS',short=short,counts=counts,requests=requests,interrupts=interrupts,
                returns=returns,writes=writes,dma_bytes=len(dma),physical_stores=len(stores),paused_dot=final,preload=loaded)
            Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n');log('complete',**summary)
        finally:
            for task in tasks:task.cancel()
    dut._log.info('PASS DISPLAY308 complete')
