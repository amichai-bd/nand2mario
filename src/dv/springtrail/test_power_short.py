"""Continuous Python entry for the finite contact/power fixture."""
import cocotb
import power_cases
from motion_unit_check import run

@cocotb.test(timeout_time=35, timeout_unit='ms')
async def power_unit(dut):
    await run(dut, short=True, suite=power_cases)
