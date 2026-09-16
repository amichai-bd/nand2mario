import cocotb
from unit_check import run
from budget import UNIT_BOUND, timeout_ms


@cocotb.test(timeout_time=timeout_ms(UNIT_BOUND), timeout_unit='ms')
async def unit(dut):
    await run(dut, 73)

