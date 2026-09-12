"""Complete fixed entity renderer normal entry."""
import cocotb
from entities_render_check import run


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def entities_render_normal(dut):
    await run(dut,short=False,variant='normal')
