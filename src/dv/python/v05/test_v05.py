"""Continuous original-program proof using public owner observations and UART."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import FallingEdge, First, ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/v05'),
               str(ROOT / 'src/dv/python/integration')]
from client_transport import connect, frames
from online import Online
from reference import FIRST_IMAGE_END, INPUT_MASKS, WINDOW_END, input_window, unpack_retirement
from n2m.records import git_state
from sw.rom_build import build_target


def known(signal):
    assert signal.value.is_resolvable, f'V05_UNKNOWN {signal._name}'
    return int(signal.value)


async def run(dut, *, complete):
    report = build_target(ROOT, Path.cwd() / 'software',
                          SimpleNamespace(target='v05', rebuild=True), git_state(ROOT))
    assert report['status'] == 'PASS', 'V05_SOFTWARE_BUILD'
    image = (ROOT / report['rom']).read_bytes()
    recipe = json.loads((ROOT / 'src/dv/v05/program.json').read_text())
    for row in recipe['instructions']:
        literal = bytes.fromhex(row['bytes'])
        assert image[row['pc']:row['pc'] + len(literal)] == literal, 'V05_IMAGE_RECIPE'
    monitor = Online()
    received = Queue()
    entries = []
    armed = False
    run_time = None
    bound = WINDOW_END if complete else FIRST_IMAGE_END
    journal = []
    tasks = []
    with Path('transactions.jsonl').open('w') as trace, Path('retirement.csv').open('w') as retirement, Path('pixels.csv').open('w') as pixels:
        retirement.write('seq,record\n')
        pixels.write('frame,index,dot,shade\n')

        def observation(kind, **fields):
            trace.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit='ps')), **fields)) + '\n')

        async def records():
            while True:
                await ValueChange(dut.record_event)
                await ReadOnly()
                raw = known(dut.record_sample)
                assert armed, 'V05_PAUSED_RETIREMENT'
                value = unpack_retirement(f'{raw:x}')
                retirement.write(f"{value['seq']},{raw:096x}\n")
                try:
                    monitor.retirement(value)
                except ValueError as error:
                    observation('retirement_failure', actual=value, mismatch=str(error))
                    raise

        async def writes():
            while True:
                await ValueChange(dut.write_event)
                await ReadOnly()
                assert armed, 'V05_PAUSED_WRITE'
                raw = known(dut.write_sample)
                dot, address, data = raw >> 24, (raw >> 8) & 65535, raw & 255
                monitor.write(dot, address, data)
                observation('cpu_write', dot=dot, address=address, data=data)

        async def source():
            while True:
                await ValueChange(dut.pixel_event)
                await ReadOnly()
                assert armed, 'V05_PAUSED_PIXEL'
                raw = known(dut.pixel_sample)
                eligible, abort, start = raw & 1, (raw >> 1) & 1, (raw >> 2) & 1
                shade, y, x = (raw >> 3) & 3, (raw >> 5) & 255, (raw >> 13) & 255
                epoch, dot = (raw >> 21) & 0xffffffff, raw >> 53
                assert run_time is not None, 'V05_PIXEL_BEFORE_RUN'
                elapsed = (int(get_sim_time(unit='ps')) - run_time) // 40000
                assert dot == elapsed * 65536 // 390625, 'V05_PIXEL_ACTIVE_EDGE'
                frame, index = divmod(monitor.pixels, 23040)
                assert (epoch, start, abort, eligible) == (2, int(index == 0), 0, int(frame != 0)), 'V05_SOURCE_FLAGS'
                pixels.write(f'{frame},{index},{dot},{shade}\n')
                try:
                    monitor.pixel(frame, x, y, dot, shade)
                except ValueError as error:
                    observation('pixel_failure', frame=frame, index=index, dot=dot, shade=shade, mismatch=str(error))
                    raise

        async def inputs():
            while True:
                await ValueChange(dut.input_event)
                await ReadOnly()
                raw = known(dut.input_sample)
                epoch, dot, buttons = raw >> 72, (raw >> 8) & ((1 << 64) - 1), raw & 255
                assert epoch == 2 and armed, 'V05_INPUT_EPOCH'
                monitor.input(dot, buttons)
                journal.append(dict(dot=dot, buttons=buttons))
                observation('applied_input', **journal[-1])

        async def receiver():
            async for encoded in frames(dut):
                received.put_nowait(encoded)

        async def continuity():
            while True:
                await First(*(ValueChange(signal) for signal in (dut.reset_sys, dut.core_reset, dut.paused, dut.fault)))
                await ReadOnly()
                if armed:
                    assert not known(dut.reset_sys) and not known(dut.core_reset) and not known(dut.fault), 'V05_CONTINUITY'
                    if known(dut.paused):
                        assert known(dut.dot_count) >= bound, 'V05_EARLY_PAUSE'

        async def time_progress():
            nonlocal run_time
            await FallingEdge(dut.paused)
            run_time = int(get_sim_time(unit='ps'))
            await Timer(1, unit='ns')
            while not known(dut.paused):
                await ReadOnly()
                elapsed = (int(get_sim_time(unit='ps')) - run_time) // 40000
                expected = elapsed * 65536 // 390625
                assert known(dut.dot_count) == expected, f'V05_TICK_PROGRESS expected={expected} actual={known(dut.dot_count)}'
                assert not known(dut.core_reset) and not known(dut.reset_sys) and not known(dut.fault), 'V05_CONTINUITY'
                await Timer(10, unit='us')
            assert known(dut.dot_count) >= bound, 'V05_EARLY_PAUSE'

        def check_tasks():
            for task in tasks:
                if task.done():
                    task.result()

        await Timer(1, unit='ns')
        tasks = [cocotb.start_soon(fn()) for fn in (records, writes, source, inputs, receiver, continuity, time_progress)]
        await Timer(320, unit='ns')
        dut.reset_sys.value = 0
        dut.reset_pix.value = 0
        client = connect(dut, received, observation, entries)

        @bridge
        def load():
            identity = client.identify()
            loaded = client.load(image)
            return identity, loaded

        identity, loaded = await load()
        assert loaded['verified_bytes'] == 32768, 'V05_FULL_READBACK'
        assert known(dut.epoch) == 2 and known(dut.dot_count) == 0 and known(dut.paused), 'V05_INITIAL_STATE'
        armed = True

        @bridge
        def control(action, value=None):
            return client.control(action, value)

        await control('RUN')
        if complete:
            for index, mask in enumerate(INPUT_MASKS, 1):
                low, high = input_window(index)
                while known(dut.dot_count) < low:
                    await Timer(1, unit='us')
                    check_tasks()
                reply = await control('INPUT', mask)
                observation('input_reply', transition=index, reply=reply)
                assert len(journal) == index, 'V05_INPUT_REPLY_WITHOUT_APPLY'
                assert reply['dot'] == journal[-1]['dot'], 'V05_INPUT_REPLY_DOT'
        while known(dut.dot_count) < bound:
            await Timer(1, unit='us')
            check_tasks()
        await control('HALT')
        await Timer(1, unit='ns')
        await ReadOnly()
        check_tasks()
        pause_dot = known(dut.dot_count)
        assert known(dut.paused) and bound <= pause_dot <= bound + 2000, 'V05_PAUSE_WINDOW'
        if complete:
            summary = monitor.finish(pause_dot)
        else:
            assert monitor.pixels == 46080, 'V05_STARTUP_PIXELS'
            assert monitor.reference.step(pause_dot) is None, 'V05_RETIRE_MISSING'
            assert not monitor.writes, 'V05_WRITE_EXTRA'
            summary = dict(scope='startup only', pixels=monitor.pixels, retirements=monitor.retirements, pause_dot=pause_dot)
        Path('summary.json').write_text(json.dumps(dict(summary=summary, identity=identity, loaded=loaded, journal=journal, requests=entries), indent=2))
        for task in tasks:
            task.cancel()
        print('PASS V05 ' + ('continuous' if complete else 'startup') + ' ' + json.dumps(summary))


@cocotb.test(timeout_time=500, timeout_unit='ms')
async def startup(dut):
    await run(dut, complete=False)
