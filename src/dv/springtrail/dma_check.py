"""Shared publisher executed by the actual CPU and Intel storage path."""
import json
from pathlib import Path
import sys
import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer, ReadOnly, ValueChange

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from test_integration import known, decode_record
from n2m.preload import adopt,verify
from dma_reference import DMA


async def run(dut,short=False):
    check=DMA(1 if short else 2); received=Queue(); entries=[]; tasks=[]
    records=0; terminal=False
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind,**values):
            journal.write(json.dumps(dict(kind=kind,**values))+'\n');journal.flush()
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        async def bus():
            nonlocal terminal
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample)
                dot,address,write,data=raw>>25,(raw>>9)&65535,(raw>>8)&1,raw&255
                log('bus',dot=dot,address=address,write=write,data=data)
                check.bus(dot,address,write,data)
                if address==0xc0ff and write:
                    assert data==0xa5 and len(check.reports)==check.count,'OAM_TERMINAL'
                    terminal=True
        async def dma():
            while True:
                await ValueChange(dut.dma_event);await ReadOnly()
                raw=known(dut.dma_sample)
                if (raw>>16)&1:
                    dot,index,data=raw>>18,(raw>>8)&255,raw&255
                    log('transfer',dot=dot,index=index,data=data)
                    check.transfer(dot,index,data)
        async def retire():
            nonlocal records
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                row=decode_record(known(dut.record_sample));log('retire',row=row)
                assert row['seq']==records and row['epoch']==2 and not row['stopped'],'OAM_RETIRE'
                records+=1
                if check.triggers and check.triggers[-1]<=row['dot']<=check.triggers[-1]+644:
                    assert 0xff80<=row['pc_before']<0xff89,'OAM_HRAM'
        def healthy():
            for task in tasks:
                if task.done():task.result()
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(f()) for f in (receiver,bus,dma,retire)]
        try:
            await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
            client=connect(dut,received,log,entries)
            @bridge
            def load():return client.identify(),adopt(client,verify(Path.cwd()))
            identity,loaded=await load();log('load',identity=identity,loaded=loaded)
            @bridge
            def control(action):return client.control(action)
            refresh_clock(client);await control('RUN')
            prior=0
            while not terminal:
                await Timer(1,unit='us');await ReadOnly();healthy()
                dot=known(dut.dot_count)
                assert prior<dot<22000 and not known(dut.fault),'OAM_PROGRESS'
                prior=dot
            refresh_clock(client);await control('HALT')
            await Timer(1,unit='ns');await ReadOnly();healthy()
            assert known(dut.paused) and not known(dut.fault),'OAM_PAUSE'
            summary=check.finish();summary.update(pause=known(dut.dot_count),records=records)
            Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            log('complete',**summary)
        finally:
            for task in tasks:task.cancel()
    dut._log.info('PASS OAM_DMA publications=%d',check.count)
