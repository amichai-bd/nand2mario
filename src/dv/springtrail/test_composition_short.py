import cocotb
from composition_check import run


@cocotb.test(timeout_time=70,timeout_unit='ms')
async def composition(dut):
    await run(dut,short=True)
