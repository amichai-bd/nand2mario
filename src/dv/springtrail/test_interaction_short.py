import cocotb
from interaction_check import run


@cocotb.test(timeout_time=200, timeout_unit='ms')
async def flow_short(dut):
    await run(dut, 3)
