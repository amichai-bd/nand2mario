"""Complete supplementary acquisition CPU fixture."""
import cocotb
import acquisition_cases
from motion_unit_check import run

@cocotb.test(timeout_time=60, timeout_unit='ms')
async def acquisition(dut):
    await run(dut, short=False, suite=acquisition_cases, part='c')
