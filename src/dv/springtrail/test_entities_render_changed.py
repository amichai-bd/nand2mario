"""Complete fixed entity renderer changed entry."""
import cocotb
from entities_render_check import run


@cocotb.test(timeout_time=100,timeout_unit='ms')
async def entities_render_changed(dut):
    await run(dut,short=False,variant='changed')
