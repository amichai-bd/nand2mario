"""Continuous actual-system title/Start/world proof with passive public trace."""
import json
from pathlib import Path
import sys
import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer, ReadOnly

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'tools'),str(ROOT/'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from test_integration import known
from n2m.preload import verify, adopt
from game_reference import Check, START_WINDOW, END


@cocotb.test(timeout_time=90, timeout_unit='ms')
async def movement_game(dut):
    received=Queue(); entries=[]; check=Check(); tasks=[]
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind,**fields):
            journal.write(json.dumps(dict(kind=kind,**fields))+'\n');journal.flush()
        async def receiver():
            async for frame in frames(dut):received.put_nowait(frame)
        await Timer(1,unit='ns')
        tasks.append(cocotb.start_soon(receiver()))
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
                sent=False;prior=0
                while known(dut.dot_count)<END:
                    await Timer(50,unit='us');await ReadOnly()
                    dot=known(dut.dot_count)
                    assert dot>prior and not any(known(s) for s in (dut.fault,dut.reset_sys,dut.core_reset,dut.paused)), 'SPRINGTRAIL_PROGRESS'
                    prior=dot;consume()
                    if not sent and dot>=START_WINDOW[0]:
                        refresh_clock(client);await start();sent=True
                        log('start_ack',dot=known(dut.dot_count))
                refresh_clock(client);await control('HALT')
                await Timer(1,unit='ns');await ReadOnly()
                pause=known(dut.dot_count)
                assert known(dut.paused) and not known(dut.fault), 'SPRINGTRAIL_FINAL_PAUSE'
                await Timer(1,unit='ns');dut.public_trace_close.value=1
                await Timer(100,unit='ns');consume()
                summary=check.finish(pause)
                for frame,data in enumerate(check.frames):Path(f'frame-{frame}.shades').write_bytes(data)
                Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
                log('complete',**summary)
        finally:
            for task in tasks:task.cancel()
    dut._log.info('PASS SPRINGTRAIL movement title start world')
