"""Exact VGA proof hierarchy: checked CDC collections and retained path reports."""
import collections
import math
import re

from .fpga_clocking import FIT_ENCODING

CHAINS = ("pix_ready_sys", "sys_ready_pix", "ack_sys", "req_pix")
LAUNCHES = ("u_clocking|u_reset|pix_release[1]", "u_clocking|u_reset|sys_release[1]",
            "u_bridge|acknowledge", "u_bridge|request")
BUNDLES = (("offer_bank", "captured_bank", 2),
           ("offer_sequence", "captured_sequence", 64),
           ("offer_epoch", "captured_epoch", 32))
# One board's checked VGA outputs: its RGB and sync pins, the physical register
# the fitter packs into each, and the fitted RAM atom its device family names.
Profile = collections.namedtuple("Profile", "ports registers atom")


def profile(channels, width, sync, *, atom="fiftyfivenm_ram_block"):
    """A board's output profile from its channel names, channel width and sync pins.

    `n2m_vga_scan` builds every channel by repeating the two-bit `gray_out` pair,
    so channel bit k carries `gray_out[k % 2]` however wide the channel is, and
    the fitter packs one physical copy of that register into each pin: the
    original plus a duplicate for every further pin of the same bit. The width
    and the names are the board's; that rule and every check below are not.
    """
    pins = [f"{name}[{bit}]" for name in channels for bit in range(width)]
    rgb = tuple(f"u_bridge|u_scan|gray_out[{i % 2}]" + (f"~_Duplicate_{i // 2}" if i // 2 else "")
                for i in range(len(pins)))
    return Profile(pins + list(sync), rgb + tuple(f"u_bridge|u_scan|{name}" for name in ("hs_out", "vs_out")), atom)


# The DE10-Lite's four-bit resistor ladder, and the default every MAX 10 target
# keeps: twelve RGB pins, six physical copies of each grayscale bit.
LADDER = profile(("red", "green", "blue"), 4, ("hsync_n", "vsync_n"))
PORTS = LADDER.ports
RGB_REGISTERS = LADDER.registers[:-2]
OUTPUT_REGISTERS = LADDER.registers
BLANK_CONTROLS = (("active", "u_bridge|blank_active"), ("request", "u_bridge|blank_pix[1]"))
CORNERS = (("slow85", "slow", 85), ("slow0", "slow", 0), ("fast0", "fast", 0))
# The fitted net the pixel clock reaches the fabric on, as the checked netlist
# names it. The hierarchy is the shared clocking wrapper's, so both ALTPLL
# families name it the same way.
PIXEL_NET = r"\u_clocking|u_pll|altpll_component|auto_generated|wire_pll1_clk[0]~clkctrl_outclk"


def chain_profile(lcd=False, *, system_clock="clk_sys"):
    if type(lcd) is not bool:
        raise ValueError("invalid VGA LCD timing profile")
    pixel = "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]"
    base = tuple((name, launch, system_clock if name in ("pix_ready_sys", "ack_sys") else pixel)
                 for name, launch in zip(CHAINS, LAUNCHES))
    return base + (("blank_pix", "u_bridge|blank_requested", pixel),
                   ("blank_seen_sys", "u_bridge|blank_active", system_clock)) if lcd else base


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


def constraints(quote, *, lcd=False, outputs=LADDER):
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
    lines += collection("ports", outputs.ports, "vga_outputs", quote)
    lines += ["set_max_delay 10.000 -to $vga_outputs", "set_min_delay 0.000 -to $vga_outputs",
              "set_max_skew -to $vga_outputs 2.000"]
    return "\n".join(lines) + "\n"


def required_reports(*, lcd=False, outputs=LADDER):
    names = ([f"{name}_{check}" for name, _, _ in chain_profile(lcd) for check in ("setup", "hold")]
             + [source for source, _, _ in BUNDLES] + ["outputs_max", "outputs_min", "skew"])
    if lcd:
        names += [f"blank_{name}_gray{bit}_{check}" for name, _ in BLANK_CONTROLS
                  for bit in range(len(outputs.registers) - 2) for check in ("setup", "hold")]
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


def audit(quote, *, lcd=False, outputs=LADDER):
    lines = ['set vga_first_report [open output/vga_first_pins.rpt w]']
    for name, _, _ in chain_profile(lcd):
        lines += first_pin(name, quote)
        lines.append(f'foreach_in_collection p $first_{name} {{puts $vga_first_report "{name} [get_pin_info -name $p]"}}')
    lines.append("close $vga_first_report")
    for source, capture, width in BUNDLES:
        lines += collection("registers", [f"u_bridge|{source}[{i}]" for i in range(width)], source, quote)
        lines += collection("registers", [f"u_bridge|{capture}[{i}]" for i in range(width)], capture, quote)
    lines += collection("ports", outputs.ports, "vga_outputs", quote)
    if lcd:
        for name, launch in BLANK_CONTROLS:
            lines += collection("registers", [launch], "vga_blank_" + name, quote)
        # -no_duplicates disables implicit replica expansion; each explicitly
        # named physical replica remains its own checked collection.
        for bit, register in enumerate(outputs.registers[:-2]):
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
            lines.append(f"report_path -to $vga_outputs -npaths {len(outputs.ports)} -nworst 1 {option} -file output/vga_{corner}_outputs_{name}.rpt")
        if lcd:
            for name, _ in BLANK_CONTROLS:
                for bit in range(len(outputs.registers) - 2):
                    for check in ("setup", "hold"):
                        lines.append(f"report_timing -from $vga_blank_{name} -to $vga_gray_{bit} -{check} -npaths 1 -detail full_path -file output/vga_{corner}_blank_{name}_gray{bit}_{check}.rpt")
        lines.append(f"report_max_skew -npaths {len(outputs.ports)} -detail full_path -file output/vga_{corner}_skew.rpt")
    return "\n".join(lines) + "\n"


def verify_memory_netlist(text, *, lcd=False, controls=False, system_net=r"\clk_sys~inputclkctrl_outclk", bridge_prefix="u_bridge|", shade="u_ppu|source_shade", atom=LADDER.atom):
    """Check the fitted atoms, including clocks and one-edge read shape.

    Only the atom's name follows the device family: MAX 10 fits
    `fiftyfivenm_ram_block` and Cyclone IV E `cycloneive_ram_block` for the same
    M9K block. Everything checked below -- the owners, the parameter set, the
    clock and reset roles, the shade bit and the bit partition -- is the design's
    and is stated once.
    """
    atoms = re.findall(re.escape(atom) + r"\s+\\(\S+)\s*\((.*?)\);", text, re.DOTALL)
    if controls or bridge_prefix != "u_bridge|":
        atoms = [(name, body) for name, body in atoms if name.startswith(bridge_prefix)]
    if len(atoms) != 18 or len({name for name, _ in atoms}) != 18:
        raise ValueError("VGA physical RAM atom inventory differs")
    bits = {bank: [] for bank in range(3)}
    evidence = {}
    for name, body in atoms:
        owner = re.fullmatch(re.escape(bridge_prefix) + r"banks\[([0-2])\]\.u_ram\|u_storage\|ram\|auto_generated\|ram_block1a[0-5]", name)
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
        expected_ports = {"clk0": system_net, "clk1": PIXEL_NET,
                          "clr0": "gnd", "clr1": "gnd", "portare": "gnd", "portbwe": "gnd",
                          "portaaddrstall": "gnd", "portbaddrstall": "gnd",
                          "portabyteenamasks": "1'b1", "portbbyteenamasks": "1'b1"}
        if any(ports.get(key) != value for key, value in expected_ports.items()):
            raise ValueError("VGA physical RAM clocks, read/write roles or reset differ")
        first = params.get("port_a_first_bit_number")
        if first not in ("0", "1") or params.get("port_b_first_bit_number") != first:
            raise ValueError("VGA physical RAM bit identity differs")
        expected_input = "{\\" + shade + "[" + first + "]}"
        input_matches = ports.get("portadatain") == expected_input if lcd else bool(
            re.fullmatch(r"\{\\shade\[" + first + r"\]~\d+_combout\}", ports.get("portadatain", "")))
        if not input_matches:
            raise ValueError("VGA physical RAM input shade bit differs")
        bits[bank].append(int(first))
        evidence[name] = {"ports": ports, "parameters": params}
    if any(sorted(partition) != [0, 0, 0, 1, 1, 1] for partition in bits.values()):
        raise ValueError("VGA physical RAM bit partition differs")
    return evidence


USED = re.compile(r"([\d,]+) / [\d,]+ \( *\d+ % \)")


def used(table, label):
    """The used count of one `used / capacity ( percent )` fit summary row.

    The capacity and the percent it implies are facts about the device, which the
    fit summary already binds through its `Device :` line, so the used count is
    the whole subject here. That keeps the check on the fitted design and lets a
    larger part with the same M9K block reuse it rather than restate a capacity.
    """
    values = [row[1] for row in table if len(row) == 2 and row[0] == label]
    match = USED.fullmatch(values[0]) if len(values) == 1 else None
    if match is None:
        raise ValueError(f"missing or malformed fitted usage row: {label}")
    return int(match[1].replace(",", ""))


def verify(folder, *, lcd=False, controls=False, system_clock="clk_sys", system_net=r"\clk_sys~inputclkctrl_outclk", outputs=LADDER):
    output = folder / "output"
    reports = {}
    for name in required_reports(lcd=lcd, outputs=outputs):
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
    fit = (output / "design.fit.rpt").read_text(encoding=FIT_ENCODING)
    if used(rows(fit), "M9Ks") != (27 if controls else 18):
        raise ValueError("unexpected total fitted M9K usage")
    if used(rows(fit), "Total block memory bits") != (181744 if controls else 138240):
        raise ValueError("unexpected total fitted memory bits")
    verify_memory_rows(fit)
    netlist = (folder / "simulation/questa/design.vo").read_text(encoding="utf-8")
    uart_ram = None
    if controls:
        from .fpga_controls import verify_uart_memory
        uart_ram = verify_uart_memory(netlist, fit, system_net=system_net)
    physical_ram = verify_memory_netlist(netlist, lcd=lcd, controls=controls, system_net=system_net, atom=outputs.atom)
    result = {"physical_ram": physical_ram, "ram_banks": 3, "memory_bits": 138240, "m9k_blocks": 18, "first_pins": pins, "corners": {}}
    if uart_ram is not None:
        result['uart_memory'] = uart_ram
    output_sources = dict(zip(outputs.ports, outputs.registers))
    packed = [row for row in rows(fit) if len(row) > 6 and row[1:3] == ["Packed Register", "Register Packing"]
              and node(row[0]) in outputs.registers]
    if len(packed) != len(outputs.ports) or {(node(row[0]), row[6]) for row in packed} != {
            (register, port + "~output") for port, register in output_sources.items()}:
        raise ValueError("VGA packed output register mapping differs")
    result["corners"] = verify_paths(reports, lcd=lcd, system_clock=system_clock, outputs=outputs)
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


def verify_paths(reports, *, lcd=False, system_clock="clk_sys", bridge_prefix="u_bridge|", outputs=LADDER):
    """Check the same path contracts in the standalone and composed hierarchy."""
    def path_node(value):
        value = node(value)
        return "u_bridge|" + value[len(bridge_prefix):] if value.startswith(bridge_prefix) else value
    pins = reports["vga_first_pins.rpt"].splitlines()
    if len(pins) != len(chain_profile(lcd)):
        raise ValueError("incomplete VGA first-pin inventory")
    for (name, _, _), line in zip(chain_profile(lcd), pins):
        if line not in [f"{name} {bridge_prefix}{name}[0]|{suffix}" for suffix in ("d", "asdata")]:
            raise ValueError("unsupported VGA first data pin")
    output_sources = dict(zip(outputs.ports, outputs.registers))
    result = {}
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
            if {(path_node(row[1]), path_node(row[2])) for row in paths} != expected:
                raise ValueError("VGA bundle path inventory differs")
            delay = max(number(row[0]) for row in paths)
            if delay > 20:
                raise ValueError("VGA bundle datapath exceeds 20 ns")
            bundles[source] = delay
        output_delays = {}
        for direction in ("max", "min"):
            paths = path_rows(reports[prefix + "outputs_" + direction + ".rpt"], len(outputs.ports))
            if {row[2] for row in paths} != set(outputs.ports) or any(path_node(row[1]) != output_sources.get(row[2]) for row in paths):
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
                for bit in range(len(outputs.registers) - 2):
                    for check in ("setup", "hold"):
                        key = f"blank_{name}_gray{bit}_{check}"
                        text = reports[prefix + key + ".rpt"]
                        if not re.search(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)", text):
                            raise ValueError("missing or violated VGA blank control path")
                        paths = [row for row in rows(summary(text)) if len(row) == 8 and row[0] != "Slack"]
                        if len(paths) != 1 or [path_node(v) for v in paths[0][1:3]] != [launch, outputs.registers[bit]] or paths[0][3:5] != [pixel_clock, pixel_clock] or number(paths[0][0]) < 0:
                            raise ValueError("VGA blank control path differs")
                        blank_slacks[key] = number(paths[0][0])
        skews = rows(summary(reports[prefix + "skew.rpt"]))
        assignment = [row for row in skews if row[0] == "set_max_skew"]
        port_filter = "[get_ports {" + " ".join("{" + p + "}" if "[" in p else p for p in outputs.ports) + "}]"
        if len(assignment) != 1 or len(assignment[0]) != 9 or assignment[0][4] or assignment[0][5] != port_filter:
            raise ValueError("VGA skew constraint inventory differs")
        details = [row for row in skews if row[0] == "--"]
        # One latest and one earliest arrival contribution per checked output pin.
        expected_paths = 2 * len(outputs.ports)
        if len(details) != expected_paths or not re.search(r"Report Max Skew: Found " + str(expected_paths) + r" paths \(0 violated\)", reports[prefix + "skew.rpt"]):
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
            if len(row) != 9 or row[5] not in outputs.ports or path_node(row[4]) != output_sources.get(row[5]) or row[6] != row[7] or row[6] != "u_clocking|u_pll|altpll_component|auto_generated|pll1|clk[0]":
                raise ValueError("unexpected VGA skew path or clock")
        chain_slacks = {}
        for name, _, clock in chain_profile(lcd, system_clock=system_clock):
            for check in ("setup", "hold"):
                text = reports[prefix + name + "_" + check + ".rpt"]
                if not re.search(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)", text):
                    raise ValueError("missing or violated VGA synchronizer path")
                paths = [row for row in rows(summary(text)) if len(row) == 8 and row[0] != "Slack"]
                if len(paths) != 1 or [path_node(v) for v in paths[0][1:3]] != [f"u_bridge|{name}[0]", f"u_bridge|{name}[1]"] or paths[0][3:5] != [clock, clock] or number(paths[0][0]) < 0:
                    raise ValueError("VGA synchronizer path differs")
                chain_slacks[name + "_" + check] = number(paths[0][0])
        result[corner] = {"bundle_max_ns": bundles, "outputs_ns": output_delays,
                                     "skew_ns": number(assignment[0][3]), "chain_slack_ns": chain_slacks}
        if lcd:
            result[corner]["blank_control_slack_ns"] = blank_slacks
    return result


def verify_memory_rows(fit, *, bridge_prefix="u_bridge|"):
    ram_rows = [row for row in rows(fit) if len(row) > 4 and row[1:4] == ["M9K", "True Dual Port", "Dual Clocks"]]
    expected_banks = {f"{bridge_prefix}banks[{i}].u_ram|u_storage|ram|auto_generated|ALTSYNCRAM" for i in range(3)}
    if len(ram_rows) != 3 or {node(row[0]) for row in ram_rows} != expected_banks:
        raise ValueError("missing or extra fitted dual-clock VGA RAM banks")
    for row in ram_rows:
        if len(row) != 27 or row[4:18] != ["23040", "2", "23040", "2", "yes", "no", "yes", "no", "46080", "23040", "2", "23040", "2", "46080"] or row[18] != "6" or row[19] != "None" or row[21:] != ["Don't care", "New data with NBE Read", "New data with NBE Read", "Off", "No", "No - Unknown"]:
            raise ValueError("VGA RAM dimensions, registers, M9K usage or initialization differ")
    return ram_rows
