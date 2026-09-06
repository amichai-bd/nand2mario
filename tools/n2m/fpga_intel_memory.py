"""Bounded actual-fit checks for the four explicit Intel memory configurations."""
import os
from pathlib import Path
import re

from .records import file_hash
from .fpga_vga import rows, node
from .intel_memory import MIXED_MODE_MODEL_HASH


SHAPES = {"byte_ram": (160, 8), "pair_ram": (80, 16),
          "lanes_ram": (64, 32), "frame_ram": (23040, 2)}
SYS_CLOCK = r"\clk_sys~inputclkctrl_outclk"
PIX_CLOCK = r"\u_clocking|u_pll|altpll_component|auto_generated|wire_pll1_clk[0]~clkctrl_outclk"


def verify_netlist(text):
    atoms = re.findall(r"fiftyfivenm_ram_block\s+\\(\S+)\s*\((.*?)\);", text, re.DOTALL)
    if len(atoms) != 10:
        raise ValueError("Intel physical RAM atom count differs")
    evidence = {}
    counts = {name: 0 for name in SHAPES}
    first_bits = {name: [] for name in SHAPES}
    for name, body in atoms:
        owner = name.split("|", 1)[0]
        if owner not in SHAPES or not name.startswith(owner + "|ram|auto_generated|ram_block"):
            raise ValueError("unexpected Intel physical RAM owner")
        counts[owner] += 1
        ports = dict(re.findall(r"\.(\w+)\((.*?)\)(?:,|$)", body, re.DOTALL))
        ports = {key: re.sub(r"\s+", "", value) for key, value in ports.items()}
        params = dict(re.findall(r"defparam\s+\\" + re.escape(name) + r"\s+\.(\w+)\s*=\s*(.*?);", text))
        params = {key: value.strip().strip('"') for key, value in params.items()}
        depth, width = SHAPES[owner]
        expected = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K",
                    "power_up_uninitialized": "true",
                    "mixed_port_feed_through_mode": "dont_care" if owner == "frame_ram" else "old",
                    "port_b_address_clock": "clock1" if owner == "frame_ram" else "clock0",
                    "port_b_read_enable_clock": "clock1" if owner == "frame_ram" else "clock0"}
        for port in ("a", "b"):
            expected.update({f"port_{port}_logical_ram_depth": str(depth),
                             f"port_{port}_logical_ram_width": str(width),
                             f"port_{port}_data_out_clock": "none",
                             f"port_{port}_address_clear": "none",
                             f"port_{port}_data_out_clear": "none",
                             f"port_{port}_read_during_write_mode": "new_data_with_nbe_read"})
        if any(params.get(key) != value for key, value in expected.items()):
            raise ValueError(f"Intel physical RAM parameter differs: {name}")
        if any(key.startswith("mem_init") or key.startswith("init_file") for key in params):
            raise ValueError("Intel physical RAM initialization unexpectedly present")
        expected_ports = {"clk0": SYS_CLOCK, "clk1": PIX_CLOCK if owner == "frame_ram" else "gnd",
                          "clr0": "gnd", "clr1": "gnd", "portbwe": "gnd", "portbbyteenamasks": "1'b1"}
        if any(ports.get(key) != value for key, value in expected_ports.items()):
            raise ValueError(f"Intel physical RAM clocks, reset or read-only B differ: {name}")
        data_bits = [int(bit) for bit in re.findall(r"\\a_wdata\[(\d+)\]~input0", ports.get("portadatain", ""))]
        enables = [int(bit) for bit in re.findall(r"\\a_byte_enable\[(\d+)\]~input0", ports.get("portabyteenamasks", ""))]
        first = int(params["port_a_first_bit_number"])
        first_bits[owner].append(first)
        if owner == "frame_ram":
            valid_lanes = data_bits == [first] and first in (0, 1) and ports.get("portabyteenamasks") == "1'b1"
        else:
            bits = 8 if owner == "byte_ram" else 16
            expected_enables = [0] if owner == "byte_ram" else ([0, 0] if owner == "pair_ram" else [first // 8 + 1, first // 8])
            valid_lanes = data_bits == list(range(first + bits - 1, first - 1, -1)) and enables == expected_enables
        if not valid_lanes:
            raise ValueError(f"Intel physical RAM data or byte-lane mapping differs: {name}")
        evidence[name] = {"ports": ports, "parameters": params}
    if counts != {"byte_ram": 1, "pair_ram": 1, "lanes_ram": 2, "frame_ram": 6}:
        raise ValueError("Intel physical RAM owner counts differ")
    if {key: sorted(value) for key, value in first_bits.items()} != {
            "byte_ram": [0], "pair_ram": [0], "lanes_ram": [0, 16], "frame_ram": [0, 0, 0, 1, 1, 1]}:
        raise ValueError("Intel physical RAM bit partition differs")
    return evidence


def identity(directory):
    quartus = Path(directory).resolve().parent
    paths = {"definition": quartus / "libraries/megafunctions/altsyncram.tdf",
             "declaration": quartus / "libraries/megafunctions/altsyncram.inc",
             "model": quartus / "eda/sim_lib/altera_mf.v"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("missing installed Intel memory synthesis dependency")
    if file_hash(paths["model"]) != MIXED_MODE_MODEL_HASH:
        raise ValueError("Intel synthesis model differs from the reviewed simulation model")
    return {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}


def audit(quote):
    sys_ports = ["board_reset_n", "a_read", "a_write", "a_address[*]", "a_wdata[*]",
                 "a_byte_enable[*]", "b_read", "b_address[*]"]
    lines = ['set memory_inputs [open output/intel_memory_inputs.rpt w]']
    for name, ports, count in (("sys", sys_ports, 63),):
        words = " ".join(quote(port) for port in ports)
        lines += [f'set memory_{name} [get_ports [list {words}]]',
                  f'if {{[get_collection_size $memory_{name}] != {count}}} {{error "Intel memory input count mismatch: {name}"}}',
                  f'puts $memory_inputs "{name} [get_collection_size $memory_{name}]"',
                  f'foreach_in_collection port $memory_{name} {{puts $memory_inputs "input {name} [get_port_info -name $port]"}}']
    lines.append("close $memory_inputs")
    lines += ['set memory_captures [get_registers {frame_ram|ram|auto_generated|*}]',
              'if {[get_collection_size $memory_captures] == 0} {error "missing frame memory captures"}']
    for corner, model, temperature in (("slow85", "slow", 85), ("slow0", "slow", 0), ("fast0", "fast", 0)):
        lines += [f"set_operating_conditions -model {model} -voltage 1200 -temperature {temperature}", "update_timing_netlist"]
        for index, source in enumerate(["frame_read"] + [f"frame_address[{bit}]" for bit in range(15)]):
            lines += [f'set memory_launch [get_registers {quote(source)}]',
                      'if {[get_collection_size $memory_launch] != 1} {error "missing frame request launch register"}']
            for check in ("setup", "hold"):
                lines.append(f'report_timing -from $memory_launch -to $memory_captures -{check} -npaths 1 -detail full_path -file output/memory_{corner}_{index}_{check}.rpt')
    return "\n".join(lines) + "\n"


def verify(folder):
    output = folder / "output"
    inventory = (output / "intel_memory_inputs.rpt").read_text().splitlines()
    expected_inputs = ["sys 63"]
    expected_inputs += ["input sys " + name for name in ("board_reset_n", "a_read", "a_write", "b_read")]
    expected_inputs += [f"input sys {name}[{bit}]" for name, size in
                        (("a_address", 15), ("a_wdata", 32), ("a_byte_enable", 4), ("b_address", 8)) for bit in range(size)]
    if sorted(inventory) != sorted(expected_inputs):
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
    evidence["physical_atoms"] = verify_netlist(netlist)
    launch_paths = {}
    for corner in ("slow85", "slow0", "fast0"):
        for index, source in enumerate(["frame_read"] + [f"frame_address[{bit}]" for bit in range(15)]):
            for check in ("setup", "hold"):
                name = f"memory_{corner}_{index}_{check}.rpt"
                report = (output / name).read_text()
                fields = dict((row[0], row[1]) for row in rows(report) if len(row) == 2)
                clock = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
                if (fields.get("From Node") != source or
                        not node(fields.get("To Node", "")).startswith("frame_ram|ram|auto_generated|") or
                        fields.get("Launch Clock") != clock or fields.get("Latch Clock") != clock or
                        float(fields.get("Slack", "-inf").split()[0]) < 0):
                    raise ValueError(f"Intel pixel launch/capture timing differs: {name}")
                launch_paths[name] = fields
    evidence["pixel_launch_paths"] = launch_paths
    return evidence
