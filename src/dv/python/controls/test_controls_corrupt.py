"""Single registered controls proof entry point."""
import cocotb
from controls import controls_corrupt as run


@cocotb.test()
async def controls_corrupt(dut):
    await run(dut)
