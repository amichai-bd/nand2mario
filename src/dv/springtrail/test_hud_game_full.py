import cocotb
from hud_game_check import run

@cocotb.test(timeout_time=90,timeout_unit="ms")
async def hud_game_full(dut):
    await run(dut,short=False)
