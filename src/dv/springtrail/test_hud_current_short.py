"""Complete current HUD and column fixture."""
import cocotb
from hud_current_check import run


@cocotb.test(timeout_time=30, timeout_unit="ms")
async def hud_current_short(dut):
    await run(dut, short=True, part="a")
