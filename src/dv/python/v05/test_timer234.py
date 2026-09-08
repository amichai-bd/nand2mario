"""Actual v0.5 timer routing, HALT wake and bounded source-pixel proof."""
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
async def timer_system(dut):
    expected=json.loads(Path('timer234.json').read_text())
    assert expected['anchor']==536 and len(expected['events'])==110
    received=Queue(); entries=[]; counts={'records':0,'pixels':0}; accesses=[]
    tasks=[]; armed=False
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
                assert armed and actual==want,f'TIMER234_RECORD index={index} expected={want} actual={actual}'
                counts['records']+=1
        async def bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);data=raw&255;write=(raw>>8)&1;address=(raw>>9)&65535;dot=raw>>25
                if address in (0xff04,0xff05,0xff06,0xff07,0xc010):
                    accesses.append((dot,address,write,data));log('timer_bus',dot=dot,address=address,write=write,data=data)
        async def source():
            while True:
                await ValueChange(dut.pixel_event);await ReadOnly()
                raw=known(dut.pixel_sample);index=counts['pixels'];y,x=divmod(index,160)
                dot=1712+(93 if y==0 else 548+(y-1)*456)+x
                want=dict(dot=dot,x=x,y=y,shade=0,epoch=2,start=int(index==0),abort=0,eligible=0)
                actual=dict(dot=raw>>53,epoch=(raw>>21)&0xffffffff,x=(raw>>13)&255,y=(raw>>5)&255,
                    shade=(raw>>3)&3,start=(raw>>2)&1,abort=(raw>>1)&1,eligible=raw&1)
                log('pixel',expected=want,actual=actual);pixels.write(f'{index},{actual["dot"]},{actual["shade"]}\n')
                assert armed and actual==want,f'TIMER234_PIXEL index={index} expected={want} actual={actual}'
                counts['pixels']+=1
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        async def progress():
            await FallingEdge(dut.paused)
            prior=0
            while not known(dut.paused):
                await Timer(10,unit='us');await ReadOnly()
                current=known(dut.dot_count);log('progress',before=prior,actual=current)
                assert current>prior,'TIMER234_PROGRESS'
                assert not known(dut.fault) and not known(dut.core_reset) and not known(dut.reset_sys),'TIMER234_CONTINUITY'
                prior=current
        def checked():
            for task in tasks:
                if task.done():task.result()
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(fn()) for fn in (retirements,bus,source,receiver,progress)]
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
        while known(dut.dot_count)<3000:
            await Timer(1,unit='us');checked()
        await control('HALT');await Timer(1,unit='ns');await ReadOnly();checked()
        assert known(dut.paused) and known(dut.dot_count)>=3000 and not known(dut.fault)
        assert counts['records']==110 and counts['pixels']>=320,counts
        want=[(320,0xff04,0,1),(336,0xff04,1,0),(348,0xff04,0,0),
            (368,0xff05,1,0x3c),(380,0xff05,0,0x3c),(400,0xff06,1,0x42),
            (412,0xff06,0,0x42),(428,0xff07,1,0),(440,0xff07,0,0xf8),
            (500,0xff05,1,255),(520,0xff07,1,4),(536,0xff04,1,0),
            (1608,0xc010,1,0x7b),(1644,0xff07,1,0),(1656,0xff05,0,0x42),(1672,0xc010,0,0x7b)]
        assert accesses==want,f'TIMER234_BUS expected={want} actual={accesses}'
        summary=dict(status='PASS',counts=counts,paused_dot=known(dut.dot_count),preload=loaded)
        Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        log('complete',**summary)
        for task in tasks:task.cancel()
    dut._log.info('PASS TIMER234 actual-v05 records=110 marker=7b')
