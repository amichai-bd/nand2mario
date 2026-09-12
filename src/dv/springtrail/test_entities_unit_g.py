"""Complete bounded entity CPU fixture."""
import cocotb
import entities_cases
from motion_unit_check import run

@cocotb.test(timeout_time=100, timeout_unit='ms')
async def entities_unit(dut):
    await run(dut, short=False, suite=entities_cases, part='g')
