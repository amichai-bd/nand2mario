"""Complete shared WALK2/skid renderer proof."""
import cocotb
from hud_game_check import run

@cocotb.test(timeout_time=90, timeout_unit="ms")
async def motion_render(dut):
    await run(dut, renderer=True, motion=True)
