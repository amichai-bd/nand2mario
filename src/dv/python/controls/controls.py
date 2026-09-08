"""Paused actual-board controls through real UART, ADC and clock models."""
import json
from pathlib import Path
import sys

import cocotb
from cocotb.queue import Queue
from cocotb.task import bridge
from cocotb.triggers import ReadOnly, Timer
from cocotb.utils import get_sim_time

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / 'tools'), str(ROOT / 'src/dv/python/integration')]
from client_transport import connect, frames, refresh_clock
from n2m import generated_interfaces as abi
from n2m.preload import adopt, verify


async def run(dut, *, corrupt=False):
    received = Queue()
    entries, observations = [], []

    def observe(kind, **fields):
        event = dict(kind=kind, time_ns=float(get_sim_time(unit='ns')), **fields)
        observations.append(event)
        with Path('transactions.jsonl').open('a') as stream:
            stream.write(json.dumps(event) + '\n')

    async def receive():
        async for packet in frames(dut):
            received.put_nowait(packet)

    receiver = cocotb.start_soon(receive())
    client = connect(dut, received, observe, entries)
    await Timer(1, unit='us')
    dut.board_reset_n.value = 1
    # Default ADC 10 ms qualifier plus acquisition; validate this margin in startup.
    await Timer(13, unit='ms')

    @bridge
    def initialize():
        client.identify()
        return adopt(client, verify(Path.cwd()))

    refresh_clock(client)
    initial = await initialize()

    @bridge
    def read_state():
        return [client.read_host(address) for address in (
            abi.HOST_REG_INPUT_PHYSICAL, abi.HOST_REG_INPUT_EFFECTIVE,
            abi.HOST_REG_INPUT_SOURCE, abi.HOST_REG_STATE, abi.HOST_REG_DOT_LO)]

    async def check(physical, effective, source):
        refresh_clock(client)
        actual = await read_state()
        await Timer(1, unit='ns')
        await ReadOnly()
        expected = [physical, effective, source, abi.STATE_PAUSED, 0]
        led = effective | (source << 8) | 0x200
        got = int(dut.leds.value)
        observations.append(dict(kind='state', expected=expected, actual=actual,
                                 led_expected=led, led_actual=got))
        assert actual == expected and got == led, f'CONTROLS_SYSTEM_MASK expected={expected},{led:03x} actual={actual},{got:03x}'
        assert int(dut.paused.value) == 1 and int(dut.fault.value) == 0, 'CONTROLS_SYSTEM_STATE'
        await Timer(1, unit='ns')

    @bridge
    def command(name, value=None):
        if value is None:
            return client.control(name)
        return client.control(name, value)

    @bridge
    def source(value):
        return client.write_host(abi.HOST_REG_INPUT_SOURCE, value)

    try:
        await check(0x08, 0, 0)
        refresh_clock(client)
        await command('INPUT', 2)
        await check(0x08, 2, 0)
        dut.buttons_n.value = 0xE
        await Timer(6, unit='ms')
        await check(0x18, 2, 0)
        refresh_clock(client)
        await source(1)
        await check(0x18, 0x18, 1)
        refresh_clock(client)
        await command('RESET')
        await check(0x18, 0, 0)
        refresh_clock(client)
        await source(1)
        await check(0x18, 0x18, 1)
        if corrupt:
            dut.corrupt.value = 1
        dut.buttons_n.value = 0xF
        await Timer(6, unit='ms')
        if corrupt:
            assert int(dut.injection_done.value) == 1, 'CONTROLS_SYSTEM_INJECTION_MISSING'
            observe('injection', intended=0x08, injected=0)
        await check(0x08, 0x08, 1)
        print('CONTROLS_SYSTEM_PASS checks=7')
    finally:
        Path('controls.json').write_text(json.dumps(dict(initial=initial,
            observations=observations, client=entries), indent=2))
        receiver.cancel()


async def controls_complete(dut):
    await run(dut)


async def controls_corrupt(dut):
    await run(dut, corrupt=True)


async def controls_startup(dut):
    """Bounded diagnostic only; no controls acceptance claim."""
    def mark(label):
        with Path('transactions.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(label=label, time_ns=float(get_sim_time(unit='ns')),
                reset=str(dut.board_reset_n.value), leds=str(dut.leds.value))) + '\n')
            stream.flush()
    mark('entry')
    await Timer(1, unit='ns')
    mark('1ns')
    await Timer(999, unit='ns')
    mark('1us')
    dut.board_reset_n.value = 1
    await Timer(999, unit='us')
    mark('1ms')
    for target_ms in (10, 11, 12, 13):
        await Timer(target_ms * 1000000 - int(get_sim_time(unit='ns')), unit='ns')
        mark(f'{target_ms}ms')
    print('CONTROLS_STARTUP_DIAGNOSTIC')
