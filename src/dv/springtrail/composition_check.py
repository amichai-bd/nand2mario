"""Check actual composer writes against fixed operands and approved source pixels."""
import json
from pathlib import Path
import sys
import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer,ReadOnly,ValueChange
from composition_cases import cases,expected
from interaction_cases import ADDRESSES,state_bytes
from interactions_reference import update

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/dv/python/integration')]
from client_transport import connect,frames,refresh_clock
from test_integration import known,decode_record
from n2m.preload import adopt,verify


async def run(dut,short=False):
    selected=cases()[:1] if short else cases()
    memory={}; active=None; reports=[]; writes=[]; durations=[]
    terminal=False; records=0; halted=False; tasks=[]; received=Queue()
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind,**values):
            journal.write(json.dumps(dict(kind=kind,**values))+'\n');journal.flush()
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        async def bus():
            nonlocal active,terminal,writes
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample)
                dot,address,write,data=raw>>25,(raw>>9)&65535,(raw>>8)&1,raw&255
                if not write:continue
                log('write',dot=dot,address=address,data=data)
                assert not terminal,'COURIER_AFTER_TERMINAL'
                if address==0xc0fc:
                    assert active is None and data==len(reports)+1 and data<=len(selected),'COURIER_BEGIN'
                    active=dot;writes=[]
                    case=selected[data-1]
                    if case['kind']!='courier':
                        actual=bytes(memory.get(a,0) for a in ADDRESSES)
                        assert actual==state_bytes(update(case['game'],case['buttons']) if case['kind']=='game' else case['game'],case['buttons']),'COURIER_GAME_STATE'
                elif address==0xc0fd:
                    assert active is not None and data==len(reports)+1,'COURIER_REPORT'
                    wants=expected(selected[data-1])
                    assert writes==list(enumerate(wants)),f'COURIER_PIECES case={data} actual={writes} expected={wants.hex()}'
                    durations.append(dot-active);reports.append(dot);active=None
                elif address==0xc0ff:
                    assert data==0xa5 and active is None and len(reports)==len(selected),'COURIER_TERMINAL'
                    terminal=True
                elif active is not None:
                    assert address not in ADDRESSES,'COURIER_GAME_MUTATION'
                    if 0xc100<=address<0xc1a0:writes.append((address-0xc100,data))
                memory[address]=data
        async def retire():
            nonlocal records,halted
            while True:
                await ValueChange(dut.record_event);await ReadOnly()
                row=decode_record(known(dut.record_sample))
                assert row['seq']==records and row['epoch']==2 and not row['stopped'],'COURIER_RETIRE'
                records+=1
                if row['opcode']==0x76:
                    assert terminal,'COURIER_EARLY_HALT'
                    halted=True
                    log('halt',row=row)
        def healthy():
            for task in tasks:
                if task.done():task.result()
        await Timer(1,unit='ns')
        tasks=[cocotb.start_soon(f()) for f in (receiver,bus,retire)]
        try:
            await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
            client=connect(dut,received,log,[])
            @bridge
            def load():return client.identify(),adopt(client,verify(Path.cwd()))
            identity,loaded=await load();log('load',identity=identity,loaded=loaded)
            @bridge
            def control(action):return client.control(action)
            refresh_clock(client);await control('RUN')
            prior=0
            while not halted:
                await Timer(2,unit='us');await ReadOnly();healthy()
                dot=known(dut.dot_count)
                assert prior<dot<(10000 if short else 220000) and not known(dut.fault),'COURIER_PROGRESS'
                prior=dot
            refresh_clock(client);await control('HALT')
            await Timer(1,unit='ns');await ReadOnly();healthy()
            assert known(dut.paused) and not known(dut.fault),'COURIER_PAUSE'
            settled=(known(dut.dot_count),records)
            await Timer(1,unit='us');await ReadOnly();healthy()
            assert (known(dut.dot_count),records)==settled and known(dut.paused),'COURIER_HOLD'
            summary=dict(cases=len(reports),durations=durations,pause=settled[0],records=records)
            Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
            log('complete',**summary)
        finally:
            for task in tasks:task.cancel()
    dut._log.info('PASS COURIER complete')
