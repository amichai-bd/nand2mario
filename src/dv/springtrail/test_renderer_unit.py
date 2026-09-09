import cocotb
from renderer_check import run


@cocotb.test(timeout_time=200, timeout_unit='ms')
async def renderer_unit(dut):
    await run(dut, 18)
