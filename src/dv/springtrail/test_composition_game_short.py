import cocotb
from composition_game_check import run


@cocotb.test(timeout_time=80,timeout_unit="ms")
async def composition_game(dut):
    await run(dut,short=True)
