"""Recognize the Cyclone V lock qualification in the checked functional netlist.

Cyclone V has no counterpart to the MAX 10 ALTPLL locked-output event latch: the
Altera PLL's `lock` leaves the fractional PLL as an ordinary signal, so the
design has no register without a clock and `check_timing` must report none. The
evidence is therefore the qualification itself, proved from the netlist:

- both PLLs take the board reference through its input buffer, and both take
  their reset from the one bootstrap register that runs on that raw reference,
  so no PLL reset depends on a stopped PLL output;
- one lock gate combines both raw locks with that reset, and its truth table is
  evaluated over every combination, so either lock loss and the reset each still
  reach the sampling reset;
- the gate reaches nothing but the two lock sampling registers' clears, and
  those registers run on the generated system clock.
"""
import re

from . import fpga_lock

PLL = "u_clocking|u_pll|altera_pll_i|"
SYSTEM = "u_clocking|u_system_pll|altera_pll_i|"
RESET = "u_clocking|u_reset|"
# The fitted atom suffixes inside each PLL wrapper instance.
FRACTIONAL = "general[0].gpll~FRACTIONAL_PLL"
COUNTER = "general[0].gpll~PLL_OUTPUT_COUNTER"
REFCLK_SELECT = "general[0].gpll~PLL_REFCLK_SELECT"
# The board reference: the input buffer's output and the global buffer that
# clocks the bootstrap register. Neither is a generated clock.
REFERENCE_PIN = "clk_reference"
REFERENCE_OUT = r"\clk_reference~input_o"
REFERENCE_NET = r"\clk_reference~inputCLKENA0_outclk"
OUTPUTS = {
    "dffeas": {"q"},
    "cyclonev_lcell_comb": {"combout", "sumout", "cout", "shareout"},
    "cyclonev_clkena": {"outclk", "enaout"},
    "cyclonev_io_ibuf": {"o"},
    "cyclonev_io_obuf": {"o", "obar"},
    "cyclonev_fractional_pll": {"cntnen", "fbclk", "fblvdsout", "lock", "mcntout", "mhi", "plniotribuf",
                                "shiftdoneout", "tclk", "vcoph"},
    "cyclonev_pll_output_counter": {"cascadeout", "divclk", "shiftdone0o"},
    "cyclonev_pll_refclk_select": {"clk0bad", "clk1bad", "clkout", "extswitchbuf", "pllclksel"},
    "cyclonev_pll_reconfig": {"blockselect", "dout", "dprioout", "iocsrdataout", "iocsrenbuf", "iocsrrstnbuf",
                              "phasedone", "shift", "shiften", "shiftenm", "up"},
    # A simulation-only task container with no ports; it drives nothing.
    "altera_pll_reconfig_tasks": set(),
}
REGISTER_MODES = {"is_wysiwyg": '"true"', "power_up": '"low"'}
BUFFER_MODES = {"clock_type": '"global clock"', "disable_mode": '"low"',
                "ena_register_mode": '"always enabled"', "ena_register_power_up": '"high"',
                "test_syn": '"high"'}
LUT_INPUTS = ("dataa", "datab", "datac", "datad", "datae", "dataf")
SUPPORTED_TOPS = ("nano_clocking_proof",)


