"""Full-duration wrapper, separate from the measured startup target."""
import cocotb
from test_v05 import run


@cocotb.test(timeout_time=12, timeout_unit="sec")
async def continuous(dut):
    await run(dut, complete=True)
