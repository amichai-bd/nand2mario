"""Continuous Python entry for the finite interactive-block fixture."""
import cocotb
import blocks_cases
from motion_unit_check import run


@cocotb.test(timeout_time=35, timeout_unit='ms')
async def blocks_unit(dut):
    await run(dut, short=True, suite=blocks_cases)
