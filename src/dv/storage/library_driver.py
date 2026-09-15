"""Verilator peer for tb_library_peer: no dot waits, named LIBRARY_ FAIL lines."""
from pathlib import Path
import sys

import cocotb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
import peer_bridge  # noqa: E402


@cocotb.test()
async def peer(dut):
    await peer_bridge.run(dut, waits=(), fail_prefix="LIBRARY_", progress_log="driver-progress.log")
