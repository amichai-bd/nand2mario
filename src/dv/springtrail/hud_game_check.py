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
from hud_game_reference import Check


async def run(dut, short=False, renderer=False, motion=False):
    if motion and renderer:
        from motion_render_reference import Check
    elif motion:
        from motion_game_reference import Check
    elif renderer:
        from hud_render_reference import Check
    else:
        from hud_game_reference import Check
    if not motion and not renderer:
        from hud_game_reference import require_baseline_rom
        require_baseline_rom(Path('program.gb').read_bytes())
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
        async def cpu_bus():
            while True:
                await ValueChange(dut.bus_event);await ReadOnly()
                raw=known(dut.bus_sample);prior=check.bus_count;check.bus(raw)
                if check.bus_count!=prior:log("dma_cpu_bus",raw=raw)
        async def irq_sources():
            while True:
                await ValueChange(dut.irq_source_event);await ReadOnly()
                raw=known(dut.irq_source_sample);check.sources.append((raw>>2,raw&3));log('irq_source',raw=raw)
        def healthy():
            for task in tasks:
                if task.done():task.result()
        await Timer(1,unit='ns')
        tasks.append(cocotb.start_soon(receiver()))
        tasks.append(cocotb.start_soon(transfers()))
        tasks.append(cocotb.start_soon(cpu_bus()))
        tasks.append(cocotb.start_soon(irq_sources()))
        try:
            await Timer(320,unit='ns');dut.reset_sys.value=0;dut.reset_pix.value=0
            client=connect(dut,received,log,entries)
            @bridge
            def load():
                identity=client.identify();prepared=verify(Path.cwd())
                return identity,adopt(client,prepared)
            identity,loaded=await load();log('load',identity=identity,loaded=loaded)
            healthy()
            assert (known(dut.epoch),known(dut.dot_count),known(dut.paused))==(2,0,1)
            @bridge
            def control(action):return client.control(action)
            @bridge
            def start():return client.control('INPUT',129)
            with Path('springtrail.trace').open() as trace:
                def consume():
                    while True:
                        position=trace.tell();line=trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(position);break
                        check.line(line)
                refresh_clock(client);await control('RUN')
                sent=short or renderer;prior=0
                while True:
                    # Only the final DMA-to-HALT boundary needs finer polling.
                    await Timer(10 if not short and len(check.triggers)==3 else 50,unit='us')
                    await ReadOnly();healthy()
                    dot=known(dut.dot_count)
                    assert dot>prior and not any(known(s) for s in (dut.fault,dut.reset_sys,dut.core_reset,dut.paused)), 'SPRINGTRAIL_PROGRESS'
                    prior=dot;consume()
                    assert dot<(300000 if renderer else 310000),'HUD_WATCHDOG'
                    if check.lcd is not None:
                        if short and check.pixels>=160:break
                        if renderer and check.halted:break
                        if not renderer and not short and len(check.triggers)==3 and dot>check.triggers[-1]+644:break
                    if not sent and check.lcd is not None and dot>=check.lcd+60000:
                        assert dot<=check.lcd+62000,'HUD_INPUT_LATE'
                        refresh_clock(client);reply=await start();sent=True
                        # Generated INPUT reply contains the applied dot, not acknowledgement time.
                        check.input_dot=reply['dot']
                        log('start_ack',applied_dot=check.input_dot,ack_dot=known(dut.dot_count),buttons=129)
                        assert check.lcd+60000<=check.input_dot<=check.lcd+62000,'HUD_INPUT_WINDOW'
                refresh_clock(client);await control('HALT')
                await Timer(1,unit='ns');await ReadOnly();healthy()
                pause=known(dut.dot_count)
                assert known(dut.paused) and not any(known(s) for s in (dut.fault,dut.reset_sys,dut.core_reset)), 'SPRINGTRAIL_FINAL_PAUSE'
                before=(known(dut.record_sample),len(check.dma))
                await Timer(1,unit='us');await ReadOnly()
                healthy()
                assert (known(dut.dot_count),known(dut.record_sample),len(check.dma),known(dut.paused))==(pause,*before,1),'HUD_PAUSED_HOLD'
                assert not any(known(s) for s in (dut.fault,dut.reset_sys,dut.core_reset)),'HUD_PAUSED_FAULT'
                # Flush and validate the real END count only after the settled hold.
                await Timer(1,unit='ns');dut.public_trace_close.value=1
                await Timer(100,unit='ns');await ReadOnly();healthy();consume()
                rom=Path('program.gb').read_bytes()
                from hud_reference import CHARS,MAPS
                tile_bytes=rom[0xc00:0x10a0]+b''.join(rom[0x6000+MAPS['glyph-'+c]['pieces'][0]['tile']*16:0x6010+MAPS['glyph-'+c]['pieces'][0]['tile']*16] for c in CHARS)
                if motion:
                    tile_bytes += rom[0x6100:0x6140]
                summary=check.finish(pause,tile_bytes)
                for frame,data in enumerate(check.frames):Path(f'frame-{frame}.shades').write_bytes(data)
                Path('summary.json').write_text(json.dumps(summary,indent=2)+'\n')
                log('complete',**summary)
        finally:
            for task in tasks:task.cancel()
    dut._log.info('PASS HUD game complete')
