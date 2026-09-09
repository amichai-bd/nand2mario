import cocotb
from flow_check import run


@cocotb.test(timeout_time=100, timeout_unit='ms')
async def flow_game(dut):
    await run(dut, False)
