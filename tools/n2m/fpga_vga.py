"""Exact VGA proof hierarchy: checked CDC collections and retained path reports."""
import math
import os
import re

CHAINS = ("pix_ready_sys", "sys_ready_pix", "ack_sys", "req_pix")
LAUNCHES = ("u_clocking|u_reset|pix_release[1]", "u_clocking|u_reset|sys_release[1]",
            "u_bridge|acknowledge", "u_bridge|request")
BUNDLES = (("offer_bank", "captured_bank", 2),
           ("offer_sequence", "captured_sequence", 64),
           ("offer_epoch", "captured_epoch", 32))
PORTS = [f"{color}[{bit}]" for color in ("red", "green", "blue") for bit in range(4)] + ["hsync_n", "vsync_n"]
CORNERS = (("slow85", "slow", 85), ("slow0", "slow", 0), ("fast0", "fast", 0))


def collection(kind, names, variable, quote):
    words = " ".join(quote(name) for name in names)
    return [f'set {variable} [get_{kind} [list {words}]]',
            f'if {{[get_collection_size ${variable}] != {len(names)}}} {{error "VGA endpoint count mismatch: {variable}"}}']


def first_pin(name, quote):
    # Mapping can use the register's D or synchronous-load data input. Never
    # match clock/reset pins, another stage, or accept both alternatives.
    names = " ".join(quote(f"u_bridge|{name}[0]|{pin}") for pin in ("d", "asdata"))
    return [f'set first_{name} [get_pins -nowarn [list {names}]]',
            f'if {{[get_collection_size $first_{name}] != 1}} {{error "VGA first data pin mismatch: {name}"}}',
            f'foreach_in_collection p $first_{name} {{puts "VGA_FIRST_PIN {name} [get_pin_info -name $p]"}}']


def constraints(quote):
    lines = []
    for name, launch in zip(CHAINS, LAUNCHES):
        lines += collection("registers", [launch], f"launch_{name}", quote)
        lines += first_pin(name, quote)
        lines.append(f"set_false_path -from $launch_{name} -to $first_{name}")
    for source, capture, width in BUNDLES:
        lines += collection("registers", [f"u_bridge|{source}[{i}]" for i in range(width)], source, quote)
        lines += collection("registers", [f"u_bridge|{capture}[{i}]" for i in range(width)], capture, quote)
        lines.append(f"set_max_delay 20.000 -from ${source} -to ${capture}")
        lines.append(f"set_min_delay 0.000 -from ${source} -to ${capture}")
    lines += collection("ports", PORTS, "vga_outputs", quote)
    lines += ["set_max_delay 10.000 -to $vga_outputs", "set_min_delay 0.000 -to $vga_outputs",
              "set_max_skew -to $vga_outputs 2.000"]
    return "\n".join(lines) + "\n"


def required_reports():
    names = ([f"{name}_{check}" for name in CHAINS for check in ("setup", "hold")]
             + [source for source, _, _ in BUNDLES] + ["outputs_max", "outputs_min", "skew"])
    return [f"vga_{corner}_{name}.rpt" for corner, _, _ in CORNERS for name in names] + ["vga_first_pins.rpt"]


