"""Unmodified pinned reg_f, real DMG owners and the linked upstream verdict."""
import json
from pathlib import Path
import sys
import time

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import Event, First, ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src/dv/mooneye'))
sys.path.insert(0, str(ROOT / 'src/dv/python/integration'))
from n2m.generated_interfaces import RECORDS
from n2m.preload import adopt, verify
from client_transport import connect, frames, refresh_clock
from check import completion


def known(signal):
    assert signal.value.is_resolvable, f'MOONEYE_UNKNOWN {signal._name}'
    return int(signal.value)


def decode(value):
    result = {}
    for field in RECORDS['retirement']:
        result[field['name']] = value & ((1 << field['bits']) - 1)
        value >>= field['bits']
    assert value == 0
    return result


@cocotb.test(timeout_time=500, timeout_unit='ms')
async def reg_f(dut):
    started = time.monotonic()
    received, complete = Queue(), Event()
    entries, last = [], {}
    counts = dict(records=0, bus=0, pixels=0)
    with Path('transactions.jsonl').open('w') as journal, \
         Path('retirement.csv').open('w') as records, Path('bus.csv').open('w') as bus:
        records.write('seq,record\n')
        bus.write('dot,address,write,data\n')

        def observation(kind, **fields):
            journal.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit='ps')), **fields))+'\n')

        def progress(stage):
            item = dict(stage=stage, wall_seconds=time.monotonic()-started,
                        time_ns=int(get_sim_time(unit='ns')), dot=known(dut.dot_count), **counts)
            print('MOONEYE_PROGRESS '+json.dumps(item), flush=True)
            observation('progress', **item)
            journal.flush()

        async def monitor_uart():
            async for encoded in frames(dut):
                observation('wire_reply', encoded=encoded.hex())
                received.put_nowait(encoded)

        async def monitor_record():
            while True:
                await ValueChange(dut.record_event)
                await ReadOnly()
                raw = known(dut.record_sample)
                actual = decode(raw)
                assert (actual['version'], actual['kind'], actual['epoch'], actual['seq']) == (1, 0, 2, counts['records']), 'MOONEYE_RECORD_ORDER'
                assert actual['f'] & 15 == 0, 'MOONEYE_F_LOW_BITS'
                records.write(f"{counts['records']},{raw:096x}\n")
                counts['records'] += 1
                last.clear()
                last.update(actual)
                if counts['records'] == 1:
                    assert actual['pc_before'] == 0x100, 'MOONEYE_ENTRY'
                    progress('first-retirement')
                if completion(actual):
                    Path('completion.json').write_text(json.dumps(dict(
                        status='PASS', record=actual, counts=counts,
                        image_sha256=verify(Path.cwd())['image_sha256']), indent=2))
                    progress('completion')
                    complete.set()
                    return

        async def monitor_bus():
            while True:
                await ValueChange(dut.bus_event)
                await ReadOnly()
                raw = known(dut.bus_sample)
                data, write, address, dot = raw & 255, (raw >> 8) & 1, (raw >> 9) & 65535, raw >> 25
                bus.write(f'{dot},{address:04x},{write},{data:02x}\n')
                counts['bus'] += 1
                assert not (write and address == 0xff02), 'MOONEYE_PAST_COMPLETION_SERIAL'

        async def monitor_pixels():
            while True:
                await ValueChange(dut.pixel_event)
                await ReadOnly()
                known(dut.pixel_sample)
                counts['pixels'] += 1

        async def guard():
            next_progress = 100000
            previous_dot = known(dut.dot_count)
            while True:
                await Timer(10, unit='us')
                assert not known(dut.fault), 'MOONEYE_OWNER_FAULT'
                assert (known(dut.reset_sys), known(dut.core_reset), known(dut.paused), known(dut.epoch)) == (0, 0, 0, 2), 'MOONEYE_RUN_BOUNDARY'
                dot = known(dut.dot_count)
                assert dot > previous_dot, 'MOONEYE_DOT_PROGRESS'
                previous_dot = dot
                if dot >= next_progress:
                    progress('running')
                    next_progress += 100000
                if dot >= 1000000:
                    Path('completion.json').write_text(json.dumps(dict(
                        status='MISSING', dot=dot, last=last, counts=counts), indent=2))
                    raise AssertionError('MOONEYE_MISSING_COMPLETION')

        await Timer(1, unit='ns')
        progress('entry')
        tasks = [cocotb.start_soon(fn()) for fn in (monitor_uart, monitor_record, monitor_bus, monitor_pixels)]
        try:
            await Timer(319, unit='ns')
            dut.reset_sys.value = 0
            client = connect(dut, received, observation, entries)

            @bridge
            def load():
                return client.identify(), adopt(client, verify(Path.cwd()))

            identity, loaded = await load()
            await Timer(1, unit='ns')
            await ReadOnly()
            assert (known(dut.epoch), known(dut.dot_count), known(dut.paused), known(dut.core_reset)) == (2, 0, 1, 0), 'MOONEYE_INITIAL_STATE'
            assert counts == dict(records=0, bus=0, pixels=0), 'MOONEYE_PAUSED_ACTIVITY'
            Path('initial-state.json').write_text(json.dumps(dict(identity=identity, load=loaded, epoch=2, counts=counts), indent=2))
            progress('loaded-paused')

            @bridge
            def run():
                client.control('INPUT', 0)
                client.control('RUN')

            refresh_clock(client)
            await run()
            progress('run')
            watchdog = cocotb.start_soon(guard())
            tasks.append(watchdog)
            # End on the sampled upstream breakpoint, before its serial routine.
            await First(complete.wait(), *tasks)
            for task in tasks:
                if task.done():
                    task.result()
            assert complete.is_set(), 'MOONEYE_MONITOR_ENDED'
            print('PASS mooneye-reg-f bank=1 pc=4a81 registers=3,5,8,13,21,34', flush=True)
        finally:
            Path('client.json').write_text(json.dumps(dict(requests=entries), indent=2))
            for task in tasks:
                if not task.done():
                    task.cancel()
