"""Complete current courier short fixture."""
import cocotb
from courier_check import run


@cocotb.test(timeout_time=40, timeout_unit="ms")
async def courier_short(dut):
    await run(dut, short=True, part="a")
