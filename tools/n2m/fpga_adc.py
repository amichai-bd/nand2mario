"""Resolve the installed ADC control core and generate its dedicated PLL."""
from pathlib import Path
import shutil
import re

from .records import file_hash
from . import fpga_pll
from .fpga_lock import parse_netlist, OUTPUTS

PLL = "u_adc|u_pll|altpll_component|auto_generated|"
FSM = "u_adc|u_control|u_control_fsm|"
SYS = r"\clk_sys~inputclkctrl_outclk"


def verify_netlist(text, checks, top="adc_proof", *, parallel=False, system_net=SYS):
    from .fpga_lock import ROW
    prefix = "u_controls|" if top == "v05_controls_proof" else ""
    pll_path, fsm_path = prefix + PLL, prefix + FSM
    if top not in ("adc_proof", "controls_proof", "v05_controls_proof"):
        raise ValueError("unsupported ADC proof top")
    reset = prefix + "u_adc_reset|" if top in ("controls_proof", "v05_controls_proof") else "u_reset|"
    row = ("n2m_controls_system:u_controls|" if prefix else "") + "n2m_adc_backend:u_adc|n2m_adc_pll:u_pll|altpll:altpll_component|n2m_adc_pll_altpll:auto_generated|pll_lock_sync"
    expected_rows = [ROW, row] if top in ("controls_proof", "v05_controls_proof") else [row]
    if parallel:
        expected_rows.append("n2m_clocking:u_clocking|n2m_system_pll:u_system_pll|altpll:altpll_component|n2m_system_pll_altpll:auto_generated|pll_lock_sync")
    actual_rows = re.findall(r";\s*([^;\r\n]+?)\s*;\s*No clock feeds this register's clock port\.\s*;", checks)
    if sorted(actual_rows) != sorted(expected_rows):
        raise ValueError("unexpected ADC no-clock endpoint")
    _, cells, params, declarations, rhs, lhs = parse_netlist(text, top)

    def cell(name, kind):
        if cells.get(name, (None,))[0] != kind:
            raise ValueError("missing ADC topology cell: " + name)
        return cells[name][1]

    def users(net):
        if any(net in expression for expression in rhs):
            raise ValueError("unexpected alias of ADC lock event")
        return {(name, port) for name, (kind, ports) in cells.items()
                for port, value in ports.items() if port not in OUTPUTS[kind] and net in value}

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def reset_buffer(name, source):
        ports = cell(name, "fiftyfivenm_clkctrl")
        require(ports == {"ena": "vcc", "inclk": "{vcc,vcc,vcc," + source + "}",
                         "clkselect": "2'b00", "devclrn": "devclrn", "devpor": "devpor",
                         "outclk": "\\" + name + "_outclk"}
                and params.get(name) == {"clock_type": '"global clock"', "ena_register_mode": '"none"'},
                "ADC reset buffer is not an always-enabled identity")
        return ports["outclk"]

    def register(name, reset, clock=None):
        clock = system_net if clock is None else clock
        ports = cell(name, "dffeas")
        require(ports.get("clk") == clock and ports.get("clrn") == reset and
                ports.get("prn") == "vcc" and ports.get("aload") == "gnd" and
                ports.get("sclr") == "gnd" and ports.get("devclrn") == "devclrn" and
                ports.get("devpor") == "devpor" and set(ports) ==
                {"clk", "clrn", "prn", "aload", "sclr", "sload", "ena", "d", "asdata", "q", "devclrn", "devpor"} and params.get(name) ==
                {"is_wysiwyg": '"true"', "power_up": '"low"'}, "ADC register clock/reset differs: " + name)
        return ports

    pll = cell(pll_path + "pll1", "fiftyfivenm_pll")
    event = register(pll_path + "pll_lock_sync", "\\" + reset + "pll_areset~clkctrl_outclk", pll["locked"])
    feeder = cell(pll_path + "pll_lock_sync~feeder", "fiftyfivenm_lcell_comb")
    require(params[pll_path + "pll_lock_sync~feeder"] == {"lut_mask": "16'hFFFF", "sum_lutc_input": '"datac"'} and
            event["d"] == feeder["combout"] and event["ena"] == "vcc" and event["sload"] == "gnd",
            "ADC lock event is not constant-one acquisition")
    require(pll["areset"] == "!" + event["clrn"], "ADC PLL/event reset differs")
    reset_gate = cell(reset + "lock_reset", "fiftyfivenm_lcell_comb")
    reset_ff = cell(reset + "pll_areset", "dffeas")
    require(reset_buffer(reset + "pll_areset~clkctrl", reset_ff["q"]) == event["clrn"],
            "ADC PLL reset buffer differs")
    raw, acquired = pll["locked"], event["q"]
    gate_specs = {
        reset + "lock_reset": ({raw, acquired, reset_ff["q"], "gnd"},
                              lambda v: not (v[raw] and v[acquired] and v[reset_ff["q"]])),
        fsm_path + "ctrl_state.IDLE~0": ({raw, acquired, "\\" + fsm_path + "ctrl_state.IDLE~q", "gnd"},
                                    lambda v: v["\\" + fsm_path + "ctrl_state.IDLE~q"] or (v[raw] and v[acquired])),
        fsm_path + "Selector1~1": ({raw, acquired, "\\" + fsm_path + "ctrl_state.IDLE~q", "\\" + fsm_path + "Selector1~0_combout"},
                             lambda v: v["\\" + fsm_path + "Selector1~0_combout"] or
                             (v[raw] and v[acquired] and not v["\\" + fsm_path + "ctrl_state.IDLE~q"]))}
    for name, (allowed, oracle) in gate_specs.items():
        gate = cell(name, "fiftyfivenm_lcell_comb")
        require(set(gate[p] for p in ("dataa", "datab", "datac", "datad")) == allowed,
                "ADC lock LUT inputs differ")
        mode = params[name]
        require(set(mode) == {"lut_mask", "sum_lutc_input"} and mode["sum_lutc_input"] == '"datac"', "ADC lock LUT mode differs")
        mask = int(mode["lut_mask"].removeprefix("16'h"), 16)
        variables = sorted(allowed - {"gnd"})
        for bits in range(1 << len(variables)):
            values = {net: (bits >> i) & 1 for i, net in enumerate(variables)} | {"gnd": 0}
            index = sum(values[gate[p]] << i for i, p in enumerate(("dataa", "datab", "datac", "datad")))
            require(bool((mask >> index) & 1) == bool(oracle(values)), "ADC lock LUT truth table differs")
    require(users(acquired) == {(n, p) for n in gate_specs for p, v in cells[n][1].items() if v == acquired}, "ADC event has extra fanout")
    require(users(raw) == {(pll_path + "pll_lock_sync", "clk")} |
            {(n, p) for n in gate_specs for p, v in cells[n][1].items() if v == raw}, "ADC raw lock has extra fanout")
    reset_net = reset_gate["combout"]
    ready_net = "\\" + reset + "ready~q"
    if top in ("controls_proof", "v05_controls_proof"):
        require(users(reset_net) == {(reset + "lock_reset~clkctrl", "inclk")},
                "ADC lock reset bypasses its buffer")
        reset_net = reset_buffer(reset + "lock_reset~clkctrl", reset_net)
        require(users(ready_net) == {(reset + "ready~clkctrl", "inclk"),
                                   (reset + "ready~0", "datac")},
                "ADC qualified ready has unexpected consumers")
        ready_net = reset_buffer(reset + "ready~clkctrl", ready_net)
        require(users(ready_net) == {(f"{reset}sys_release[{i}]", "clrn") for i in (0, 1)},
                "ADC qualified reset buffer has unexpected consumers")
    require(users(reset_net) == {(f"{reset}lock_samples[{i}]", "clrn") for i in (0, 1)}, "ADC reset gate has extra fanout")
    for i in (0, 1):
        register(f"{reset}lock_samples[{i}]", "!" + reset_net)
        register(f"{reset}sys_release[{i}]", ready_net)
    register(reset + "ready", "\\" + reset + "lock_samples[1]")
    for i in range(10):
        register(f"{reset}lock_count[{i}]", "\\" + reset + "lock_samples[1]")
    combinational_drivers = {}
    for name, (kind, ports) in cells.items():
        if kind == "fiftyfivenm_lcell_comb":
            for port in ("combout", "cout"):
                if ports.get(port):
                    combinational_drivers.setdefault(ports[port], []).append((name, ports))
    def evaluate(net, values, visiting=()):
        if net in values:
            return values[net]
        if net.startswith("!"):
            return 1 - evaluate(net[1:], values, visiting)
        require(net not in visiting, "cyclic ADC reset qualification")
        drivers = combinational_drivers.get(net, [])
        require(len(drivers) == 1 and drivers[0][0].startswith(reset), "unknown ADC qualification driver")
        name, ports = drivers[0]
        require(set(params[name]) == {"lut_mask", "sum_lutc_input"} and
                params[name]["sum_lutc_input"] in {'"datac"', '"cin"'}, "unsupported ADC qualification LUT")
        # Pinned fiftyfivenm_atoms.v lcell_comb: combout selects datac/cin;
        # carry uses LUT(dataa, datab, cin, 0), independently of that selector.
        carry = ports.get("cout") == net
        third = "cin" if carry or params[name]["sum_lutc_input"] == '"cin"' else "datac"
        inputs = (ports["dataa"], ports["datab"], ports[third], "gnd" if carry else ports["datad"])
        index = sum(evaluate(value, values, (*visiting, net)) << i for i, value in enumerate(inputs))
        return (int(params[name]["lut_mask"].removeprefix("16'h"), 16) >> index) & 1

    def next_register(ports, values):
        if not evaluate(ports["ena"], values):
            return values[ports["q"]]
        return evaluate(ports["asdata"] if evaluate(ports["sload"], values) else ports["d"], values)
    ready = cells[reset + "ready"][1]
    for prefix in ("lock_samples", "sys_release"):
        for i in (0, 1):
            ports = cells[f"{reset}{prefix}[{i}]"][1]
            require(ports["ena"] == "vcc" and ports["sload"] in {"vcc", "gnd"}, "ADC release stage control differs")
            data = ports["asdata"] if ports["sload"] == "vcc" else ports["d"]
            for prior in (0, 1):
                values = {"gnd": 0, "vcc": 1, "\\" + reset + prefix + "[0]": prior}
                require(evaluate(data, values) == (1 if i == 0 else prior), "ADC release stage bypassed")
    for held in (0, 1):
        for count in range(1024):
            values = {"\\" + reset + "lock_count[" + str(i) + "]": (count >> i) & 1 for i in range(10)}
            values.update({"gnd": 0, "vcc": 1, ready["q"]: held})
            require(next_register(ready, values) == (held or count == 1023), "ADC lock qualification is not 1024 cycles")
            actual_count = sum(next_register(cells[f"{reset}lock_count[{i}]"][1], values) << i for i in range(10))
            require(actual_count == (count if held or count == 1023 else count + 1),
                    "ADC lock counter transition/hold differs")
    for state, gate in (("IDLE", "ctrl_state.IDLE~0"), ("PWRDWN", "Selector1~1")):
        name = fsm_path + "ctrl_state." + state
        ports = register(name, "\\" + reset + "sys_release[1]")
        require(ports["sload"] in {"gnd", "vcc"} and ports["ena"] == "vcc",
                "ADC vendor lock load/enable differs")
        # Quartus may route the same synchronous input through D or ASDATA.
        # Accept only the port actually selected by the constant SLOAD control.
        port = "asdata" if ports["sload"] == "vcc" else "d"
        pending = [cells[fsm_path + gate][1]["combout"]]
        seen = set()
        endpoints = set()
        while pending:
            net = pending.pop()
            if net in seen:
                continue
            seen.add(net)
            for consumer, input_port in users(net):
                kind, connections = cells[consumer]
                require(consumer.startswith(fsm_path), "ADC lock escapes vendor controller")
                if kind == "fiftyfivenm_lcell_comb":
                    pending.extend(connections[p] for p in OUTPUTS[kind] if connections.get(p))
                else:
                    register(consumer, "\\" + reset + "sys_release[1]")
                    endpoints.add((consumer, input_port))
        expected = {(name, port)}
        if state == "PWRDWN":
            expected |= {(fsm_path + f"chsel[{i}]", "d") for i in range(3)}
        require(endpoints == expected, "ADC vendor lock reset-qualified closure differs")

    atom = prefix + "u_adc|u_control|adc_inst|adcblock_instance|primitive_instance"
    adc = cell(atom, "fiftyfivenm_adcblock")
    require({n for n, (k, _) in cells.items() if k == "fiftyfivenm_adcblock"} == {atom, "~QUARTUS_CREATED_ADC2~"}, "ADC atom inventory differs")
    require(params[atom] == {"analog_input_pin_mask": "110", "clkdiv": "5", "device_partname_fivechar_prefix": '"10m50"',
            "is_this_first_or_second_adc": "1", "prescalar": "0", "pwd": "0", "refsel": "1", "reserve_block": '"false"',
            "testbits": "66", "tsclkdiv": "0", "tsclksel": "1"}, "ADC1 configuration differs")
    reserved = cell("~QUARTUS_CREATED_ADC2~", "fiftyfivenm_adcblock")
    require(reserved["usr_pwd"] == "vcc" and reserved["clkin_from_pll_c0"] == "gnd" and
            params["~QUARTUS_CREATED_ADC2~"]["pwd"] == "1" and params["~QUARTUS_CREATED_ADC2~"]["reserve_block"] == '"true"', "ADC2 not reserved powered down")
    require(adc["clkin_from_pll_c0"] == "\\" + pll_path + "wire_pll1_clk[0]" and
            (adc["clkin_from_pll_c0"], pll["clk"] + "[0]") in zip(lhs, rhs), "ADC clock is not dedicated PLL c0")
    for key, value in {"operation_mode": '"no compensation"', "clk0_multiply_by": "1", "clk0_divide_by": "1",
                       "inclk0_input_frequency": "100000", "m": "40", "n": "1", "c0_high": "20", "c0_low": "20"}.items():
        require(params[pll_path + "pll1"].get(key) == value, "ADC PLL physical parameter differs: " + key)
    return {"active_adc": 1, "reserved_powered_down_adc": 1, "channel_mask": 6, "sample_rate_hz": 125000,
            "pll_hz": 10000000, "lock_event": row, "lock_consumers": sorted(gate_specs), "qualified_reset_registers": 20,
            "qualification_truth_cases": 2048}


