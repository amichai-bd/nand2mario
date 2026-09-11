import cocotb
from pause_game_check import run

@cocotb.test(timeout_time=90,timeout_unit="ms")
async def pause_game_short(dut):
    await run(dut,short=True)
