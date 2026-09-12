"""Complete fixed entity renderer short entry."""
import cocotb
from entities_render_check import run


@cocotb.test(timeout_time=60,timeout_unit='ms')
async def entities_render_short(dut):
    await run(dut,short=True,variant='normal')
