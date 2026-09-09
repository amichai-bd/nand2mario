import cocotb
from sequence import run


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def display_short(dut):
    await run(dut,short=True)
