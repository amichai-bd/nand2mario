"""Complete current entity OAM a fixture."""
import cocotb
from entities_oam_check import run


@cocotb.test(timeout_time=60,timeout_unit='ms')
async def entities_oam_a(dut):
    await run(dut,short=False,part='a')
