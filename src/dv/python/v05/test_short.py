"""Complete harness path at a short, separately named implementation scope."""
import cocotb
from test_v05 import run


@cocotb.test(timeout_time=150, timeout_unit='ms')
async def short_complete(dut):
    await run(dut, complete=True, short=True)