def verify(folder, top="adc_proof", *, parallel=False, system_net=SYS):
    result = verify_netlist((folder / "simulation/questa/design.vo").read_text(),
                            (folder / "output/check_timing.rpt").read_text(), top, parallel=parallel, system_net=system_net)
    fit = (folder / "output/design.fit.rpt").read_text()
    summary = (folder / "output/design.fit.summary").read_text()
    expected_resources = (("Total PLLs", 3 if parallel else 2), ("ADC blocks", 1)) if top in ("controls_proof", "v05_controls_proof") else (
        ("Total PLLs", 1), ("ADC blocks", 1), ("Total memory bits", 0))
    for label, expected in expected_resources:
        values = re.findall(r"(?m)^" + re.escape(label) + r"\s*:\s*(\d+)\s*/", summary)
        if values != [str(expected)]:
            raise ValueError("ADC fit resource mismatch: " + label)
    for pin, signal in (("N5", "clk_adc_reference"), ("P11", "clk_reference" if parallel else "clk_sys")):
        rows = [row for row in fit.splitlines() if re.match(r";\s*" + pin + r"\s*;", row)]
        if len(rows) != 1 or not re.search(r";\s*" + signal + r"\s*;\s*input\s*;\s*3.3-V LVTTL\s*;", rows[0]):
            raise ValueError("ADC physical clock pin mismatch: " + pin)
    mode = r";\s*PLL mode\s*;\s*" + (r"Normal\s*;\s*" * (2 if parallel else 1) if top in ("controls_proof", "v05_controls_proof") else "") + r"No Compensation\s*;"
    if not re.search(mode, fit, re.I):
        raise ValueError("ADC fit compensation mode differs")
    return result

