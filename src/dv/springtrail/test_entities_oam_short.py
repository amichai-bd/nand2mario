"""Complete current entity OAM short fixture."""
import cocotb
from entities_oam_check import run


@cocotb.test(timeout_time=40,timeout_unit='ms')
async def entities_oam_short(dut):
    await run(dut,short=True,part=None)
