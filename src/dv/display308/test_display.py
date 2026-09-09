import cocotb
from sequence import run


@cocotb.test(timeout_time=30,timeout_unit='ms')
async def display_sequence(dut):
    await run(dut)
