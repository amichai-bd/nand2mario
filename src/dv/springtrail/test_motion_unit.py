"""Continuous Python entry for the finite motion fixture."""
import cocotb
from motion_unit_check import run

@cocotb.test()
async def motion_unit(dut):
    await run(dut, short=False)
