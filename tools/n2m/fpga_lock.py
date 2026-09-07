"""Recognize only the documented MAX 10 ALTPLL locked-output event latch."""
import re

PLL = "u_clocking|u_pll|altpll_component|auto_generated|"
RESET = "u_clocking|u_reset|"
ROW = "n2m_clocking:u_clocking|n2m_pixel_pll:u_pll|altpll:altpll_component|n2m_pixel_pll_altpll:auto_generated|pll_lock_sync"
OUTPUTS = {
    "dffeas": {"q"}, "fiftyfivenm_lcell_comb": {"combout", "cout"},
    "fiftyfivenm_clkctrl": {"outclk"}, "fiftyfivenm_io_ibuf": {"o"}, "fiftyfivenm_io_obuf": {"o", "obar"},
    "fiftyfivenm_pll": {"locked", "clk", "fbout", "phasedone", "scandataout", "scandone", "activeclock", "vcooverrange", "vcounderrange", "clkbad"},
    "fiftyfivenm_adcblock": {"eoc", "dout"}, "fiftyfivenm_unvm": {"busy", "osc", "bgpbusy", "sp_pass", "se_pass", "drdout"},
    "fiftyfivenm_ram_block": {"portadataout", "portbdataout"},
}


def parse_netlist(text, top):
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"(?m)^\s*`timescale[^\n]*", "", text)
    cells = {}
    assignments = []
    assigned_nets = []
    declarations = []
    parameters = {}
    # Consume every statement. Unknown syntax cannot silently hide another sink.
    for statement in text.split(";"):
        statement = statement.strip()
        if not statement or statement == "endmodule":
            continue
        if re.fullmatch(r"module\s+" + re.escape(top) + r"\s*\([A-Za-z0-9_,\s]+\)", statement):
            continue
        if re.fullmatch(r"(?:input|output|wire|tri0|tri1)\s+(?:\[\d+:\d+\]\s*)?(?:\\[^\s]+\s*(?:\[\d+\])?|[A-Za-z_]\w*)", statement):
            declarations.append(" ".join(statement.split()))
            continue
        param = re.fullmatch(r"defparam\s+(?:\\([^\s]+)\s+|([A-Za-z_]\w*)\s*)\.(\w+)\s*=\s*(\"[^\"]*\"|[A-Za-z0-9_'.+-]+)", statement)
        if param:
            escaped, plain, key, value = param.groups()
            owner = escaped or plain
            values = parameters.setdefault(owner, {})
            if key in values:
                raise ValueError("duplicate primitive parameter")
            values[key] = value
            continue
        assignment = re.fullmatch(r"assign\s+([^=]+)=(.+)", statement, re.S)
        if assignment:
            assigned_nets.append(re.sub(r"\s", "", assignment[1]))
            assignments.append(re.sub(r"\s", "", assignment[2]))
            continue
        match = re.fullmatch(r"(\w+)\s+(?:\\(\S+)\s+|([A-Za-z_]\w*)\s*)\((.*)\)", statement, re.S)
        if not match:
            raise ValueError(f"unsupported structural netlist statement: {statement[:80]}")
        kind, escaped, plain, body = match.groups()
        if kind not in OUTPUTS:
            raise ValueError("unsupported vendor primitive type")
        name = escaped or plain
        if name in cells:
            raise ValueError("duplicate netlist cell")
        connections = re.findall(r"\.(\w+)\(([^()]*)\)", body)
        remainder = re.sub(r"\.(\w+)\(([^()]*)\)", "", body)
        if re.sub(r"[\s,]", "", remainder) or len({p for p, _ in connections}) != len(connections):
            raise ValueError("unsupported or duplicate netlist connection")
        ports = {key: re.sub(r"\s", "", value) for key, value in connections}
        cells[name] = (kind, ports)

    for constant, declaration in {"gnd": "wire gnd", "vcc": "wire vcc", "devclrn": "tri1 devclrn", "devpor": "tri1 devpor"}.items():
        if re.search(r"\\" + constant + r"\s", text) or [d for d in declarations if re.search(r"\b" + constant + r"$", d)] != [declaration]:
            raise ValueError("vendor constant declaration differs")
        values = [(lhs, rhs) for lhs, rhs in zip(assigned_nets, assignments) if re.search(r"\b" + constant + r"\b", lhs)]
        if values != ([(constant, "1'b0")] if constant == "gnd" else [(constant, "1'b1")] if constant == "vcc" else []):
            raise ValueError("vendor constant assignment differs")
        if any(re.search(r"\b" + constant + r"\b", value) for kind, ports in cells.values() for port, value in ports.items()
               if port in OUTPUTS[kind]):
            raise ValueError("vendor constant has a primitive driver")

    return text, cells, parameters, declarations, assignments, assigned_nets


