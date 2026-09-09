import cocotb
from hud_game_check import run

@cocotb.test(timeout_time=90,timeout_unit="ms")
async def hud_render(dut):
    await run(dut,renderer=True)
