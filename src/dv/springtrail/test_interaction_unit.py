import cocotb
from interaction_check import run


@cocotb.test(timeout_time=200, timeout_unit='ms')
async def flow_unit(dut):
    await run(dut, 27)
