"""Bounded CPU proof through the existing public write/retirement trace."""
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
from cases import expected


async def run(dut, count):
    wants = expected()[:count]
    memory, reports, vram = {}, [], []
    lines = records = last_retire = 0
    begin = render_begin = None
    routine_dots = render_dots = None
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
            with Path('stackdrop.trace').open() as trace:
                def read_bytes(address, size):
                    assert all(address+i in memory for i in range(size)), 'STACKDROP_UNKNOWN_MEMORY'
                    return bytes(memory[address+i] for i in range(size))
                def consume():
                    nonlocal lines, records, last_retire, begin, render_begin
                    nonlocal routine_dots, render_dots, terminal, ended, vram
                    while True:
                        offset = trace.tell()
                        line = trace.readline()
                        if not line or not line.endswith('\n'):
                            trace.seek(offset)
                            return
                        assert not ended, 'STACKDROP_AFTER_END'
                        kind, raw = line.strip().split(' ')
                        if kind == 'END':
                            assert int(raw) == lines and terminal and begin is None and render_begin is None and routine_dots is None and render_dots is None and not vram, 'STACKDROP_END'
                            ended = True
                            continue
                        widths = {'W': 22, 'R': 96, 'I': 26, 'P': 30}
                        assert kind in widths and len(raw) == widths[kind] and all(c in '0123456789abcdef' for c in raw.lower()), 'STACKDROP_TRACE_UNKNOWN'
                        value = int(raw, 16)
                        lines += 1
                        assert kind not in ('I', 'P'), 'STACKDROP_UNIT_IO'
                        if kind == 'R':
                            row = decode_record(value)
                            assert row['seq'] == records and row['epoch'] == 2 and row['dot'] > last_retire, 'STACKDROP_RETIRE'
                            records += 1
                            last_retire = row['dot']
                            continue
                        dot, address, data = value >> 24, (value >> 8) & 65535, value & 255
                        assert not terminal, 'STACKDROP_WRITE_AFTER_TERMINAL'
                        if 0xc000 <= address < 0xc300:
                            memory[address] = data
                        if 0x9800 <= address < 0x9c00:
                            assert render_begin is not None, 'STACKDROP_UNEXPECTED_RENDER'
                            vram.append((address, data))
                        if address == 0xc0ee:
                            assert begin is None and routine_dots is None and data == len(reports) < count, 'STACKDROP_BEGIN'
                            begin = dot
                        elif address == 0xc0ef:
                            assert begin is not None and data == len(reports), 'STACKDROP_FINISH_CALL'
                            routine_dots = dot-begin
                            assert 0 < routine_dots <= 42000, 'STACKDROP_UPDATE_BUDGET'
                            begin = None
                        elif address == 0xc0f1:
                            assert render_begin is None and not vram, 'STACKDROP_RENDER_BEGIN'
                            render_begin = dot
                        elif address == 0xc0f2:
                            assert render_begin is not None, 'STACKDROP_RENDER_END'
                            render_dots = dot-render_begin
                            assert render_dots == 4496, f'STACKDROP_RENDER_TIME {render_dots}'
                            render_begin = None
                        elif address == 0xc0fe:
                            index = len(reports)
                            assert data == index < count and begin is None and routine_dots is not None, 'STACKDROP_CHECKPOINT'
                            want = wants[index]
                            for field, address, size in (('state', 0xc000, 7), ('score', 0xc009, 4), ('board', 0xc100, 96)):
                                actual = read_bytes(address, size)
                                assert actual == want[field], f'STACKDROP_{field.upper()} index={index} expected={want[field].hex()} actual={actual.hex()}'
                            if want['prepare']:
                                actual = read_bytes(0xc200, 118)
                                assert actual == want['image'], f'STACKDROP_IMAGE index={index} expected={want["image"].hex()} actual={actual.hex()}'
                            if want['render']:
                                addresses = [0x9866+y*32+x for y in range(12) for x in range(8)]
                                addresses += [0x988f+y*32+x for y in range(4) for x in range(4)]
                                addresses += list(range(0x9a08, 0x9a0c))+[0x9844, 0x9864]
                                assert vram == list(zip(addresses, want['image'])), 'STACKDROP_VRAM'
                                assert render_dots == 4496, 'STACKDROP_MISSING_RENDER'
                            else:
                                assert not vram and render_dots is None, 'STACKDROP_EXTRA_RENDER'
                            reports.append(dict(index=index, group=want['group'], dot=dot, update_dots=routine_dots, render_dots=render_dots))
                            routine_dots = render_dots = None
                            vram = []
                        elif address == 0xc0ff:
                            assert not terminal and data == 165 and len(reports) == count and begin is None and render_begin is None and routine_dots is None and render_dots is None and not vram, 'STACKDROP_TERMINAL'
                            terminal = True
                refresh_clock(client)
                await control('RUN')
                prior = 0
                while not terminal:
                    await Timer(50, unit='us')
                    await ReadOnly()
                    consume()
                    dot = known(dut.dot_count)
                    assert prior < dot < 500000 and not any(known(s) for s in (dut.fault, dut.reset_sys, dut.core_reset, dut.paused)), 'STACKDROP_PROGRESS'
                    prior = dot
                refresh_clock(client)
                await control('HALT')
                await Timer(1, unit='ns')
                assert known(dut.paused) and not known(dut.fault), 'STACKDROP_PAUSE'
                dut.public_trace_close.value = 1
                await Timer(100, unit='ns')
                consume()
                assert ended and len(reports) == count, 'STACKDROP_MISSING'
                summary = dict(status='PASS', reports=reports, retirements=records, pause_dot=known(dut.dot_count))
                Path('summary.json').write_text(json.dumps(summary, indent=2)+'\n')
                log('complete', **summary)
        finally:
            receiver.cancel()
    dut._log.info('PASS STACKDROP unit cases=%d', count)

