"""Single registered controls proof entry point."""
import cocotb
from controls import controls_startup as run


@cocotb.test()
async def controls_startup(dut):
    await run(dut)
