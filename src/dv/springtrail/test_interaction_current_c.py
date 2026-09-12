"""Complete bounded current interaction CPU fixture."""
import cocotb
import interaction_current_cases
from motion_unit_check import run

@cocotb.test(timeout_time=60, timeout_unit='ms')
async def interaction_current(dut):
    await run(dut, short=False, suite=interaction_current_cases, part='c')
