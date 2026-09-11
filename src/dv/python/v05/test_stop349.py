"""Composed STOP entry, stopped observation and joypad wake on the actual system."""
import json
from pathlib import Path
import sys

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from test_integration import decode_record, known
from n2m import generated_interfaces as abi
from n2m.preload import adopt, verify

# STOP withholds emulated ticks, so the sleeping window is measured in real
# simulated time, not dots: no dot may elapse in it. A quarter-millisecond is
# about a thousand dots of running time, far longer than any legitimate wake.
SLEEP_WINDOW_NS = 250000


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def stop_wake(dut):
    expected = json.loads(Path('stop349.json').read_text())
    events = expected['entry_events'] + expected['resumed_events']
    entry = expected['entry_events']
    assert len(events) == 11 and expected['stop_dot'] == 68 and expected['wake_dot'] == 80
    received = Queue()
    entries = []
    records = []
    writes = []
    inputs = []
    tasks = []
    armed = False
    with Path('transactions.jsonl').open('w') as trace, \
            Path('retirement.csv').open('w') as record_file:
        record_file.write('seq,record\n')

        def log(kind, **fields):
            trace.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit='ps')), **fields)) + '\n')
            trace.flush()

        async def retirements():
            while True:
                await ValueChange(dut.record_event)
                await ReadOnly()
                raw = known(dut.record_sample)
                actual = decode_record(raw)
                index = len(records)
                record_file.write(f'{index},{raw:096x}\n')
                record_file.flush()
                assert armed and index < len(events), f'STOP349_EXTRA_RECORD index={index}'
                want = events[index]
                log('retirement', index=index, expected=want, actual=actual)
                assert actual == want, f'STOP349_RECORD index={index} expected={want} actual={actual}'
                records.append(actual)

        async def bus():
            while True:
                await ValueChange(dut.bus_event)
                await ReadOnly()
                raw = known(dut.bus_sample)
                data, write, address, dot = raw & 255, (raw >> 8) & 1, (raw >> 9) & 65535, raw >> 25
                if write and address in (0xff00, 0xff40, expected['marker_address']):
                    writes.append((dot, address, data))
                    log('write', dot=dot, address=address, data=data)

        async def applied_input():
            while True:
                await ValueChange(dut.input_event)
                await ReadOnly()
                raw = known(dut.input_sample)
                item = dict(dot=(raw >> 8) & ((1 << 64) - 1), buttons=raw & 255)
                inputs.append(item)
                log('input', **item)

        async def receiver():
            async for frame in frames(dut):
                received.put_nowait(frame)

        def checked():
            for task in tasks:
                if task.done():
                    task.result()

        async def asleep(label):
            frozen = known(dut.dot_count)
            elapsed = 0
            while elapsed < SLEEP_WINDOW_NS:
                await Timer(1, unit='us')
                elapsed += 1000
                checked()
                assert not known(dut.fault), 'STOP349_FAULT'
                assert known(dut.dot_count) == frozen, f'STOP349_SLEEP_TICKS {label}'
                assert len(records) == len(entry), f'STOP349_SLEEP_RETIREMENT {label}'

        await Timer(1, unit='ns')
        tasks = [cocotb.start_soon(fn()) for fn in (retirements, bus, applied_input, receiver)]
        await Timer(320, unit='ns')
        dut.reset_sys.value = 0
        dut.reset_pix.value = 0
        client = connect(dut, received, log, entries)

        @bridge
        def load():
            identity = client.identify()
            prepared = verify(Path.cwd())
            assert prepared['image_sha256'] == expected['sha256'], 'STOP349_IMAGE'
            return identity, adopt(client, prepared)

        identity, loaded = await load()
        log('adopted', identity=identity, loaded=loaded)
        assert (known(dut.epoch), known(dut.dot_count), known(dut.paused)) == (2, 0, 1)
        armed = True

        @bridge
        def command(action, value=None):
            return client.control(action, value)

        async def control(action, value=None):
            refresh_clock(client)
            return await command(action, value)

        # 1. Run until the original program retires STOP.
        await control('RUN')
        elapsed = 0
        while len(records) < len(entry):
            await Timer(1, unit='us')
            elapsed += 1000
            checked()
            assert elapsed < SLEEP_WINDOW_NS, 'STOP349_ENTRY_DEADLINE'
        assert records[-1]['stopped'] == 1 and records[-1]['pc_after'] == expected['resume_pc'], records[-1]

        # 2. STOP withholds emulated ticks: no dot elapses and nothing retires.
        await asleep('idle')
        assert known(dut.dot_count) == expected['stop_dot'], 'STOP349_STOP_DOT'

        # 3. The stopped state is publicly observable: a dot budget cannot run.
        await control('HALT')
        stopped_reply = await control('RUN_DOTS', 1000)
        log('run_dots', reply=stopped_reply)
        assert stopped_reply['reason'] == abi.WIRE_RUN_DOTS_STOPPED and stopped_reply['executed'] == 0, stopped_reply
        await control('RUN')

        # 4. A press outside the selected row is not a wake source.
        applied = len(inputs)
        await control('INPUT', expected['inert_buttons'])
        await asleep('inert')
        assert len(inputs) == applied + 1 and inputs[-1]['buttons'] == expected['inert_buttons'], inputs

        # 5. A selected-row press wakes the CPU on the documented schedule: no
        # dot elapses while it sleeps, the wake spends one M-cycle on the fresh
        # PC read, and the first resumed instruction then retires on its length.
        applied = len(inputs)
        await control('INPUT', expected['wake_buttons'])
        while len(inputs) == applied:
            await Timer(1, unit='us')
            checked()
        press_dot = inputs[-1]['dot']
        assert inputs[-1]['buttons'] == expected['wake_buttons'], inputs
        assert press_dot == expected['stop_dot'], 'STOP349_PRESS_DOT'
        elapsed = 0
        while len(records) < len(events):
            await Timer(1, unit='us')
            elapsed += 1000
            checked()
            assert elapsed < SLEEP_WINDOW_NS, 'STOP349_WAKE_MISSING'
        wake_dot = records[len(entry)]['dot']
        assert wake_dot == expected['wake_dot'], f'STOP349_WAKE_DOT actual={wake_dot}'
        assert records[-1]['halted'] == 1 and records[-1]['stopped'] == 0, records[-1]

        await control('HALT')
        await Timer(1, unit='ns')
        await ReadOnly()
        checked()
        assert known(dut.paused) and not known(dut.fault), 'STOP349_FINAL_STATE'
        # Each accepted store commits four dots before its instruction retires.
        want_writes = [(40, 0xff40, 0), (60, 0xff00, expected['select_write']),
                       (expected['marker_dot'], expected['marker_address'], expected['marker_value'])]
        assert writes == want_writes, f'STOP349_WRITES expected={want_writes} actual={writes}'
        summary = dict(status='PASS', records=len(records), stop_dot=records[len(entry) - 1]['dot'],
                       press_dot=press_dot, wake_dot=wake_dot,
                       paused_dot=known(dut.dot_count), preload=loaded)
        Path('summary.json').write_text(json.dumps(summary, indent=2) + '\n')
        log('complete', **summary)
        for task in tasks:
            task.cancel()
    dut._log.info('PASS STOP349 composed stop wake records=11 marker=5a')
