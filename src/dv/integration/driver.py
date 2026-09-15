"""Verilator peer for tb_integration: the integration scenario waits for dot 136280."""
import cocotb

import peer_bridge


@cocotb.test()
async def peer(dut):
    await peer_bridge.run(dut, waits=(136280,))
