"""Actual v0.5 HRAM DMA transfer, full CPU readback and bounded pixels."""
import json
from pathlib import Path
import sys
import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import FallingEdge, ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time

ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from test_integration import decode_record, known
from n2m.preload import adopt, verify


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def dma_system(dut):
    expected=json.loads(Path('dma239.json').read_text())
    assert expected['trigger']==4180 and len(expected['events'])==638
    received=Queue(); entries=[]; counts={'records':0,'pixels':0}; accesses=[]
    tasks=[]; armed=False; transfers=[]; stores=[]; phases=[]
    with Path('transactions.jsonl').open('w') as trace, Path('retirement.csv').open('w') as records, Path('pixels.csv').open('w') as pixels:
        records.write('seq,record\n');pixels.write('index,dot,shade\n')
        def log(kind,**fields):
            trace.write(json.dumps(dict(kind=kind,time_ps=int(get_sim_time(unit='ps')),**fields))+'\n');trace.flush()
        async def retirements():
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                raw=known(dut.record_sample);actual=decode_record(raw);index=counts['records']
                want=expected['events'][index] if index<len(expected['events']) else None
                records.write(f'{index},{raw:096x}\n');records.flush()
                log('retirement',expected=want,actual=actual)
                assert armed and actual==want,f'DMA239_RECORD index={index} expected={want} actual={actual}'
                counts['records']+=1
        async def bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);data=raw&255;write=(raw>>8)&1;address=(raw>>9)&65535;dot=raw>>25
                if address == 0xff46 or 0xfe00 <= address < 0xfea0:
                    accesses.append((dot,address,write,data));log('dma_bus',dot=dot,address=address,write=write,data=data)
        async def source():
            while True:
                await ValueChange(dut.pixel_event);await ReadOnly()
                raw=known(dut.pixel_sample);index=counts['pixels'];y,x=divmod(index,160)
                dot=expected['lcd_commit']+(93 if y==0 else 548+(y-1)*456)+x
                want=dict(dot=dot,x=x,y=y,shade=0,epoch=2,start=int(index==0),abort=0,eligible=0)
                actual=dict(dot=raw>>53,epoch=(raw>>21)&0xffffffff,x=(raw>>13)&255,y=(raw>>5)&255,
                    shade=(raw>>3)&3,start=(raw>>2)&1,abort=(raw>>1)&1,eligible=raw&1)
                log('pixel',expected=want,actual=actual);pixels.write(f'{index},{actual["dot"]},{actual["shade"]}\n')
                assert armed and actual==want,f'DMA239_PIXEL index={index} expected={want} actual={actual}'
                counts['pixels']+=1
        async def dma():
            while True:
                await ValueChange(dut.dma_event);await ReadOnly()
                raw=known(dut.dma_sample);dot=raw>>18
                if expected['trigger'] <= dot <= expected['last_transfer']+4:
                    age=(dot-expected['trigger'])//4
                    actual=dict(dot=dot,active=(raw>>17)&1,write=(raw>>16)&1,
                        offset=(raw>>8)&255,data=raw&255)
                    writing=2<=age<=161
                    want=dict(dot=expected['trigger']+age*4,active=int(writing),write=int(writing),
                        offset=age-2 if writing else 0,
                        data=expected['expected_oam'][age-2] if writing else 0)
                    log('dma_phase',expected=want,actual=actual);phases.append(actual)
                    assert actual==want,f'DMA239_PHASE expected={want} actual={actual}'
                    if writing:transfers.append(actual)
        async def physical():
            while True:
                await ValueChange(dut.oam_store_event);await ReadOnly()
                raw=known(dut.oam_store_sample);index=len(stores)
                actual=dict(dot=raw>>25,pair=(raw>>18)&127,enables=(raw>>16)&3,data=raw&65535)
                # DMA-only service commits one byte at system edge13 after its T4.
                # The two intervening emulated dots precede that system edge.
                want=dict(dot=expected['first_transfer']+4*index+2,pair=index//2,
                    enables=2 if index&1 else 1,data=expected['expected_oam'][index]*257)
                log('oam_store',expected=want,actual=actual);stores.append(actual)
                assert actual==want,f'DMA239_STORE index={index} expected={want} actual={actual}'
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        async def progress():
            await FallingEdge(dut.paused)
            prior=0
            while not known(dut.paused):
                await Timer(10,unit='us');await ReadOnly()
                current=known(dut.dot_count);log('progress',before=prior,actual=current)
                assert current>prior,'DMA239_PROGRESS'
                assert not known(dut.fault) and not known(dut.core_reset) and not known(dut.reset_sys),'DMA239_CONTINUITY'
                prior=current
        def checked():
            for task in tasks:
                if task.done():task.result()
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (retirements,bus,source,dma,physical,receiver,progress)]
        await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
        client=connect(dut,received,log,entries)
        @bridge
        def load():
            identity=client.identify();prepared=verify(Path.cwd())
            assert prepared['image_sha256']==expected['sha256']
            return identity,adopt(client,prepared)
        identity,loaded=await load();log('adopted',identity=identity,loaded=loaded)
        assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
        armed=True
        @bridge
        def command(action):return client.control(action)
        async def control(action):
            refresh_clock(client)
            return await command(action)
        await control('RUN')
        while known(dut.dot_count)<expected['lcd_commit']+1200:
            await Timer(1,unit='us');checked()
        await control('HALT');await Timer(1,unit='ns');await ReadOnly();checked()
        assert known(dut.paused) and known(dut.dot_count)>=expected['lcd_commit']+1200 and not known(dut.fault)
        assert counts['records']==638 and counts['pixels']>=320,counts
        want=[(4180,0xff46,1,0xc0),(5012,0xff46,0,0xc0)]
        want += [(r['dot'],r['address'],0,r['value']) for r in expected['readbacks']]
        assert len(transfers)==160 and len(stores)==160 and len(phases)==163
        assert accesses==want,f'DMA239_BUS expected={want} actual={accesses}'
        summary=dict(status='PASS',transfers=len(transfers),physical_writes=len(stores),phases=len(phases),counts=counts,paused_dot=known(dut.dot_count),preload=loaded)
        Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        log('complete',**summary)
        for task in tasks:task.cancel()
    dut._log.info('PASS DMA239 actual-v05 records=638 bytes=160')
