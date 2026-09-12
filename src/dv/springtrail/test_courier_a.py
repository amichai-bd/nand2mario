"""Complete current courier a fixture."""
import cocotb
from courier_check import run


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def courier_a(dut):
    await run(dut, short=False, part="a")