def audit(quote):
    lines = ['set vga_first_report [open output/vga_first_pins.rpt w]']
    for name in CHAINS:
        lines += first_pin(name, quote)
        lines.append(f'foreach_in_collection p $first_{name} {{puts $vga_first_report "{name} [get_pin_info -name $p]"}}')
    lines.append("close $vga_first_report")
    for source, capture, width in BUNDLES:
        lines += collection("registers", [f"u_bridge|{source}[{i}]" for i in range(width)], source, quote)
        lines += collection("registers", [f"u_bridge|{capture}[{i}]" for i in range(width)], capture, quote)
    lines += collection("ports", PORTS, "vga_outputs", quote)
    # -multi_corner does not provide all file-output corners for these commands.
    for corner, model, temperature in CORNERS:
        lines += [f"set_operating_conditions -model {model} -voltage 1200 -temperature {temperature}",
                  "update_timing_netlist"]
        for name in CHAINS:
            for i in (0, 1):
                lines += collection("registers", [f"u_bridge|{name}[{i}]"], f"vga_chain_{i}", quote)
            for check in ("setup", "hold"):
                lines.append(f"report_timing -from $vga_chain_0 -to $vga_chain_1 -{check} -npaths 1 -detail full_path -file output/vga_{corner}_{name}_{check}.rpt")
        for source, capture, width in BUNDLES:
            # Each captured bit needs a path, not only the easiest bus member.
            lines.append(f"report_path -from ${source} -to ${capture} -npaths {width} -nworst 1 -file output/vga_{corner}_{source}.rpt")
        for name, option in (("max", ""), ("min", "-min_path")):
            lines.append(f"report_path -to $vga_outputs -npaths 14 -nworst 1 {option} -file output/vga_{corner}_outputs_{name}.rpt")
        lines.append(f"report_max_skew -npaths 14 -detail full_path -file output/vga_{corner}_skew.rpt")
    return "\n".join(lines) + "\n"


