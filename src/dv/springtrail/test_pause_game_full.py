import cocotb
from pause_game_check import run

@cocotb.test(timeout_time=170,timeout_unit="ms")
async def pause_game_full(dut):
    await run(dut,short=False)
