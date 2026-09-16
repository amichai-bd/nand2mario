"""Unmodified pinned Mooneye MBC1 selection (rom_512kb) in the 64 KiB profile, real DMG owners and the linked upstream verdict."""
import json
from pathlib import Path

import cocotb

from mooneye_run import run

# The prepared selection names the fixture and its locked completion address.
SELECTION = json.loads(Path('mooneye-build.json').read_text())


@cocotb.test(timeout_time=500, timeout_unit='ms')
async def mbc1(dut):
    await run(dut, SELECTION['fixture'], SELECTION['selection']['completion_address'], SELECTION['selection']['completion_bank'])
