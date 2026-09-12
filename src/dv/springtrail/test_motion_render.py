"""Complete shared WALK2/skid renderer proof."""
import cocotb
from hud_game_check import run
from entities_render_check import expected_tiles
from motion_render_reference import Check
from motion_render_program import bounds
from pathlib import Path

@cocotb.test(timeout_time=120, timeout_unit="ms")
async def motion_render(dut):
    timing=bounds(Path("program.gb").read_bytes())
    await run(dut, checker=Check(source_lcd=timing["lcd"]), renderer_bound=timing["end_bound"], renderer=True, motion=True, expected_tiles=expected_tiles())
