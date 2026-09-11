"""Continuous Python entry for the finite progression fixture."""
import cocotb
import progress_cases
from motion_unit_check import run


@cocotb.test(timeout_time=35, timeout_unit='ms')
async def progress_unit(dut):
    await run(dut, short=True, suite=progress_cases)
