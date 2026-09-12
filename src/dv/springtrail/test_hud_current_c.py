"""Complete current HUD and column fixture."""
import cocotb
from hud_current_check import run


@cocotb.test(timeout_time=60, timeout_unit="ms")
async def hud_current_c(dut):
    await run(dut, short=False, part="c")
