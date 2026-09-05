"""Bounded ALTPLL generation; generated vendor HDL stays inside the attempt."""
from pathlib import Path
import os
import re

from .records import file_hash


def validate(definition):
    if definition != {"module": "n2m_pixel_pll", "input_ps": 20000,
                      "multiply": 63, "divide": 125}:
        raise ValueError("unsupported PLL definition")


def identity(directory):
    directory = Path(directory).resolve()
    paths = {"generator": directory / "qmegawiz.exe",
             "definition": directory.parent / "libraries/megafunctions/xml_info/altpll_info.xml",
             "primitive": directory.parent / "libraries/megafunctions/altpll.tdf",
             "rules": directory.parent / "libraries/megafunctions/xml_info/altpll_rules.xml",
             "wizard": directory.parent / "libraries/megafunctions/xml_info/altpll_wiz_map.xml"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("missing explicit Quartus ALTPLL generation dependency")
    return {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}


def generate(folder, identity, definition, execute, timeout, record, build):
    validate(definition)
    output = folder / "n2m_pixel_pll.v"
    command = [identity["generator"]["path"], "-silent", "module=altpll",
               "INTENDED_DEVICE_FAMILY=MAX 10", "INCLK0_INPUT_FREQUENCY=20000",
               "CLK0_MULTIPLY_BY=63", "CLK0_DIVIDE_BY=125", "CLK0_DUTY_CYCLE=50",
               "CLK0_PHASE_SHIFT=0", "COMPENSATE_CLOCK=CLK0", "OPERATION_MODE=NORMAL",
               "areset=used", "locked=used", "clk0=used", "OPTIONAL_FILES=NONE", output.name]
    generation_folder = folder
    if os.name == "nt":
        # qmegawiz's internal temporary paths exceed MAX_PATH in deep worktrees.
        # The filesystem alias names the same retained attempt, not a shared scratch area.
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        size = ctypes.windll.kernel32.GetShortPathNameW(str(folder.resolve()), buffer, len(buffer))
        if not size or size >= len(buffer) or Path(buffer.value).resolve() != folder.resolve():
            raise ValueError("cannot resolve a safe short path for PLL generation")
        generation_folder = Path(buffer.value)
    execute(command, generation_folder, folder / "generate-pll.log", timeout, record, build)
    verify(folder)


def verify(folder):
    path = folder / "n2m_pixel_pll.v"
    text = path.read_text(encoding="utf-8")
    expected = {"clk0_divide_by": "125", "clk0_multiply_by": "63", "clk0_duty_cycle": "50",
                "clk0_phase_shift": '"0"', "inclk0_input_frequency": "20000",
                "intended_device_family": '"MAX 10"', "operation_mode": '"NORMAL"',
                "port_areset": '"PORT_USED"', "port_locked": '"PORT_USED"'}
    for key, value in expected.items():
        values = re.findall(r"altpll_component\." + key + r"\s*=\s*([^,;]+)", text)
        if values != [value]:
            raise ValueError(f"generated PLL parameter mismatch: {key}")
    if re.search(r'`include\b|\$(?:readmemh|readmemb|fopen)\b', text):
        raise ValueError("untracked generated PLL dependency")
    if not re.search(r"module\s+n2m_pixel_pll\s*\(", text):
        raise ValueError("generated PLL module mismatch")
