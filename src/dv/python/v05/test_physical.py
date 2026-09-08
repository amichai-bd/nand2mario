"""Existing bounded original program through the public physical input ports."""
import cocotb
from test_v05 import run


@cocotb.test(timeout_time=50, timeout_unit='ms')
async def physical_complete(dut):
    await run(dut, complete=True, bounded=True, preloaded=True, physical=True)
