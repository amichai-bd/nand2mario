"""Complete current entity OAM b fixture."""
import cocotb
from entities_oam_check import run


@cocotb.test(timeout_time=60,timeout_unit='ms')
async def entities_oam_b(dut):
    await run(dut,short=False,part='b')
