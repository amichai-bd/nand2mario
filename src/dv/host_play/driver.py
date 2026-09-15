"""Verilator peer for the host_play scenario: relative waits and named FAIL lines."""
from pathlib import Path
import sys

import cocotb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "integration"))
import peer_bridge  # noqa: E402


@cocotb.test()
async def peer(dut):
    await peer_bridge.run(dut, waits=(200000, 150000), relative=True, fail_prefix="PLAY_",
                          wait_seconds=300, progress_log="driver-progress.log")