def verify(text, checks, top="nano_clocking_proof"):
    if top not in SUPPORTED_TOPS:
        raise ValueError("unsupported Cyclone V PLL proof top")
    rows = re.findall(r";\s*([^;\r\n]+?)\s*;\s*No clock feeds this register's clock port\.\s*;", checks)
    if rows:
        raise ValueError("unrecognized no-clock endpoint")
    _, cells, params, _declarations, rhs, lhs = fpga_lock.parse_netlist(text, top, outputs=OUTPUTS)

    def cell(name, kind, modes=None):
        if cells.get(name, (None,))[0] != kind or (modes is not None and params.get(name) != modes):
            raise ValueError("Cyclone V lock cell or mode differs: " + name)
        return cells[name][1]

    def contains(net, value):
        return net in re.findall(r"\\[^,{}!]+", value)

    def users(net):
        if any(contains(net, value) for value in rhs + lhs):
            raise ValueError("Cyclone V lock alias is not allowed: " + net)
        return {(name, port) for name, (kind, ports) in cells.items() for port, value in ports.items()
                if port not in OUTPUTS[kind] and contains(net, value)}

    # The bootstrap reset register runs on the board reference, not on a PLL output.
    reset = cell(RESET + "pll_areset", "dffeas", REGISTER_MODES)
    buffer = cell(REFERENCE_PIN + "~inputCLKENA0", "cyclonev_clkena", BUFFER_MODES)
    pin = cell(REFERENCE_PIN + "~input", "cyclonev_io_ibuf")
    if (reset["clk"] != REFERENCE_NET or buffer.get("outclk") != REFERENCE_NET
            or buffer.get("inclk") != REFERENCE_OUT or buffer.get("ena") != "vcc"
            or pin.get("o") != REFERENCE_OUT or pin.get("i") != REFERENCE_PIN):
        raise ValueError("PLL reset bootstrap does not run on the board reference")
    # The reset register holds the complement: a Cyclone V register clears
    # asynchronously to zero, and the contract powers this reset up asserted.
    if (reset.get("clrn") != "\\" + RESET + "board_release[1]" or reset.get("prn") != "vcc"
            or reset.get("aload") != "gnd" or reset.get("sclr") != "gnd" or reset.get("ena") != "vcc"):
        raise ValueError("PLL reset register clear or control differs")
    released = reset["q"]
    critical = [(released, RESET + "pll_areset", "q")]
    locks = []
    for prefix in (SYSTEM, PLL):
        pll = cell(prefix + FRACTIONAL, "cyclonev_fractional_pll")
        select = cell(prefix + REFCLK_SELECT, "cyclonev_pll_refclk_select")
        counter = cell(prefix + COUNTER, "cyclonev_pll_output_counter")
        outputs = cell(prefix + "outclk_wire[0]~CLKENA0", "cyclonev_clkena", BUFFER_MODES)
        if (pll.get("nresync") != "!" + released
                or pll.get("refclkin") != "\\" + prefix + REFCLK_SELECT + "_O_CLKOUT"
                or select.get("clkout") != "\\" + prefix + REFCLK_SELECT + "_O_CLKOUT"
                or select.get("clkin") != "{gnd,gnd,gnd," + REFERENCE_OUT + "}"
                or counter.get("divclk") != "\\" + prefix + "outclk_wire[0]"
                or outputs.get("inclk") != "\\" + prefix + "outclk_wire[0]"
                or outputs.get("ena") != "vcc"
                or outputs.get("outclk") != "\\" + prefix + "outclk_wire[0]~CLKENA0_outclk"):
            raise ValueError("Cyclone V PLL reference, reset or output binding differs: " + prefix)
        locks.append(pll["lock"])
        critical += [(pll["lock"], prefix + FRACTIONAL, "lock"),
                     (counter["divclk"], prefix + COUNTER, "divclk"),
                     (outputs["outclk"], prefix + "outclk_wire[0]~CLKENA0", "outclk")]
    system_net = "\\" + SYSTEM + "outclk_wire[0]~CLKENA0_outclk"

    # One gate qualifies reset with both raw locks. Its inputs may be inverted,
    # so each is resolved to its net and polarity before the table is evaluated.
    gate_name = RESET + "lock_reset"
    gate = cell(gate_name, "cyclonev_lcell_comb")
    mask = params.get(gate_name, {}).get("lut_mask", "")
    if (set(params.get(gate_name, {})) != {"extended_lut", "lut_mask", "shared_arith"}
            or params[gate_name]["extended_lut"] != '"off"' or params[gate_name]["shared_arith"] != '"off"'
            or not re.fullmatch(r"64'h[0-9A-Fa-f]{16}", mask)):
        raise ValueError("Cyclone V lock gate mode differs")
    if any(gate.get(port) != "gnd" for port in ("datag", "cin", "sharein")) or any(
            gate.get(port) != "" for port in ("sumout", "cout", "shareout")):
        raise ValueError("Cyclone V lock gate has unexpected arithmetic or outputs")
    mask = int(mask[4:], 16)
    for assignment in range(8):
        system, pixel, release = [(assignment >> i) & 1 for i in range(3)]
        values = {locks[0]: system, locks[1]: pixel, released: release, "gnd": 0, "vcc": 1}
        index = 0
        for shift, port in enumerate(LUT_INPUTS):
            value = gate.get(port, "")
            inverted = value.startswith("!")
            net = value.removeprefix("!")
            if net not in values:
                raise ValueError("Cyclone V lock gate has unrelated inputs")
            index |= (values[net] ^ inverted) << shift
        # `released` is the complement of the contract's pll_areset, so reset is
        # asserted when it is low. Lock reset must hold then, or on either loss.
        if ((mask >> index) & 1) != int(not release or not system or not pixel):
            raise ValueError("Cyclone V lock gate loses reset or raw lock propagation")
    critical.append((gate["combout"], gate_name, "combout"))

    # The gate reaches only the two lock sampling clears, and nothing else uses
    # either raw lock. The samples run on the generated system clock.
    samples = {RESET + f"lock_samples[{i}]" for i in (0, 1)}
    if users(gate["combout"]) != {(name, "clrn") for name in samples}:
        raise ValueError("Cyclone V lock reset reaches a functional datapath")
    for net in locks:
        expected = {(gate_name, port) for port, value in gate.items() if value.removeprefix("!") == net}
        if users(net) != expected or not expected:
            raise ValueError("Cyclone V raw lock has non-reset fanout")
    for i in (0, 1):
        name = RESET + f"lock_samples[{i}]"
        sample = cell(name, "dffeas", REGISTER_MODES)
        if (sample.get("clk") != system_net or sample.get("clrn") != "!" + gate["combout"]
                or any(sample.get(port) != value for port, value in
                       {"prn": "vcc", "ena": "vcc", "aload": "gnd", "sclr": "gnd",
                        "devclrn": "devclrn", "devpor": "devpor"}.items())
                or sample.get("sload") not in ("gnd", "vcc")
                or sample.get("q") != "\\" + RESET + f"lock_samples[{i}]"):
            raise ValueError("Cyclone V lock sample clock, reset or control differs")
        selected = sample.get("d" if sample["sload"] == "gnd" else "asdata")
        expected = "vcc" if i == 0 else "\\" + RESET + "lock_samples[0]"
        if selected != expected:
            feeder_name = name + "~feeder"
            feeder = cell(feeder_name, "cyclonev_lcell_comb")
            modes = params.get(feeder_name, {})
            feeder_mask = modes.get("lut_mask", "")
            if (selected != feeder.get("combout") or feeder.get("cin") != "gnd"
                    or set(modes) != {"extended_lut", "lut_mask", "shared_arith"}
                    or not re.fullmatch(r"64'h[0-9A-Fa-f]{16}", feeder_mask)):
                raise ValueError("Cyclone V lock sample feeder differs")
            feeder_mask = int(feeder_mask[4:], 16)
            for bit in (0, 1):
                # A constant data input keeps its constant value: the vendor
                # constants are written last so they override the swept bit.
                values = {expected: bit, "gnd": 0, "vcc": 1}
                index = 0
                for shift, port in enumerate(LUT_INPUTS):
                    value = feeder.get(port, "")
                    net = value.removeprefix("!")
                    if net not in values:
                        raise ValueError("Cyclone V lock sample has unrelated data")
                    index |= (values[net] ^ value.startswith("!")) << shift
                if ((feeder_mask >> index) & 1) != values[expected]:
                    raise ValueError("Cyclone V lock sample pipeline bypassed")
            critical.append((selected, feeder_name, "combout"))
        critical.append((sample["q"], name, "q"))
    for net, name, port in critical:
        drivers = {(owner, key) for owner, (kind, ports) in cells.items() for key, value in ports.items()
                   if key in OUTPUTS[kind] and contains(net, value)}
        if drivers != {(name, port)} or any(contains(net, value) for value in lhs):
            raise ValueError("Cyclone V lock net has extra drivers: " + net)
    return {"endpoints": [], "classification": "no vendor lock latch; Altera PLL lock qualifies reset only",
            "truth_cases": 8, "bootstrap_clock": REFERENCE_NET, "sampling_clock": system_net,
            "raw_locks": locks}
