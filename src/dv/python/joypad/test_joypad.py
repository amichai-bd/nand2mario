"""Independent public-port checks of the digital JOYP owner, from MAS_joypad."""
import json
import os
from pathlib import Path
import random

import cocotb
from cocotb.triggers import ReadOnly, Timer


def read_value(buttons, select):
    """Each selected row pulls its pressed lines low; unselected lines stay high."""
    lines = 15
    if not select & 1:
        lines &= ~(buttons & 15)
    if not select & 2:
        lines &= ~(buttons >> 4)
    return 0xC0 | (select << 4) | lines


def advance(state, pins):
    buttons, select, _ = state
    if pins["reset_sys"] or pins["core_reset"]:
        return 0, 3, 0
    new_buttons = pins["input_buttons"] if pins["input_commit"] else buttons
    new_select = (pins["io_wdata"] >> 4) & 3 if pins["io_commit"] and pins["io_write"] else select
    falls = read_value(buttons, select) & ~read_value(new_buttons, new_select) & 15
    return new_buttons, new_select, int(bool(falls))


def outputs(state, pins):
    buttons, select, event = (0, 3, 0) if pins["reset_sys"] or pins["core_reset"] else state
    selected = int(pins["io_address"] == 0xFF00)
    value = read_value(buttons, select)
    return dict(io_selected=selected, io_rdata=value if selected else 0,
                buttons_observe=buttons, selected_active=int((value & 15) != 15),
                request_event=event)


@cocotb.test(timeout_time=100, timeout_unit="us")
async def joypad_contract(dut):
    # Literal anchors establish row mapping independently of the transition model.
    assert read_value(0, 3) == 0xFF
    assert read_value(1, 2) == 0xEE
    assert read_value(0x10, 1) == 0xDE
    assert read_value(0x81, 0) == 0xC6
    seed = int(os.environ["COCOTB_RANDOM_SEED"])
    rng = random.Random(seed)
    state = (0, 3, 0)
    pins = dict(reset_sys=1, core_reset=0, gb_tick=0, input_commit=0,
                input_buttons=0, io_commit=0, io_write=0, io_address=0xFF00, io_wdata=0)
    cycle = 0
    checks = 0
    dut.clk_sys.value = 0
    for name, value in pins.items():
        getattr(dut, name).value = value

    with Path("transactions.jsonl").open("w", encoding="utf-8") as trace:
        async def check(label, phase):
            nonlocal checks
            await ReadOnly()
            applied = {}
            for name, intended in pins.items():
                value = getattr(dut, name).value
                assert value.is_resolvable, f"JOYP_INPUT_UNKNOWN cycle={cycle} signal={name}"
                applied[name] = int(value)
                assert applied[name] == intended, f"JOYP_DRIVE_MISMATCH cycle={cycle} signal={name}"
            expected = outputs(state, applied)
            actual = {}
            for name in expected:
                value = getattr(dut, name).value
                assert value.is_resolvable, f"JOYP_UNKNOWN cycle={cycle} phase={phase} signal={name} value={value}"
                actual[name] = int(value)
            trace.write(json.dumps(dict(cycle=cycle, phase=phase, label=label, seed=seed,
                                        inputs=applied, expected=expected, actual=actual)) + "\n")
            trace.flush()
            for name, value in expected.items():
                assert actual[name] == value, (
                    f"JOYP_MISMATCH cycle={cycle} phase={phase} signal={name} "
                    f"expected={value} actual={actual[name]}")
            checks += 1
            return applied

        async def step(label, **changes):
            nonlocal state, cycle
            await Timer(5, unit="ns")
            dut.clk_sys.value = 0
            pins.update(input_commit=0, io_commit=0, io_write=0, gb_tick=0)
            pins.update(changes)
            for name, value in pins.items():
                getattr(dut, name).value = value
            await Timer(5, unit="ns")
            applied = await check(label, "pre")
            await Timer(5, unit="ns")
            dut.clk_sys.value = 1
            state = advance(state, applied)
            cycle += 1
            await check(label, "post")

        async def reset(name):
            nonlocal state
            # Assert between clocks, then observe before any rising edge.
            await Timer(2, unit="ns")
            dut.clk_sys.value = 0
            pins[name] = 1
            getattr(dut, name).value = 1
            state = (0, 3, 0)
            await Timer(1, unit="ns")
            await check(name, "async")
            await step(name + " held")
            await step(name + " release", **{name: 0})

        await Timer(1, unit="ns")
        await check("initial reset", "async")
        await step("reset release", reset_sys=0)
        await step("directions select", io_commit=1, io_write=1, gb_tick=1, io_wdata=0x20)
        await step("host update without dot", input_commit=1, input_buttons=1)
        await step("held line clears pulse")
        await step("release", input_commit=1, input_buttons=0)
        await step("repress", input_commit=1, input_buttons=1)
        await reset("reset_sys")  # Cancels a pending event before its consumer edge.
        await step("unselected held", input_commit=1, input_buttons=0x11)
        await step("select held", io_commit=1, io_write=1, gb_tick=1, io_wdata=0x20)
        await step("both rows same held line", io_commit=1, io_write=1, gb_tick=1, io_wdata=0)
        await step("shared line release one row", input_commit=1, input_buttons=0x10)
        await step("another line falls", input_commit=1, input_buttons=0x30)
        await step("adjacent event", input_commit=1, input_buttons=0x70)
        await reset("core_reset")

        for select in range(4):
            for buttons in range(256):
                await step("matrix", input_commit=1, input_buttons=buttons,
                           io_commit=1, io_write=1, gb_tick=1, io_wdata=select << 4)
        for value in range(256):
            await step("all write bits", io_commit=1, io_write=1, gb_tick=1, io_wdata=value)
        await step("uncommitted write", io_write=1, io_wdata=0)
        await step("read commit", io_commit=1, gb_tick=1, io_wdata=0)
        await step("off-address read", io_address=0xFF01)
        await step("return address", io_address=0xFF00)
        for _ in range(128):
            # Independent host and select commits, including coincident replacement.
            write = rng.randrange(2)
            await step("seeded updates", input_commit=rng.randrange(2), input_buttons=rng.randrange(256),
                       io_commit=write, io_write=write, gb_tick=write, io_wdata=rng.randrange(256))
        await step("final pulse clear")
    dut._log.info("PASS python-joypad cycles=%d observations=%d seed=%d", cycle, checks, seed)
