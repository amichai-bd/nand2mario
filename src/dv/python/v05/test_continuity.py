"""Bounded continuity: all 18 legacy input transitions at one-frame spacing."""
import cocotb
from test_v05 import run


@cocotb.test(timeout_time=450, timeout_unit='ms')
async def continuity_complete(dut):
    await run(dut, complete=True, continuity=True, preloaded=True)
