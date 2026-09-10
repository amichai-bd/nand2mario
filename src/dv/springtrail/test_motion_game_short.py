import cocotb
from hud_game_check import run


@cocotb.test(timeout_time=90,timeout_unit="ms")
async def motion_game(dut):
    await run(dut, short=True, motion=True)