CONTROL = (
    "altera_modular_adc_control.v", "altera_modular_adc_control_fsm.v",
    "altera_modular_adc_control_avrg_fifo.v", "chsel_code_converter_sw_to_hw.v",
    "fiftyfivenm_adcblock_top_wrapper.v", "fiftyfivenm_adcblock_primitive_wrapper.v",
    "altera_modular_adc_control.sdc",
)
SUPPORTED_CONTROL = {
    "altera_modular_adc_control.v": "03fb3f3602704606e33a477491da61ae2415409e1376212b71c95354ece49d92",
    "altera_modular_adc_control_fsm.v": "dd39a51bd11f96ddea56de2be9ef56e2184985d2063a1ab2bda4ca1506e40105",
    "altera_modular_adc_control_avrg_fifo.v": "e4570567d633185546949acf6d6f9d875ee6567a6adc44e27d22c296361accf8",
}


def explained_diagnostics(text, folder, sources, top="adc_proof"):
    """Exact unused dual-ADC and temperature paths in the two-channel proof.

    This does not permit general unused logic/RAM warnings. Raw lines, source
    identity and the complete 15-line inventory must all match.
    """
    if any(sources.get(name, {}).get("sha256") != pin for name, pin in SUPPORTED_CONTROL.items()):
        raise ValueError("unsupported ADC source for diagnostic classification")
    for name, pin in SUPPORTED_CONTROL.items():
        if file_hash(folder / name) != pin:
            raise ValueError("copied ADC source differs from supported diagnostic pin")
    lines = [line.strip() for line in text.splitlines()]
    unused = ('Warning (10036): Verilog HDL or VHDL warning at altera_modular_adc_control_fsm.v(70): '
              'object "sync_ctrl_state_nxt" assigned a value but never read File: '
              + (folder / 'altera_modular_adc_control_fsm.v').as_posix() + ' Line: 70')
    required = [unused, 'Warning (14284): Synthesized away the following node(s):',
                'Warning (14285): Synthesized away the following RAM node(s):']
    prefix = ('Warning (14320): Synthesized away node "' +
              ('n2m_controls_system:u_controls|' if top == 'v05_controls_proof' else '') + 'n2m_adc_backend:u_adc|'
              'altera_modular_adc_control:u_control|altera_modular_adc_control_fsm:u_control_fsm|'
              'altera_modular_adc_control_avrg_fifo:ts_avrg_fifo|scfifo:scfifo_component|')
    for bit in range(12):
        pattern = (re.escape(prefix) + r'scfifo_\w+:auto_generated\|a_dpfifo_\w+:dpfifo\|'
                   + r'altsyncram_\w+:FIFOram\|q_b\[' + str(bit) + r'\]" File: '
                   + re.escape((folder / 'db').as_posix()) + r'/altsyncram_\w+\.tdf Line: '
                   + str(40 + 30 * bit))
        matches = [line for line in lines if re.fullmatch(pattern, line)]
        if len(matches) != 1:
            raise ValueError(f"missing or duplicate ADC temperature FIFO diagnostic bit {bit}")
        required.extend(matches)
    for line in required:
        if lines.count(line) != 1:
            raise ValueError("missing or duplicate ADC unused-feature diagnostic")
    actual = [line for line in lines if re.match(r'Warning \((10036|14284|14285|14320)\):', line)]
    if len(actual) != 15 or set(actual) != set(required):
        raise ValueError("unexpected ADC unused-feature diagnostic")
    return [{"code": re.match(r'Warning \((\d+)\)', line)[1], "text": line,
             "reason": "pinned Intel ADC1 control: unused dual-ADC state and channel17 temperature FIFO"}
            for line in required]


