"""Complete current courier b fixture."""
import cocotb
from courier_check import run


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def courier_b(dut):
    await run(dut, short=False, part="b")
