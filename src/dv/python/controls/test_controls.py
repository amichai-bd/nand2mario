"""Single registered controls proof entry point."""
import cocotb
from controls import controls_complete as run


@cocotb.test()
async def controls_complete(dut):
    await run(dut)
