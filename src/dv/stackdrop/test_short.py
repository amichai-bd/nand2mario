import cocotb
from unit_check import run


@cocotb.test(timeout_time=20, timeout_unit='ms')
async def short(dut):
    await run(dut, 3)
