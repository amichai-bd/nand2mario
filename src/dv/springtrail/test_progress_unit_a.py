"""Continuous Python entry for one half of the progression fixture."""
import cocotb
import progress_cases
from motion_unit_check import run


@cocotb.test(timeout_time=150, timeout_unit='ms')
async def progress_unit(dut):
    await run(dut, short=False, suite=progress_cases, part='a')
