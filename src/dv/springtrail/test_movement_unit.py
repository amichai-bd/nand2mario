"""Original CPU unit ROM executes the exact linked gameplay routines."""
import json,sys
from pathlib import Path
import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer,ReadOnly

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/dv/python/integration')]
from client_transport import connect,frames,refresh_clock
from test_integration import known
from n2m.preload import verify,adopt
from unit_cases import expected,timing_marker,timing_report


@cocotb.test(timeout_time=90,timeout_unit='ms')
async def movement_unit(dut):
    wants=expected();reports=[];pending=[];writes=[];lines=0;ended=False;terminal=False;begin=None;elapsed=None
    received=Queue();entries=[]
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind,**fields):
            journal.write(json.dumps(dict(kind=kind,**fields))+'\n');journal.flush()
        async def receive():
            async for frame in frames(dut):received.put_nowait(frame)
        await Timer(1,unit='ns');receiver=cocotb.start_soon(receive())
        await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
        client=connect(dut,received,log,entries)
        @bridge
        def load():return client.identify(),adopt(client,verify(Path.cwd()))
        @bridge
        def control(action):return client.control(action)
        try:
            identity,loaded=await load();log('load',identity=identity,loaded=loaded)
            assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
            with Path('springtrail.trace').open() as trace:
                def consume():
                    nonlocal lines,ended,terminal,pending,writes,begin,elapsed
                    while True:
                        offset=trace.tell();line=trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(offset);break
                        assert not ended,'MOVEMENT_AFTER_END'
                        kind,raw=line.strip().split(' ')
                        if kind=='END':
                            assert int(raw)==lines,'MOVEMENT_TRACE_COUNT'
                            assert terminal and begin is None and elapsed is None and not pending and not writes,'MOVEMENT_END_PENDING'
                            ended=True;continue
                        widths={'W':22,'R':96,'I':26,'P':30}
                        assert kind in widths and len(raw)==widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()),'MOVEMENT_TRACE_UNKNOWN'
                        lines+=1
                        assert kind not in ('I','P'),'MOVEMENT_UNIT_UNEXPECTED_IO'
                        if kind!='W':continue
                        value=int(raw,16);address=(value>>8)&65535;data=value&255
                        if address in (0xc0ee,0xc0ef):
                            assert not terminal and len(reports)<len(wants),'MOVEMENT_EXTRA_CALL'
                            begin,elapsed=timing_marker(begin,elapsed,address,value>>24,data,wants[len(reports)]['buttons'])
                        elif address in (0xff43,0xfe00,0xfe01,0xfe02,0xfe03) or 0x9800<=address<0x9c00:
                            writes.append((address,data))
                        elif 0xc100<=address<=0xc10d:
                            timing_report(begin,elapsed)
                            assert address==0xc100+len(pending),'MOVEMENT_REPORT_ORDER'
                            pending.append(data)
                        elif address==0xc0f0:
                            timing_report(begin,elapsed)
                            index=len(reports)
                            assert data==index and index<len(wants),'MOVEMENT_REPORT_COUNT'
                            actual=bytes(pending).hex();want=wants[index]
                            assert actual==want['bytes'],f'MOVEMENT_STATE index={index} group={want["group"]} expected={want["bytes"]} actual={actual}'
                            assert writes==want['writes'],f'MOVEMENT_RENDER index={index} expected={want["writes"]} actual={writes}'
                            reports.append(dict(index=index,dot=value>>24,routine_dots=elapsed,**want));pending=[];writes=[];elapsed=None
                        elif address==0xc0ff:
                            assert not terminal and data==165 and len(reports)==len(wants),'MOVEMENT_TERMINAL'
                            assert begin is None and elapsed is None and not pending and not writes,'MOVEMENT_TERMINAL_PENDING'
                            terminal=True
                refresh_clock(client);await control('RUN');prior=0
                while not terminal:
                    await Timer(50,unit='us');await ReadOnly();consume()
                    dot=known(dut.dot_count)
                    assert prior<dot<300000 and not any(known(x) for x in (dut.fault,dut.reset_sys,dut.core_reset,dut.paused)),'MOVEMENT_UNIT_PROGRESS'
                    prior=dot
                refresh_clock(client);await control('HALT')
                await Timer(1,unit='ns');assert known(dut.paused) and not known(dut.fault)
                dut.public_trace_close.value=1;await Timer(100,unit='ns');consume()
                assert ended and begin is None and elapsed is None and not pending and not writes and len(reports)==85,'MOVEMENT_UNIT_MISSING'
                summary=dict(reports=reports,pause_dot=known(dut.dot_count),status='PASS')
                Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n');log('complete',**summary)
        finally:receiver.cancel()
    dut._log.info('PASS SPRINGTRAIL movement unit cases=85')
