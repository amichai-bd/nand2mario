import cocotb
from hud_unit_check import run


@cocotb.test(timeout_time=35, timeout_unit='ms')
async def hud_unit(dut):
    await run(dut, short=True)
