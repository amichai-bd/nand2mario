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
from interaction_cases import expected, ADDRESSES


async def run(dut, count):
    wants = expected()[:count]
    memory, reports = {}, []
    lines = records = last_retire = 0
    begin = elapsed = None
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
                    nonlocal lines, records, last_retire, begin, elapsed, terminal, ended
                    while True:
                        offset = trace.tell()
                        line = trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(offset)
                            return
                        assert not ended, 'FLOW_AFTER_END'
                        kind, raw = line.strip().split(' ')
                        if kind == 'END':
                            assert terminal and begin is None and elapsed is None, 'FLOW_END_PENDING'
                            assert int(raw) == lines, 'FLOW_END_COUNT'
                            ended = True
                            continue
                        widths = {'W': 22, 'R': 96, 'I': 26, 'P': 30}
                        assert kind in widths and len(raw) == widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()), 'FLOW_TRACE_UNKNOWN'
                        value = int(raw, 16)
                        lines += 1
                        assert kind not in ('I', 'P'), 'FLOW_UNIT_IO'
                        if kind == 'R':
                            row = decode_record(value)
                            assert row['seq'] == records and row['epoch'] == 2 and row['dot'] > last_retire, 'FLOW_RETIRE'
                            records += 1
                            last_retire = row['dot']
                            continue
                        assert not terminal, 'FLOW_WRITE_AFTER_TERMINAL'
                        dot, address, data = value >> 24, (value >> 8) & 65535, value & 255
                        memory[address] = data
                        if address == 0xc0ee:
                            assert begin is None and elapsed is None and data == len(reports) < count, 'FLOW_BEGIN'
                            begin = dot
                        elif address == 0xc0ef:
                            assert begin is not None and elapsed is None and data == len(reports), 'FLOW_CALL_END'
                            elapsed = dot-begin
                            assert 0 < elapsed < 20000, 'FLOW_CALL_BUDGET'
                            begin = None
                        elif address == 0xc0fe:
                            index = len(reports)
                            assert begin is None and elapsed is not None and data == index < count, 'FLOW_REPORT'
                            assert all(a in memory for a in ADDRESSES), 'FLOW_UNINITIALIZED'
                            actual = bytes(memory[a] for a in ADDRESSES).hex()
                            want = wants[index]
                            assert actual == want['state'], f'FLOW_STATE index={index} group={want["group"]} expected={want["state"]} actual={actual}'
                            reports.append(dict(index=index, dot=dot, routine_dots=elapsed, **want))
                            elapsed = None
                        elif address == 0xc0ff:
                            assert data == 165 and len(reports) == count and begin is None and elapsed is None, 'FLOW_TERMINAL'
                            terminal = True
                refresh_clock(client)
                await control('RUN')
                prior = 0
                while not terminal:
                    await Timer(50, unit='us')
                    await ReadOnly()
                    consume()
                    dot = known(dut.dot_count)
                    assert prior < dot < 600000 and not any(known(s) for s in (dut.fault, dut.reset_sys, dut.core_reset, dut.paused)), 'FLOW_PROGRESS'
                    prior = dot
                refresh_clock(client)
                await control('HALT')
                await Timer(1, unit='ns')
                assert known(dut.paused) and not known(dut.fault), 'FLOW_PAUSE'
                dut.public_trace_close.value = 1
                await Timer(100, unit='ns')
                consume()
                assert ended and len(reports) == count, 'FLOW_MISSING'
                result = dict(status='PASS', reports=reports, retirements=records, pause_dot=known(dut.dot_count))
                Path('summary.json').write_text(json.dumps(result, indent=2)+'\n')
                log('complete', **result)
        finally:
            receiver.cancel()
    dut._log.info('PASS SPRINGTRAIL flow cases=%d', count)
