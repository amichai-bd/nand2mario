"""Continuous actual-system title/Start/world proof with passive public trace."""
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
from test_integration import known
from n2m.preload import verify, adopt
from composition_game_reference import Check, PERIOD


async def run(dut, short=False):
    received=Queue(); entries=[]; check=Check(short); tasks=[]
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind,**fields):
            journal.write(json.dumps(dict(kind=kind,**fields))+'\n');journal.flush()
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        async def transfers():
            while True:
                await ValueChange(dut.dma_event);await ReadOnly()
                raw=known(dut.dma_sample)
                if (raw>>16)&1:
                    check.dma.append(raw);log('dma',raw=raw)
        await Timer(1,unit='ns')
        tasks.append(cocotb.start_soon(receiver()))
        tasks.append(cocotb.start_soon(transfers()))
        await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
        client=connect(dut,received,log,entries)
        @bridge
        def load():
            identity=client.identify();prepared=verify(Path.cwd())
            return identity,adopt(client,prepared)
        identity,loaded=await load();log('load',identity=identity,loaded=loaded)
        assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
        @bridge
        def control(action):return client.control(action)
        @bridge
        def start():return client.control('INPUT',129)
        try:
            with Path('springtrail.trace').open() as trace:
                def consume():
                    while True:
                        position=trace.tell();line=trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(position);break
                        check.line(line)
                refresh_clock(client);await control('RUN')
                sent=short;prior=0
                while True:
                    await Timer(50,unit='us');await ReadOnly()
                    dot=known(dut.dot_count)
                    assert dot>prior and not any(known(s) for s in (dut.fault,dut.reset_sys,dut.core_reset,dut.paused)), 'SPRINGTRAIL_PROGRESS'
                    prior=dot;consume()
                    assert dot<285000,'COMPOSITION_WATCHDOG'
                    if check.lcd is not None:
                        if short and check.pixels>=160:break
                        if not short and len(check.triggers)==3 and dot>check.triggers[-1]+644:break
                    if not sent and check.lcd is not None and dot>=check.lcd+60000:
                        refresh_clock(client);reply=await start();sent=True
                        check.input_dot=reply['dot']
                        log('start_ack',dot=known(dut.dot_count))
                refresh_clock(client);await control('HALT')
                await Timer(1,unit='ns');await ReadOnly()
                pause=known(dut.dot_count)
                assert known(dut.paused) and not known(dut.fault), 'SPRINGTRAIL_FINAL_PAUSE'
                await Timer(1,unit='ns');dut.public_trace_close.value=1
                await Timer(100,unit='ns');consume()
                before=known(dut.record_sample)
                await Timer(1,unit='us');await ReadOnly()
                assert (known(dut.dot_count),known(dut.record_sample),known(dut.paused))==(pause,before,1),'COMPOSITION_PAUSED_HOLD'
                summary=check.finish(pause,Path('program.gb').read_bytes()[0xc00:0x10a0])
                for frame,data in enumerate(check.frames):Path(f'frame-{frame}.shades').write_bytes(data)
                Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
                log('complete',**summary)
        finally:
            for task in tasks:task.cancel()
    dut._log.info('PASS COMPOSITION game complete')
