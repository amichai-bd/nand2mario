"""Complete current courier c fixture."""
import cocotb
from courier_check import run


@cocotb.test(timeout_time=100, timeout_unit="ms")
async def courier_c(dut):
    await run(dut, short=False, part="c")
