"""Real initialization and one continuous blank-to-normal input update."""
import cocotb
from test_v05 import run


@cocotb.test(timeout_time=50, timeout_unit='ms')
async def bounded_complete(dut):
    await run(dut, complete=True, bounded=True, preloaded=True)