def identity(directory):
    quartus = Path(directory).resolve().parent
    ip = quartus.parent / "ip/altera"
    paths = {name: ip / "altera_modular_adc/control" / name for name in CONTROL}
    # Synthesis resolves the canonical megafunction automatically. Retain this
    # same source for explicit simulation compilation without shadowing it in QSF.
    paths["altera_std_synchronizer.v"] = quartus / "libraries/megafunctions/altera_std_synchronizer.v"
    paths["control_definition"] = ip / "altera_modular_adc/control/altera_modular_adc_control_hw.tcl"
    paths["core_definition"] = ip / "altera_modular_adc/top/altera_modular_adc_hw.tcl"
    paths["atom_model"] = quartus / "eda/sim_lib/fiftyfivenm_atoms.v"
    paths["generator"] = Path(directory) / "qmegawiz.exe"
    paths["pll_definition"] = quartus / "libraries/megafunctions/altpll.tdf"
    if any(not p.is_file() for p in paths.values()):
        raise ValueError("missing installed Intel ADC/PLL dependency")
    result = {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}
    result.update({"pll_" + name: value for name, value in fpga_pll.identity(directory).items()})
    return result


def generate(folder, sources, execute, timeout, record, build):
    for name in CONTROL:
        source = Path(sources[name]["path"])
        if file_hash(source) != sources[name]["sha256"]:
            raise ValueError("Intel ADC dependency changed before generation")
        shutil.copyfile(source, folder / name)
    execute(generation_command(sources), folder, folder / "generate-adc-pll.log", timeout, record, build)
    verify_generated(folder)