def verify(text, checks, top="clocking_proof"):
    if top not in ("clocking_proof", "vga_proof", "ppu_proof", "intel_memory_proof"):
        raise ValueError("unsupported PLL proof top")
    rows = re.findall(r";\s*([^;\r\n]+?)\s*;\s*No clock feeds this register's clock port\.\s*;", checks)
    if rows != [ROW]:
        raise ValueError("unrecognized no-clock endpoint")
    text, cells, parameters, declarations, assignments, assigned_nets = parse_netlist(text, top)

    def cell(name, kind):
        if name not in cells or cells[name][0] != kind:
            raise ValueError(f"vendor lock topology missing {name}")
        return cells[name][1]

    def parameter(name, key):
        if key not in parameters.get(name, {}):
            raise ValueError("missing or duplicate vendor lock parameter")
        return parameters[name][key]

    # Exact supported overrides close over the installed primitive model's defaults.
    # In particular, LUT cin mode and registered clock enables change behavior.
    def modes(name, expected):
        if parameters.get(name) != expected:
            raise ValueError(f"unsupported primitive parameter set: {name}")

    def users(net):
        result = {(name, port) for name, (kind, ports) in cells.items() for port, value in ports.items()
                  if port not in OUTPUTS[kind] and net in value}
        result |= {(f"assign-{i}", "rhs") for i, rhs in enumerate(assignments) if net in rhs}
        return result

    pll = cell(PLL + "pll1", "fiftyfivenm_pll")
    ff = cell(PLL + "pll_lock_sync", "dffeas")
    modes(PLL + "pll_lock_sync", {"is_wysiwyg": '"true"', "power_up": '"low"'})
    expected = {"clk": pll["locked"], "d": "\\" + PLL + "pll_lock_sync~feeder_combout",
                "asdata": "vcc", "clrn": pll["areset"].removeprefix("!"), "aload": "gnd",
                "sclr": "gnd", "sload": "gnd", "ena": "vcc", "devclrn": "devclrn",
                "devpor": "devpor", "q": "\\" + PLL + "pll_lock_sync~q", "prn": "vcc"}
    if not pll["areset"].startswith("!") or ff != expected:
        raise ValueError("vendor lock event latch ports differ")
    if parameter(PLL + "pll_lock_sync", "power_up") != '"low"':
        raise ValueError("vendor lock event latch initialization differs")
    feeder = cell(PLL + "pll_lock_sync~feeder", "fiftyfivenm_lcell_comb")
    modes(PLL + "pll_lock_sync~feeder", {"lut_mask": "16'hFFFF", "sum_lutc_input": '"datac"'})
    if parameter(PLL + "pll_lock_sync~feeder", "lut_mask").lower() != "16'hffff" or feeder.get("combout") != ff["d"]:
        raise ValueError("vendor lock event latch D is not constant one")
    if any(feeder.get(p) != "gnd" for p in ("dataa", "datab", "datac", "datad", "cin")):
        raise ValueError("vendor lock constant feeder has unexpected inputs")

    # The latch clears from the very same reset as the PLL, with opposite polarity.
    reset_buffer = cell(RESET + "pll_areset~clkctrl", "fiftyfivenm_clkctrl")
    reset_ff = cell(RESET + "pll_areset", "dffeas")
    modes(RESET + "pll_areset", {"is_wysiwyg": '"true"', "power_up": '"low"'})
    modes(RESET + "pll_areset~clkctrl", {"clock_type": '"global clock"', "ena_register_mode": '"none"'})
    if (reset_buffer.get("outclk") != ff["clrn"] or reset_buffer.get("ena") != "vcc"
            or reset_buffer.get("clkselect") != "2'b00"
            or reset_buffer.get("inclk") != "{vcc,vcc,vcc," + reset_ff["q"] + "}"):
        raise ValueError("vendor lock reset source differs")

    gate_name = RESET + "lock_reset~0"
    gate = cell(gate_name, "fiftyfivenm_lcell_comb")
    mask = parameter(gate_name, "lut_mask")
    modes(gate_name, {"lut_mask": mask, "sum_lutc_input": '"datac"'})
    if not re.fullmatch(r"16'h[0-9A-Fa-f]{4}", mask):
        raise ValueError("invalid vendor lock gate truth table")
    mask = int(mask[4:], 16)
    for assignment in range(8):
        q, raw, released = [(assignment >> i) & 1 for i in range(3)]
        values = {ff["q"]: q, pll["locked"]: raw, reset_ff["q"]: released, "gnd": 0, "vcc": 1}
        try:
            address = sum(values[gate[port]] << i for i, port in enumerate(("dataa", "datab", "datac", "datad")))
        except KeyError as error:
            raise ValueError("vendor lock gate has unrelated inputs") from error
        if ((mask >> address) & 1) != (not (q and raw and released)):
            raise ValueError("vendor lock gate no longer propagates raw lock loss")
    q_users = users(ff["q"])
    raw_users = users(pll["locked"])
    if len(q_users) != 1 or {name for name, _ in q_users} != {gate_name}:
        raise ValueError("vendor lock latch has non-lock fanout")
    if raw_users != {(PLL + "pll_lock_sync", "clk")} | {(gate_name, p) for p, v in gate.items() if v == pll["locked"]}:
        raise ValueError("raw PLL lock has unexpected fanout")
    gate_buffer_name = RESET + "lock_reset~0clkctrl"
    gate_buffer = cell(gate_buffer_name, "fiftyfivenm_clkctrl")
    modes(gate_buffer_name, {"clock_type": '"global clock"', "ena_register_mode": '"none"'})
    if (gate_buffer.get("inclk") != "{vcc,vcc,vcc," + gate["combout"] + "}"
            or gate_buffer.get("clkselect") != "2'b00" or gate_buffer.get("ena") != "vcc"
            or users(gate["combout"]) != {(gate_buffer_name, "inclk")}):
        raise ValueError("lock-only reset fanout differs")
    sample_names = {RESET + f"lock_samples[{i}]" for i in (0, 1)}
    if users(gate_buffer["outclk"]) != {(name, "clrn") for name in sample_names}:
        raise ValueError("vendor lock drives a functional datapath")
    for name in sample_names:
        sample = cell(name, "dffeas")
        modes(name, {"is_wysiwyg": '"true"', "power_up": '"low"'})
        if sample.get("clrn") != "!" + gate_buffer["outclk"] or sample.get("clk") != reset_ff["clk"]:
            raise ValueError("lock sampling reset or system clock differs")
    critical_drivers = [(pll["locked"], PLL + "pll1", "locked"), (ff["q"], PLL + "pll_lock_sync", "q"),
                        (ff["d"], PLL + "pll_lock_sync~feeder", "combout"),
                        (ff["clrn"], RESET + "pll_areset~clkctrl", "outclk"),
                        (reset_ff["q"], RESET + "pll_areset", "q"), (gate["combout"], gate_name, "combout"),
                        (gate_buffer["outclk"], gate_buffer_name, "outclk")]
    for net, expected_name, expected_port in critical_drivers:
        drivers = {(name, port) for name, (kind, ports) in cells.items() for port, value in ports.items()
                   if port in OUTPUTS[kind] and net in value}
        if drivers != {(expected_name, expected_port)} or any(net in lhs for lhs in assigned_nets):
            raise ValueError("vendor lock net has additional drivers")
    return {"endpoint": ROW, "classification": "documented ALTPLL lock event latch",
            "topology": "constant-one D; PLL reset clears; raw lock loss propagates; only reset sampling fanout"}
