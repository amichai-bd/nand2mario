"""Continuous Python entry for one half of the contact/power fixture."""
import cocotb
import power_cases
from motion_unit_check import run

@cocotb.test(timeout_time=150, timeout_unit='ms')
async def power_unit(dut):
    await run(dut, short=False, suite=power_cases, part='a')
