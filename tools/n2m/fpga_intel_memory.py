"""Bounded actual-fit checks for the four explicit Intel memory configurations."""
import os
from pathlib import Path
import re

from .records import file_hash
from .fpga_vga import rows, node


SHAPES = {"byte_ram": (160, 8), "pair_ram": (80, 16),
          "lanes_ram": (64, 32), "frame_ram": (23040, 2)}


def identity(directory):
    quartus = Path(directory).resolve().parent
    paths = {"definition": quartus / "libraries/megafunctions/altsyncram.tdf",
             "declaration": quartus / "libraries/megafunctions/altsyncram.inc",
             "model": quartus / "eda/sim_lib/altera_mf.v"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("missing installed Intel memory synthesis dependency")
    return {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}


def audit(quote):
    sys_ports = ["board_reset_n", "a_read", "a_write", "a_address[*]", "a_wdata[*]",
                 "a_byte_enable[*]", "b_read", "b_address[*]"]
    lines = ['set memory_inputs [open output/intel_memory_inputs.rpt w]']
    for name, ports, count in (("sys", sys_ports, 63), ("pix", ["frame_read", "frame_address[*]"], 16)):
        words = " ".join(quote(port) for port in ports)
        lines += [f'set memory_{name} [get_ports [list {words}]]',
                  f'if {{[get_collection_size $memory_{name}] != {count}}} {{error "Intel memory input count mismatch: {name}"}}',
                  f'puts $memory_inputs "{name} [get_collection_size $memory_{name}]"']
    lines.append("close $memory_inputs")
    return "\n".join(lines) + "\n"


def verify(folder):
    output = folder / "output"
    if (output / "intel_memory_inputs.rpt").read_text().splitlines() != ["sys 63", "pix 16"]:
        raise ValueError("Intel memory input-domain inventory differs")
    fit = (output / "design.fit.rpt").read_text(encoding="cp1252" if os.name == "nt" else "utf-8")
    memories = [row for row in rows(fit) if len(row) >= 20 and row[1] == "M9K"]
    if len(memories) != 4:
        raise ValueError("missing or extra Intel memory blocks in fitter RAM summary")
    evidence = {}
    for owner, (depth, width) in SHAPES.items():
        matches = [row for row in memories if node(row[0]).startswith(owner + "|ram|")]
        if len(matches) != 1:
            raise ValueError(f"Intel memory owner missing or duplicated: {owner}")
        row = matches[0]
        if row[4:12] != [str(depth), str(width), str(depth), str(width), "yes", "no", "yes", "no"]:
            raise ValueError(f"Intel memory dimensions or register stages differ: {owner}")
        if row[3] != ("Dual Clocks" if owner == "frame_ram" else "Single Clock"):
            raise ValueError(f"Intel memory clock mode differs: {owner}")
        if row[12] != str(depth * width) or row[19] != "None" or not int(row[18]) > 0:
            raise ValueError(f"Intel memory capacity, initialization or block usage differs: {owner}")
        evidence[owner] = {"depth": depth, "width": width, "m9ks": int(row[18]),
                           "mode": row[2], "clocks": row[3], "row": row}
    totals = [row[1] for row in rows(fit) if len(row) == 2 and row[0] == "Total block memory bits"]
    if len(totals) != 1 or not totals[0].startswith("50,688 /"):
        raise ValueError("Intel memory total block capacity differs")
    netlist = (folder / "simulation/questa/design.vo").read_text(encoding="utf-8")
    if "fiftyfivenm_ram_block" not in netlist or re.search(r"(?i)black.?box", netlist):
        raise ValueError("Intel memory device RAM primitive missing or black boxed")
    return evidence
