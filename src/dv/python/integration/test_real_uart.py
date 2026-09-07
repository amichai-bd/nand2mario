"""Full product Client integration using independent Python monitors."""
import cocotb
from test_integration import run_contract


@cocotb.test(timeout_time=500, timeout_unit="ms")
async def real_uart_contract(dut):
    await run_contract(dut, real_uart=True)
