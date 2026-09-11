"""Continuous Python entry for the finite motion fixture."""
import cocotb
from motion_unit_check import run

@cocotb.test(timeout_time=35, timeout_unit='ms')
async def motion_unit(dut):
    await run(dut, short=True)
