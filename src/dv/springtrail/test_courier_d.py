"""Complete current courier d fixture."""
import cocotb
from courier_check import run


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def courier_d(dut):
    await run(dut, short=False, part="d")
