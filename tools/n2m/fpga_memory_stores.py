"""Check the seven direct-profile stores in retained MAX 10 fit evidence."""
import os
import re

from .fpga_intel_memory import SYS_CLOCK
from .fpga_vga import rows, node


# Independent acceptance inventory, not inferred from DUT parameters.
STORES = {"rom": (32768, 32), "wram": (8192, 8), "vram": (8192, 8),
          "hram": (127, 1), "oam_low": (80, 1), "oam_high": (80, 1),
          "wave_ram": (16, 1)}


def verify_netlist(text):
    atoms = re.findall(r"fiftyfivenm_ram_block\s+\\(\S+)\s*\((.*?)\);", text, re.DOTALL)
    if len(atoms) != 52 or len({name for name, _ in atoms}) != 52:
        raise ValueError("memory store physical atom count differs")
    evidence = {}
    partitions = {owner: [] for owner in STORES}
    for name, body in atoms:
        owner = name.split("|", 1)[0]
        if owner not in STORES or not name.startswith(owner + "|ram|auto_generated|ram_block"):
            raise ValueError("unexpected memory store physical owner")
        ports = {key: re.sub(r"\s+", "", value) for key, value in
                 re.findall(r"\.(\w+)\((.*?)\)(?:,|$)", body, re.DOTALL)}
        pairs = re.findall(r"defparam\s+\\" + re.escape(name) + r"\s+\.(\w+)\s*=\s*(.*?);", text)
        params = {key: value.strip().strip('"') for key, value in pairs}
        if len(params) != len(pairs):
            raise ValueError("duplicate memory store physical parameter")
        depth, _ = STORES[owner]
        wide = depth < 8192
        expected = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K",
                    "power_up_uninitialized": "true", "mixed_port_feed_through_mode": "old",
                    "port_b_address_clock": "clock0", "port_b_read_enable_clock": "clock0"}
        for port in ("a", "b"):
            expected.update({f"port_{port}_logical_ram_depth": str(depth),
                             f"port_{port}_logical_ram_width": "8",
                             f"port_{port}_data_out_clock": "none",
                             f"port_{port}_address_clear": "none",
                             f"port_{port}_data_out_clear": "none",
                             f"port_{port}_read_during_write_mode": "new_data_with_nbe_read",
                             f"port_{port}_data_width": "18" if wide else "1",
                             f"port_{port}_first_address": "0",
                             f"port_{port}_last_address": str((1 << (depth - 1).bit_length()) - 1 if wide else 8191)})
        if any(params.get(key) != value for key, value in expected.items()):
            raise ValueError(f"memory store physical parameter differs: {name}")
        if any(key.startswith(("mem_init", "init_file")) for key in params):
            raise ValueError("memory store initialization unexpectedly present")
        required_ports = {"clk0": SYS_CLOCK, "clk1": "gnd", "clr0": "gnd", "clr1": "gnd",
                          "portbwe": "gnd", "portabyteenamasks": "1'b1", "portbbyteenamasks": "1'b1",
                          "portaaddrstall": "gnd", "portbaddrstall": "gnd"}
        if any(ports.get(key) != value for key, value in required_ports.items()):
            raise ValueError(f"memory store clock, reset or whole-byte control differs: {name}")
        first = int(params.get("port_a_first_bit_number", "-1"))
        if params.get("port_b_first_bit_number") != str(first):
            raise ValueError("memory store A/B bit partition differs")
        partitions[owner].append(first)
        evidence[name] = {"ports": ports, "parameters": params}
    for owner, (depth, count) in STORES.items():
        expected = [0] if depth < 8192 else [bit for bit in range(8) for _ in range(count // 8)]
        if sorted(partitions[owner]) != expected:
            raise ValueError(f"memory store physical bit inventory differs: {owner}")
    return evidence


def verify(folder):
    fit = (folder / "output/design.fit.rpt").read_text(encoding="cp1252" if os.name == "nt" else "utf-8")
    memories = [row for row in rows(fit) if len(row) >= 24 and row[1] == "M9K"]
    if len(memories) != 7:
        raise ValueError("memory store logical inventory differs")
    evidence = {}
    for owner, (depth, blocks) in STORES.items():
        matches = [row for row in memories if node(row[0]).startswith(owner + "|ram|")]
        if len(matches) != 1:
            raise ValueError(f"memory store missing or duplicated: {owner}")
        row = matches[0]
        if (row[2:12] != ["True Dual Port", "Single Clock", str(depth), "8", str(depth), "8", "yes", "no", "yes", "no"]
                or row[12] != str(depth * 8) or row[18:20] != [str(blocks), "None"]
                or row[21:24] != ["Old data", "New data with NBE Read", "New data with NBE Read"]):
            raise ValueError(f"memory store fitted service differs: {owner}")
        evidence[owner] = {"depth": depth, "width": 8, "m9ks": blocks, "row": row}
    totals = [row[1] for row in rows(fit) if len(row) == 2 and row[0] == "Total block memory bits"]
    if len(totals) != 1 or not totals[0].startswith("395,640 /"):
        raise ValueError("memory store total capacity differs")
    text = (folder / "simulation/questa/design.vo").read_text()
    if re.search(r"(?i)black.?box", text):
        raise ValueError("memory store black box present")
    evidence["physical_atoms"] = verify_netlist(text)
    return evidence
