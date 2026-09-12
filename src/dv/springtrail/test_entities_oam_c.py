"""Complete current entity OAM c fixture."""
import cocotb
from entities_oam_check import run


@cocotb.test(timeout_time=60,timeout_unit='ms')
async def entities_oam_c(dut):
    await run(dut,short=False,part='c')
