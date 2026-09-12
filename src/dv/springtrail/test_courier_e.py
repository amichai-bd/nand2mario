"""Complete current courier e fixture."""
import cocotb
from courier_check import run


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def courier_e(dut):
    await run(dut, short=False, part="e")
