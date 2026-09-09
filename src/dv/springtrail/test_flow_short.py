import cocotb
from flow_check import run


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def flow_short(dut):
    await run(dut, True)
