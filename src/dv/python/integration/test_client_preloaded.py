"""Supported Intel preload with the same Client execution contract as real load."""
import cocotb
from test_integration import run_contract


@cocotb.test(timeout_time=500, timeout_unit="ms")
async def client_preloaded_contract(dut):
    await run_contract(dut, real_uart=True, client_preloaded=True)
