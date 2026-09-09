"""Actual CPU flow proof through the existing passive public trace."""
import json
import sys
from pathlib import Path

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Timer, ReadOnly

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from test_integration import known, decode_record
from n2m.preload import verify, adopt
from renderer_oracle import Check


async def run(dut, count):
    checker = Check(count)
    lines = records = last_retire = 0
    terminal = ended = False
    received = Queue()
    with Path('transactions.jsonl').open('w') as journal:
        def log(kind, **fields):
            journal.write(json.dumps(dict(kind=kind, **fields))+'\n')
            journal.flush()
        async def receive():
            async for frame in frames(dut):
                received.put_nowait(frame)
        await Timer(1, unit='ns')
        receiver = cocotb.start_soon(receive())
        await Timer(320, unit='ns')
        dut.reset_sys.value = 0
        dut.reset_pix.value = 0
        client = connect(dut, received, log, [])
        @bridge
        def load():
            return client.identify(), adopt(client, verify(Path.cwd()))
        @bridge
        def control(action):
            return client.control(action)
        try:
            identity, loaded = await load()
            log('load', identity=identity, loaded=loaded)
            assert (known(dut.epoch), known(dut.dot_count), known(dut.paused)) == (2, 0, 1)
            with Path('springtrail.trace').open() as trace:
                def consume():
                    nonlocal lines, records, last_retire, terminal, ended
                    while True:
                        offset = trace.tell()
                        line = trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(offset)
                            return
                        assert not ended, 'RENDER_AFTER_END'
                        kind, raw = line.strip().split(' ')
                        if kind == 'END':
                            assert terminal, 'RENDER_END_PENDING'
                            assert int(raw) == lines, 'RENDER_END_COUNT'
                            ended = True
                            continue
                        widths = {'W': 22, 'R': 96, 'I': 26, 'P': 30}
                        assert kind in widths and len(raw) == widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()), 'RENDER_TRACE_UNKNOWN'
                        value = int(raw, 16)
                        lines += 1
                        assert kind not in ('I', 'P'), 'RENDER_UNIT_IO'
                        if kind == 'R':
                            row = decode_record(value)
                            assert row['seq'] == records and row['epoch'] == 2 and row['dot'] > last_retire, 'RENDER_RETIRE'
                            records += 1
                            last_retire = row['dot']
                            continue
                        assert not terminal, 'RENDER_WRITE_AFTER_TERMINAL'
                        dot, address, data = value >> 24, (value >> 8) & 65535, value & 255
                        checker.write(dot, address, data)
                        terminal = checker.terminal
                refresh_clock(client)
                await control('RUN')
                prior = 0
                while not terminal:
                    await Timer(50, unit='us')
                    await ReadOnly()
                    consume()
                    dot = known(dut.dot_count)
                    assert prior < dot < 600000 and not any(known(s) for s in (dut.fault, dut.reset_sys, dut.core_reset, dut.paused)), 'RENDER_PROGRESS'
                    prior = dot
                refresh_clock(client)
                await control('HALT')
                await Timer(1, unit='ns')
                assert known(dut.paused) and not known(dut.fault), 'RENDER_PAUSE'
                dut.public_trace_close.value = 1
                await Timer(100, unit='ns')
                consume()
                assert ended and len(checker.reports) == count, 'RENDER_MISSING'
                result = dict(status='PASS', reports=checker.reports, retirements=records, pause_dot=known(dut.dot_count))
                Path('summary.json').write_text(json.dumps(result, indent=2)+'\n')
                log('complete', **result)
        finally:
            receiver.cancel()
    dut._log.info('PASS SPRINGTRAIL renderer cases=%d', count)
