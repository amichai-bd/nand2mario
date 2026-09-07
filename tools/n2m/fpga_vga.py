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
# Fitter packs six copies of each grayscale bit into the twelve RGB pins.
RGB_REGISTERS = tuple(f"u_bridge|u_scan|gray_out[{i % 2}]" +
                      (f"~_Duplicate_{i // 2}" if i // 2 else "") for i in range(12))
OUTPUT_REGISTERS = (*RGB_REGISTERS, "u_bridge|u_scan|hs_out", "u_bridge|u_scan|vs_out")
BLANK_CONTROLS = (("active", "u_bridge|blank_active"), ("request", "u_bridge|blank_pix[1]"))
CORNERS = (("slow85", "slow", 85), ("slow0", "slow", 0), ("fast0", "fast", 0))


def chain_profile(lcd=False):
    if type(lcd) is not bool:
        raise ValueError("invalid VGA LCD timing profile")
    pixel = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
    base = tuple((name, launch, "clk_sys" if name in ("pix_ready_sys", "ack_sys") else pixel)
                 for name, launch in zip(CHAINS, LAUNCHES))
    return base + (("blank_pix", "u_bridge|blank_requested", pixel),
                   ("blank_seen_sys", "u_bridge|blank_active", "clk_sys")) if lcd else base


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


def constraints(quote, *, lcd=False):
    lines = []
    for name, launch, _ in chain_profile(lcd):
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


def required_reports(*, lcd=False):
    names = ([f"{name}_{check}" for name, _, _ in chain_profile(lcd) for check in ("setup", "hold")]
             + [source for source, _, _ in BUNDLES] + ["outputs_max", "outputs_min", "skew"])
    if lcd:
        names += [f"blank_{name}_gray{bit}_{check}" for name, _ in BLANK_CONTROLS
                  for bit in range(12) for check in ("setup", "hold")]
    return [f"vga_{corner}_{name}.rpt" for corner, _, _ in CORNERS for name in names] + ["vga_first_pins.rpt"]


def physical_register(bit, register, quote):
    """Keep Quartus collection identity and disable automatic replica expansion."""
    return [f"set vga_gray_{bit} [get_registers -no_duplicates {quote(register)}]",
            f'if {{[get_collection_size $vga_gray_{bit}] != 1}} {{error "VGA physical output mismatch: gray{bit}"}}',
            f"foreach_in_collection r $vga_gray_{bit} {{",
            "set n [get_register_info -name $r]",
            r"regsub -all {(^|[|])[^|:]+:} $n {\1} n",
            f'if {{$n ne {quote(register)}}} {{error "VGA physical output name mismatch: gray{bit}"}}',
            "}"]


def audit(quote, *, lcd=False):
    lines = ['set vga_first_report [open output/vga_first_pins.rpt w]']
    for name, _, _ in chain_profile(lcd):
        lines += first_pin(name, quote)
        lines.append(f'foreach_in_collection p $first_{name} {{puts $vga_first_report "{name} [get_pin_info -name $p]"}}')
    lines.append("close $vga_first_report")
    for source, capture, width in BUNDLES:
        lines += collection("registers", [f"u_bridge|{source}[{i}]" for i in range(width)], source, quote)
        lines += collection("registers", [f"u_bridge|{capture}[{i}]" for i in range(width)], capture, quote)
    lines += collection("ports", PORTS, "vga_outputs", quote)
    if lcd:
        for name, launch in BLANK_CONTROLS:
            lines += collection("registers", [launch], "vga_blank_" + name, quote)
        # -no_duplicates disables implicit replica expansion; each explicitly
        # named physical replica remains its own checked collection.
        for bit, register in enumerate(RGB_REGISTERS):
            lines += physical_register(bit, register, quote)
    # -multi_corner does not provide all file-output corners for these commands.
    for corner, model, temperature in CORNERS:
        lines += [f"set_operating_conditions -model {model} -voltage 1200 -temperature {temperature}",
                  "update_timing_netlist"]
        for name, _, _ in chain_profile(lcd):
            for i in (0, 1):
                lines += collection("registers", [f"u_bridge|{name}[{i}]"], f"vga_chain_{i}", quote)
            for check in ("setup", "hold"):
                lines.append(f"report_timing -from $vga_chain_0 -to $vga_chain_1 -{check} -npaths 1 -detail full_path -file output/vga_{corner}_{name}_{check}.rpt")
        for source, capture, width in BUNDLES:
            # Each captured bit needs a path, not only the easiest bus member.
            lines.append(f"report_path -from ${source} -to ${capture} -npaths {width} -nworst 1 -file output/vga_{corner}_{source}.rpt")
        for name, option in (("max", ""), ("min", "-min_path")):
            lines.append(f"report_path -to $vga_outputs -npaths 14 -nworst 1 {option} -file output/vga_{corner}_outputs_{name}.rpt")
        if lcd:
            for name, _ in BLANK_CONTROLS:
                for bit in range(12):
                    for check in ("setup", "hold"):
                        lines.append(f"report_timing -from $vga_blank_{name} -to $vga_gray_{bit} -{check} -npaths 1 -detail full_path -file output/vga_{corner}_blank_{name}_gray{bit}_{check}.rpt")
        lines.append(f"report_max_skew -npaths 14 -detail full_path -file output/vga_{corner}_skew.rpt")
    return "\n".join(lines) + "\n"


def verify_memory_netlist(text, *, lcd=False, controls=False):
    """Check the fitted MAX 10 atoms, including clocks and one-edge read shape."""
    atoms = re.findall(r"fiftyfivenm_ram_block\s+\\(\S+)\s*\((.*?)\);", text, re.DOTALL)
    if controls:
        atoms = [(name, body) for name, body in atoms if name.startswith('u_bridge|')]
    if len(atoms) != 18 or len({name for name, _ in atoms}) != 18:
        raise ValueError("VGA physical RAM atom inventory differs")
    bits = {bank: [] for bank in range(3)}
    evidence = {}
    for name, body in atoms:
        owner = re.fullmatch(r"u_bridge\|banks\[([0-2])\]\.u_ram\|u_storage\|ram\|auto_generated\|ram_block1a[0-5]", name)
        if not owner:
            raise ValueError("unexpected VGA physical RAM owner")
        bank = int(owner[1])
        ports = {key: re.sub(r"\s+", "", value) for key, value in
                 re.findall(r"\.(\w+)\((.*?)\)(?:,|$)", body, re.DOTALL)}
        params = {key: value.strip().strip('"') for key, value in
                  re.findall(r"defparam\s+\\" + re.escape(name) + r"\s+\.(\w+)\s*=\s*(.*?);", text)}
        expected = {"operation_mode": "bidir_dual_port", "ram_block_type": "M9K",
                    "power_up_uninitialized": "true", "mixed_port_feed_through_mode": "dont_care",
                    "port_b_address_clock": "clock1", "port_b_read_enable_clock": "clock1"}
        for port in ("a", "b"):
            expected.update({f"port_{port}_logical_ram_depth": "23040", f"port_{port}_logical_ram_width": "2",
                             f"port_{port}_data_out_clock": "none", f"port_{port}_address_clear": "none",
                             f"port_{port}_data_out_clear": "none", f"port_{port}_data_width": "1",
                             f"port_{port}_address_width": "13", f"port_{port}_first_address": "0",
                             f"port_{port}_last_address": "8191",
                             f"port_{port}_read_during_write_mode": "new_data_with_nbe_read"})
        if any(params.get(key) != value for key, value in expected.items()):
            raise ValueError("VGA physical RAM parameters differ")
        if any(key.startswith(("mem_init", "init_file")) for key in params):
            raise ValueError("VGA physical RAM initialization unexpectedly present")
        expected_ports = {"clk0": r"\clk_sys~inputclkctrl_outclk",
                          "clk1": r"\u_clocking|u_pll|altpll_component|auto_generated|wire_pll1_clk[0]~clkctrl_outclk",
                          "clr0": "gnd", "clr1": "gnd", "portare": "gnd", "portbwe": "gnd",
                          "portaaddrstall": "gnd", "portbaddrstall": "gnd",
                          "portabyteenamasks": "1'b1", "portbbyteenamasks": "1'b1"}
        if any(ports.get(key) != value for key, value in expected_ports.items()):
            raise ValueError("VGA physical RAM clocks, read/write roles or reset differ")
        first = params.get("port_a_first_bit_number")
        if first not in ("0", "1") or params.get("port_b_first_bit_number") != first:
            raise ValueError("VGA physical RAM bit identity differs")
        expected_input = "{\\u_ppu|source_shade[" + first + "]}"
        input_matches = ports.get("portadatain") == expected_input if lcd else bool(
            re.fullmatch(r"\{\\shade\[" + first + r"\]~\d+_combout\}", ports.get("portadatain", "")))
        if not input_matches:
            raise ValueError("VGA physical RAM input shade bit differs")
        bits[bank].append(int(first))
        evidence[name] = {"ports": ports, "parameters": params}
    if any(sorted(partition) != [0, 0, 0, 1, 1, 1] for partition in bits.values()):
        raise ValueError("VGA physical RAM bit partition differs")
    return evidence


def verify(folder, *, lcd=False, controls=False):
    output = folder / "output"
    reports = {}
    for name in required_reports(lcd=lcd):
        path = output / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"missing VGA evidence: {name}")
        reports[name] = path.read_text(encoding="utf-8")
    pins = reports["vga_first_pins.rpt"].splitlines()
    if len(pins) != len(chain_profile(lcd)):
        raise ValueError("incomplete VGA first-pin inventory")
    for (name, _, _), line in zip(chain_profile(lcd), pins):
        if line not in [f"{name} u_bridge|{name}[0]|{suffix}" for suffix in ("d", "asdata")]:
            raise ValueError("unsupported VGA first data pin")
    fit = (output / "design.fit.rpt").read_text(encoding="cp1252" if os.name == "nt" else "utf-8")
    if [row[1] for row in rows(fit) if len(row) == 2 and row[0] == "M9Ks"] != (["27 / 182 ( 15 % )"] if controls else ["18 / 182 ( 10 % )"]):
        raise ValueError("unexpected total fitted M9K usage")
    memory = [row[1] for row in rows(fit) if len(row) == 2 and row[0] == "Total block memory bits"]
    if memory != (["181,744 / 1,677,312 ( 11 % )"] if controls else ["138,240 / 1,677,312 ( 8 % )"]):
        raise ValueError("unexpected total fitted memory bits")
    ram_rows = [row for row in rows(fit) if len(row) > 4 and row[1:4] == ["M9K", "True Dual Port", "Dual Clocks"]]
    expected_banks = {f"u_bridge|banks[{i}].u_ram|u_storage|ram|auto_generated|ALTSYNCRAM" for i in range(3)}
    if len(ram_rows) != 3 or {node(row[0]) for row in ram_rows} != expected_banks:
        raise ValueError("missing or extra fitted dual-clock VGA RAM banks")
    for row in ram_rows:
        if len(row) != 27 or row[4:18] != ["23040", "2", "23040", "2", "yes", "no", "yes", "no", "46080", "23040", "2", "23040", "2", "46080"] or row[18] != "6" or row[19] != "None" or row[21:] != ["Don't care", "New data with NBE Read", "New data with NBE Read", "Off", "No", "No - Unknown"]:
            raise ValueError("VGA RAM dimensions, registers, M9K usage or initialization differ")
    netlist = (folder / "simulation/questa/design.vo").read_text(encoding="utf-8")
    uart_ram = None
    if controls:
        from .fpga_controls import verify_uart_memory
        uart_ram = verify_uart_memory(netlist, fit)
    physical_ram = verify_memory_netlist(netlist, lcd=lcd, controls=controls)
    result = {"physical_ram": physical_ram, "ram_banks": 3, "memory_bits": 138240, "m9k_blocks": 18, "first_pins": pins, "corners": {}}
    if uart_ram is not None:
        result['uart_memory'] = uart_ram
    output_sources = dict(zip(PORTS, OUTPUT_REGISTERS))
    packed = [row for row in rows(fit) if len(row) > 6 and row[1:3] == ["Packed Register", "Register Packing"]
              and node(row[0]) in OUTPUT_REGISTERS]
    if len(packed) != 14 or {(node(row[0]), row[6]) for row in packed} != {
            (register, port + "~output") for port, register in output_sources.items()}:
        raise ValueError("VGA packed output register mapping differs")
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
            if {row[2] for row in paths} != set(PORTS) or any(node(row[1]) != output_sources.get(row[2]) for row in paths):
                raise ValueError("VGA output path inventory differs")
            delays = [number(row[0]) for row in paths]
            if any(value < 0 or value > 10 for value in delays):
                raise ValueError("VGA output datapath outside 0..10 ns")
            output_delays[direction] = max(delays) if direction == "max" else min(delays)
        if output_delays["max"] - output_delays["min"] > 2:
            raise ValueError("VGA complete output path spread exceeds 2 ns")
        blank_slacks = {}
        if lcd:
            pixel_clock = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
            for name, launch in BLANK_CONTROLS:
                for bit in range(12):
                    for check in ("setup", "hold"):
                        key = f"blank_{name}_gray{bit}_{check}"
                        text = reports[prefix + key + ".rpt"]
                        if not re.search(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)", text):
                            raise ValueError("missing or violated VGA blank control path")
                        paths = [row for row in rows(summary(text)) if len(row) == 8 and row[0] != "Slack"]
                        if len(paths) != 1 or [node(v) for v in paths[0][1:3]] != [launch, RGB_REGISTERS[bit]] or paths[0][3:5] != [pixel_clock, pixel_clock] or number(paths[0][0]) < 0:
                            raise ValueError("VGA blank control path differs")
                        blank_slacks[key] = number(paths[0][0])
        skews = rows(summary(reports[prefix + "skew.rpt"]))
        assignment = [row for row in skews if row[0] == "set_max_skew"]
        port_filter = "[get_ports {" + " ".join("{" + p + "}" if "[" in p else p for p in PORTS) + "}]"
        if len(assignment) != 1 or len(assignment[0]) != 9 or assignment[0][4] or assignment[0][5] != port_filter:
            raise ValueError("VGA skew constraint inventory differs")
        details = [row for row in skews if row[0] == "--"]
        if len(details) != 28 or not re.search(r"Report Max Skew: Found 28 paths \(0 violated\)", reports[prefix + "skew.rpt"]):
            raise ValueError("missing or violated VGA skew paths")
        if not 0 <= number(assignment[0][3]) <= 2:
            raise ValueError("VGA aggregate skew exceeds required bound")
        for row in assignment + details:
            # Individual latest/earliest arrival contributions can be signed;
            # the assignment's aggregate is nonnegative. Never accept a bad
            # slack, out-of-bound magnitude or inconsistent slack equation.
            slack, actual = number(row[1]), number(row[3])
            if (row[2] != "2.000" or slack < 0 or abs(actual) > 2
                    or abs(slack - (2 - actual)) > 0.0011):
                raise ValueError("VGA skew exceeds required bound")
        for row in details:
            if len(row) != 9 or row[5] not in PORTS or node(row[4]) != output_sources.get(row[5]) or row[6] != row[7] or row[6] != "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]":
                raise ValueError("unexpected VGA skew path or clock")
        chain_slacks = {}
        for name, _, clock in chain_profile(lcd):
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
        if lcd:
            result["corners"][corner]["blank_control_slack_ns"] = blank_slacks
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
