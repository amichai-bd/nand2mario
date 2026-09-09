"""Continuous game proof, including actual VBlank-to-last-write timing."""
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
from game_check import Check, INPUT_WINDOW, END, FRAMES


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def game(dut):
    check = Check()
    received = Queue()
    lines = records = last_retire = 0
    ended = sent = False
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
        @bridge
        def start():
            return client.control('INPUT', 128)
        try:
            identity, loaded = await load()
            log('load', identity=identity, loaded=loaded)
            assert (known(dut.epoch), known(dut.dot_count), known(dut.paused)) == (2, 0, 1)
            with Path('stackdrop.trace').open() as trace:
                def consume():
                    nonlocal lines, records, last_retire, ended
                    while True:
                        position = trace.tell()
                        line = trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(position)
                            return
                        assert not ended, 'STACKDROP_AFTER_END'
                        kind, raw = line.strip().split(' ')
                        if kind == 'END':
                            assert int(raw) == lines, 'STACKDROP_TRACE_COUNT'
                            ended = True
                            continue
                        widths = {'W': 22, 'R': 96, 'I': 26, 'P': 30}
                        assert kind in widths and len(raw) == widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()), 'STACKDROP_TRACE_UNKNOWN'
                        value = int(raw, 16)
                        lines += 1
                        if kind == 'W':
                            check.write(value)
                        elif kind == 'P':
                            check.pixel(value)
                        elif kind == 'I':
                            check.input(value)
                        else:
                            row = decode_record(value)
                            assert row['seq'] == records and row['epoch'] == 2 and row['dot'] > last_retire, 'STACKDROP_RETIRE'
                            records += 1
                            last_retire = row['dot']
                refresh_clock(client)
                await control('RUN')
                prior = 0
                while known(dut.dot_count) < END:
                    await Timer(50, unit='us')
                    await ReadOnly()
                    consume()
                    dot = known(dut.dot_count)
                    assert dot > prior and not any(known(s) for s in (dut.fault, dut.reset_sys, dut.core_reset, dut.paused)), 'STACKDROP_PROGRESS'
                    prior = dot
                    if not sent and dot >= INPUT_WINDOW[0]:
                        refresh_clock(client)
                        applied = await start()
                        log('start_ack', applied=applied)
                        sent = True
                refresh_clock(client)
                await control('HALT')
                await Timer(1, unit='ns')
                assert known(dut.paused) and not known(dut.fault), 'STACKDROP_PAUSE'
                dut.public_trace_close.value = 1
                await Timer(100, unit='ns')
                consume()
                assert ended, 'STACKDROP_MISSING_END'
                result = dict(check.finish(known(dut.dot_count)), retirements=records)
                Path('summary.json').write_text(json.dumps(result, indent=2)+'\n')
                # These are checked complete expected images; the retained raw
                # trace carries every actual pixel used by the comparison.
                for index, frame in enumerate(FRAMES):
                    Path(f'checked-frame-{index}.shades').write_bytes(frame)
                log('complete', **result)
        finally:
            receiver.cancel()
    dut._log.info('PASS STACKDROP game title start frame timing')
