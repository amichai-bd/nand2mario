"""Unmodified pinned reg_f, real DMG owners and the linked upstream verdict."""
import cocotb

from mooneye_run import run


@cocotb.test(timeout_time=500, timeout_unit='ms')
async def reg_f(dut):
    await run(dut, 'mooneye-reg-f', 0x4a81, 1)