def generation_command(sources):
    return [sources["generator"]["path"], "-silent", "module=altpll",
               "INTENDED_DEVICE_FAMILY=MAX 10", "INCLK0_INPUT_FREQUENCY=100000",
               "CLK0_MULTIPLY_BY=1", "CLK0_DIVIDE_BY=1", "CLK0_DUTY_CYCLE=50",
               "CLK0_PHASE_SHIFT=0", "COMPENSATE_CLOCK=CLK0", "OPERATION_MODE=NO_COMPENSATION",
               "areset=used", "locked=used", "clk0=used", "OPTIONAL_FILES=NONE", "n2m_adc_pll.v"]


def verify_generated(folder):
    text = (folder / "n2m_adc_pll.v").read_text()
    expected = {"clk0_divide_by": "1", "clk0_multiply_by": "1", "clk0_duty_cycle": "50",
                "clk0_phase_shift": '"0"', "inclk0_input_frequency": "100000",
                "intended_device_family": '"MAX 10"', "operation_mode": '"NO_COMPENSATION"',
                "port_areset": '"PORT_USED"', "port_locked": '"PORT_USED"'}
    for name, value in expected.items():
        if re.findall(r"altpll_component\." + name + r"\s*=\s*([^,;]+)", text) != [value]:
            raise ValueError(f"generated ADC PLL parameter mismatch: {name}")


def assignments():
    return [f'set_global_assignment -name VERILOG_FILE {name}'
            for name in (*CONTROL[:-1], "n2m_adc_pll.v")] + [
                "set_global_assignment -name SDC_FILE altera_modular_adc_control.sdc"]
