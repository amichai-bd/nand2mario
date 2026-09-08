"""Continuous original-program proof using public owner observations and UART."""
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import FallingEdge, First, ReadOnly, Timer, ValueChange
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/v05'),
               str(ROOT / 'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from online import Online
from reference import FIRST_IMAGE_END, INPUT_MASKS, WINDOW_END, LCD_COMMIT, FRAME_DOTS, BOUNDED_END, input_window, unpack_retirement
from n2m.records import git_state
from n2m import generated_interfaces as abi
from n2m.preload import adopt, verify
from sw.rom_build import build_target


_WEAK_BITS = str.maketrans('LH', '01')


def known(signal):
    bits = str(signal.value)
    assert not bits.strip('01LH'), f'V05_UNKNOWN {signal._name}'
    return int(bits.translate(_WEAK_BITS), 2)


def wave_windows(complete, *, short=False, bounded=False):
    if bounded:
        return [(0,64), (LCD_COMMIT-32,LCD_COMMIT+256), (49968,52128), (107616,108192),
                (112268,112556), (BOUNDED_END-32,BOUNDED_END+2000)]
    windows = [(0,64), (LCD_COMMIT-32,LCD_COMMIT+256),
               (FIRST_IMAGE_END-32,FIRST_IMAGE_END+64)]
    if complete:
        for j in range(1,3 if short else 19):
            low,high = input_window(j, short=short)
            windows.append((low-32, high+128))
            first = LCD_COMMIT+70316+((1 if short else 20)*j+2)*FRAME_DOTS
            wake = first - 4652
            windows.append((wake-32,wake+508+32))
            windows.append((first-32,first+256))
        end = FIRST_IMAGE_END + 4*FRAME_DOTS if short else WINDOW_END
        windows.append((end-32,end+2000))
    return sorted(windows)


async def run(dut, *, complete, short=False, bounded=False, preloaded=False, physical=False):
    assert not physical or (bounded and preloaded), 'V05_PHYSICAL_PROFILE'
    entered = time.monotonic()
    dut._log.info("V05_PHASE entry")
    report = build_target(ROOT, Path.cwd() / ('run' if preloaded else 'software'),
                          SimpleNamespace(target='v05', rebuild=True), git_state(ROOT))
    dut._log.info("V05_PHASE software_built wall=%.3f", time.monotonic()-entered)
    assert report['status'] == 'PASS', 'V05_SOFTWARE_BUILD'
    image = (ROOT / report['rom']).read_bytes()
    recipe = json.loads((ROOT / 'src/dv/v05/program.json').read_text())
    for row in recipe['instructions']:
        literal = bytes.fromhex(row['bytes'])
        assert image[row['pc']:row['pc'] + len(literal)] == literal, 'V05_IMAGE_RECIPE'
    monitor = Online(short=short, bounded=bounded)
    received = Queue()
    entries = []
    armed = False
    run_time = None
    bound = monitor.end if complete else FIRST_IMAGE_END
    journal = []
    tasks = []
    with Path('transactions.jsonl').open('w') as trace, Path('retirement.csv').open('w') as retirement, Path('pixels.csv').open('w') as pixels:
        retirement.write('seq,record\n')
        pixels.write('frame,index,dot,shade\n')

        def observation(kind, **fields):
            trace.write(json.dumps(dict(kind=kind, time_ps=int(get_sim_time(unit='ps')), **fields)) + '\n')

        def phase(name):
            observation('phase', name=name, elapsed_wall_seconds=time.monotonic()-entered)
            trace.flush()
            dut._log.info("V05_PHASE %s", name)

        async def heartbeat():
            while True:
                await Timer(10, unit='ms')
                await ReadOnly()
                observation('heartbeat', dot=str(dut.dot_count.value), paused=str(dut.paused.value), epoch=str(dut.epoch.value), elapsed_wall_seconds=time.monotonic()-entered)
                trace.flush()
                dut._log.info("V05_HEARTBEAT")

        async def waveform_windows():
            await FallingEdge(dut.paused)
            for first, last in wave_windows(complete, short=short, bounded=bounded):
                while known(dut.dot_count) < first:
                    await Timer(1, unit='us')
                await Timer(1, unit='ns')
                dut.wave_enable.value = 1
                observation('wave_open', first=first, last=last, dot=known(dut.dot_count))
                while known(dut.dot_count) <= last:
                    await Timer(1, unit='us')
                dut.wave_enable.value = 0
                observation('wave_close', dot=known(dut.dot_count))

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
                try:
                    assert armed, 'V05_PAUSED_WRITE'
                    raw = known(dut.write_sample)
                except AssertionError as error:
                    observation('write_sample_failure', raw=str(dut.write_sample.value), armed=armed, mismatch=str(error))
                    raise
                dot, address, data = raw >> 24, (raw >> 8) & 65535, raw & 255
                monitor.write(dot, address, data)
                observation('cpu_write', dot=dot, address=address, data=data)

        async def source():
            while True:
                await ValueChange(dut.pixel_event)
                await ReadOnly()
                raw_text = str(dut.pixel_sample.value)
                try:
                    assert armed, 'V05_PAUSED_PIXEL'
                    raw = known(dut.pixel_sample)
                except AssertionError:
                    observation('pixel_sample_failure', raw=raw_text, armed=armed)
                    raise
                eligible, abort, start = raw & 1, (raw >> 1) & 1, (raw >> 2) & 1
                shade, y, x = (raw >> 3) & 3, (raw >> 5) & 255, (raw >> 13) & 255
                epoch, dot = (raw >> 21) & 0xffffffff, raw >> 53
                frame, index = divmod(monitor.pixels, 23040)
                try:
                    assert run_time is not None, 'V05_PIXEL_BEFORE_RUN'
                    elapsed = (int(get_sim_time(unit='ps')) - run_time) // 40000
                    assert dot == elapsed * 65536 // 390625, 'V05_PIXEL_ACTIVE_EDGE'
                    assert (epoch, start, abort, eligible) == (2, int(index == 0), 0, int(frame != 0)), 'V05_SOURCE_FLAGS'
                except AssertionError as error:
                    observation('pixel_boundary_failure', raw=raw_text, frame=frame, index=index, dot=dot, x=x, y=y, shade=shade, epoch=epoch, start=start, abort=abort, eligible=eligible, mismatch=str(error))
                    raise
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
                actual = known(dut.dot_count)
                if actual != expected:
                    observation('progress_failure', expected=expected, actual=actual)
                    trace.flush()
                    raise AssertionError(f'V05_TICK_PROGRESS expected={expected} actual={actual}')
                assert not known(dut.core_reset) and not known(dut.reset_sys) and not known(dut.fault), 'V05_CONTINUITY'
                await Timer(10, unit='us')
            assert known(dut.dot_count) >= bound, 'V05_EARLY_PAUSE'

        def check_tasks():
            for task in tasks:
                if task.done():
                    task.result()

        phase('before_first_timer')
        await Timer(1, unit='ns')
        phase('after_first_timer')
        tasks = [cocotb.start_soon(fn()) for fn in (records, writes, source, inputs, receiver, continuity, time_progress, heartbeat, waveform_windows)]
        await Timer(320, unit='ns')
        dut.reset_sys.value = 0
        dut.reset_pix.value = 0
        phase('reset_released')
        client = connect(dut, received, observation, entries)

        @bridge
        def load():
            identity = client.identify()
            if preloaded:
                prepared = verify(Path.cwd())
                assert (Path.cwd() / 'program.gb').read_bytes() == image, 'V05_PRELOAD_IMAGE'
                loaded = adopt(client, prepared)
            else:
                loaded = client.load(image)
            return identity, loaded

        phase('load_start')
        try:
            identity, loaded = await load()
        except Exception as error:
            observation('load_failure', command=getattr(error, 'command', None),
                        status=getattr(error, 'status', None), mismatch=str(error))
            trace.flush()
            raise
        phase('load_completed')
        if not preloaded:
            assert loaded['verified_bytes'] == 32768, 'V05_FULL_READBACK'
        assert known(dut.epoch) == 2 and known(dut.dot_count) == 0 and known(dut.paused), 'V05_INITIAL_STATE'
        armed = True

        @bridge
        def bridged_control(action, value=None):
            return client.control(action, value)

        async def control(action, value=None):
            refresh_clock(client)
            return await bridged_control(action, value)

        @bridge
        def selected(source):
            return client.select_input_source(source)

        @bridge
        def input_state():
            return tuple(client.read_host(address) for address in
                         (abi.HOST_REG_INPUT_SOURCE, abi.HOST_REG_INPUT,
                          abi.HOST_REG_INPUT_PHYSICAL, abi.HOST_REG_INPUT_EFFECTIVE))

        async def check_input(expected):
            refresh_clock(client)
            actual = await input_state()
            observation('input_state', expected=expected, actual=actual)
            assert actual == expected, f'V05_PHYSICAL_STATE expected={expected} actual={actual}'
            assert (known(dut.input_source_observe), known(dut.effective_buttons)) == (expected[0], expected[3]), 'V05_PUBLIC_INPUT_STATE'
            check_tasks()

        async def select(source):
            refresh_clock(client)
            await selected(source)

        async def physical_commit(mask):
            # Tick is stable from the falling edge through the accepting edge.
            while True:
                await FallingEdge(dut.clk_sys)
                if not known(dut.gb_tick):
                    break
            dut.physical_buttons.value = mask
            dut.physical_commit.value = 1
            dot = known(dut.dot_count)
            await FallingEdge(dut.clk_sys)
            dut.physical_commit.value = 0
            observation('physical_commit', dot=dot, buttons=mask)
            check_tasks()
            return dot

        if physical:
            await check_input((0, 0, 0, 0))
            await select(abi.INPUT_SOURCE_PHYSICAL)
            await check_input((1, 0, 0, 0))

        phase('run_request')
        await control('RUN')
        phase('run_reply')
        if complete:
            for index, mask in enumerate(monitor.input_masks, 1):
                low, high = input_window(index, short=short, bounded=bounded)
                while known(dut.dot_count) < low:
                    await Timer(1, unit='us')
                    check_tasks()
                if bounded:
                    assert monitor.reference.halted, 'V05_INPUT_BEFORE_FIRST_HALT'
                if physical:
                    dot = await physical_commit(mask)
                    assert len(journal) == 1 and journal[0] == dict(dot=dot, buttons=17), 'V05_PHYSICAL_APPLY'
                    await check_input((1, 0, 17, 17))
                    await control('INPUT', 2)
                    await check_input((1, 2, 17, 17))
                    await control('INPUT', 17)
                    await select(abi.INPUT_SOURCE_UART)
                    await check_input((0, 17, 17, 17))
                    await physical_commit(0)
                    await check_input((0, 17, 0, 17))
                    assert len(journal) == 1, 'V05_INPUT_ISOLATION'
                else:
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
            summary['scope'] = 'bounded startup/cross-frame' if bounded else 'short complete-path only' if short else 'legacy 600-interval'
            if physical:
                summary['input_scope'] = 'public physical commit, UART isolation and source switch'
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