def verify(folder):
    output = folder / "output"
    reports = {}
    for name in required_reports():
        path = output / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"missing VGA evidence: {name}")
        reports[name] = path.read_text(encoding="utf-8")
    pins = reports["vga_first_pins.rpt"].splitlines()
    if len(pins) != len(CHAINS):
        raise ValueError("incomplete VGA first-pin inventory")
    for name, line in zip(CHAINS, pins):
        if line not in [f"{name} u_bridge|{name}[0]|{suffix}" for suffix in ("d", "asdata")]:
            raise ValueError("unsupported VGA first data pin")
    fit = (output / "design.fit.rpt").read_text(encoding="cp1252" if os.name == "nt" else "utf-8")
    if [row[1] for row in rows(fit) if len(row) == 2 and row[0] == "M9Ks"] != ["18 / 182 ( 10 % )"]:
        raise ValueError("unexpected total fitted M9K usage")
    memory = [row[1] for row in rows(fit) if len(row) == 2 and row[0] == "Total block memory bits"]
    if memory != ["138,240 / 1,677,312 ( 8 % )"]:
        raise ValueError("unexpected total fitted memory bits")
    ram_rows = [row for row in rows(fit) if len(row) > 4 and row[1:4] == ["M9K", "Simple Dual Port", "Dual Clocks"]]
    expected_banks = {f"u_bridge|banks[{i}].u_ram|pixels_rtl_0|auto_generated|ALTSYNCRAM" for i in range(3)}
    if len(ram_rows) != 3 or {node(row[0]) for row in ram_rows} != expected_banks:
        raise ValueError("missing or extra fitted dual-clock VGA RAM banks")
    for row in ram_rows:
        if len(row) < 20 or row[4:18] != ["23040", "2", "23040", "2", "yes", "no", "yes", "no", "46080", "23040", "2", "23040", "2", "46080"] or row[18] != "6" or row[19] != "None":
            raise ValueError("VGA RAM dimensions, registers, M9K usage or initialization differ")
    result = {"ram_banks": 3, "memory_bits": 138240, "m9k_blocks": 18, "first_pins": pins, "corners": {}}
    output_sources = {"u_clocking|u_reset|pix_release[1]", "u_bridge|u_scan|valid_out", "u_bridge|u_scan|hs_out", "u_bridge|u_scan|vs_out"}
    output_sources.update(f"u_bridge|u_scan|gray_out[{i}]" for i in range(4))
    for corner, model, temperature in CORNERS:
        model_name = f"{model.title()} 1200mV {temperature}C Model"
        prefix = f"vga_{corner}_"
        for name, text in reports.items():
            if name.startswith(prefix) and re.findall(r"Delay Model:\s*([^\r\n]+)", text) != [model_name]:
                raise ValueError(f"VGA report corner mismatch: {name}")
        bundles = {}
        for source, capture, width in BUNDLES:
            paths = path_rows(reports[prefix + source + ".rpt"], width)
            expected = {(f"u_bridge|{source}[{i}]", f"u_bridge|{capture}[{i}]") for i in range(width)}
            if {(node(row[1]), node(row[2])) for row in paths} != expected:
                raise ValueError("VGA bundle path inventory differs")
            delay = max(number(row[0]) for row in paths)
            if delay > 20:
                raise ValueError("VGA bundle datapath exceeds 20 ns")
            bundles[source] = delay
        output_delays = {}
        for direction in ("max", "min"):
            paths = path_rows(reports[prefix + "outputs_" + direction + ".rpt"], len(PORTS))
            if {row[2] for row in paths} != set(PORTS) or any(node(row[1]) not in output_sources for row in paths):
                raise ValueError("VGA output path inventory differs")
            delays = [number(row[0]) for row in paths]
            if any(value < 0 or value > 10 for value in delays):
                raise ValueError("VGA output datapath outside 0..10 ns")
            output_delays[direction] = max(delays) if direction == "max" else min(delays)
        if output_delays["max"] - output_delays["min"] > 2:
            raise ValueError("VGA complete output path spread exceeds 2 ns")
        skews = rows(summary(reports[prefix + "skew.rpt"]))
        assignment = [row for row in skews if row[0] == "set_max_skew"]
        port_filter = "[get_ports {" + " ".join("{" + p + "}" if "[" in p else p for p in PORTS) + "}]"
        if len(assignment) != 1 or len(assignment[0]) != 9 or assignment[0][4] or assignment[0][5] != port_filter:
            raise ValueError("VGA skew constraint inventory differs")
        details = [row for row in skews if row[0] == "--"]
        if len(details) != 28 or not re.search(r"Report Max Skew: Found 28 paths \(0 violated\)", reports[prefix + "skew.rpt"]):
            raise ValueError("missing or violated VGA skew paths")
        for row in assignment + details:
            if row[2] != "2.000" or number(row[1]) < 0 or not 0 <= number(row[3]) <= 2:
                raise ValueError("VGA skew exceeds required bound")
        for row in details:
            if len(row) != 9 or row[5] not in PORTS or node(row[4]) not in output_sources or row[6] != row[7] or row[6] != "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]":
                raise ValueError("unexpected VGA skew path or clock")
        chain_slacks = {}
        for name in CHAINS:
            clock = "clk_sys" if name in ("pix_ready_sys", "ack_sys") else "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
            for check in ("setup", "hold"):
                text = reports[prefix + name + "_" + check + ".rpt"]
                if not re.search(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)", text):
                    raise ValueError("missing or violated VGA synchronizer path")
                paths = [row for row in rows(summary(text)) if len(row) == 8 and row[0] != "Slack"]
                if len(paths) != 1 or [node(v) for v in paths[0][1:3]] != [f"u_bridge|{name}[0]", f"u_bridge|{name}[1]"] or paths[0][3:5] != [clock, clock] or number(paths[0][0]) < 0:
                    raise ValueError("VGA synchronizer path differs")
                chain_slacks[name + "_" + check] = number(paths[0][0])
        result["corners"][corner] = {"bundle_max_ns": bundles, "outputs_ns": output_delays,
                                     "skew_ns": number(assignment[0][3]), "chain_slack_ns": chain_slacks}
    return result


def rows(text):
    return [[part.strip() for part in line.split(";")[1:-1]] for line in text.splitlines() if line.startswith(";")]


def node(value):
    return "|".join(part.split(":")[-1] for part in value.split("|"))


def number(value):
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("nonfinite VGA timing evidence")
    return value


def summary(text):
    if text.count("; Summary of Paths") != 1 or "Path #1:" not in text:
        raise ValueError("missing VGA path summary")
    return text.split("; Summary of Paths", 1)[1].split("Path #1:", 1)[0]


def path_rows(text, count):
    if not re.search(r"Report Path: Found " + str(count) + r" paths\.", text):
        raise ValueError("incomplete VGA datapath report")
    paths = [row for row in rows(summary(text)) if len(row) == 3 and row[0] != "Delay"]
    if len(paths) != count or len({row[2] for row in paths}) != count:
        raise ValueError("missing or duplicate VGA datapath endpoint")
    if any(number(row[0]) < 0 for row in paths):
        raise ValueError("negative VGA datapath delay")
    return paths
