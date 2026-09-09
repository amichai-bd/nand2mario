import cocotb
from dma_check import run


@cocotb.test(timeout_time=20,timeout_unit='ms')
async def publisher(dut):
    await run(dut)
