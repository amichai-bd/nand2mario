"""Continuous Python entry for one half of the interactive-block fixture."""
import cocotb
import blocks_cases
from motion_unit_check import run


@cocotb.test(timeout_time=150, timeout_unit='ms')
async def blocks_unit(dut):
    await run(dut, short=False, suite=blocks_cases, part='b')
