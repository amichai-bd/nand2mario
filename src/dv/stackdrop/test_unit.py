import cocotb
from unit_check import run


@cocotb.test(timeout_time=200, timeout_unit='ms')
async def unit(dut):
    await run(dut, 73)

