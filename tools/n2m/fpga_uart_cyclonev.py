"""The Cyclone V UART endpoint image's checked receive synchronizer.

The endpoint RTL is the qualified one, so the audit is the same audit: the
external port must reach one first-stage register and nothing else, and every
analysed corner must time the path to the second stage. Only the fitted netlist
differs. A Cyclone V netlist has no `fiftyfivenm_*` atom and no
`clk_sys~inputclkctrl_outclk` net, so the structure check lives here while
[fpga_controls](fpga_controls.py) still owns the false-path collections, the
per-corner reports and their report check.

The board's analysed corners and core voltage are this family's
(wiki/src/de10-nano-board.md#targets), and the launching clock is the fitted
Altera PLL output counter rather than a port name.
"""
import re

from . import fpga_controls, fpga_lock, fpga_lock_cyclonev, fpga_pll_cyclonev, fpga_vga
from .fpga_clocking import FIT_ENCODING

# The industrial Cyclone V's four analysed corners, in the order the board
# registry declares them, and its 1.10 V nominal core voltage.
CORNERS = (("slow100", "slow", 100), ("slow-40", "slow", -40),
           ("fast100", "fast", 100), ("fast-40", "fast", -40))
VOLTAGE = 1100
# The one chain this image carries: the serial receive line into the endpoint's
# two-flop synchronizer. The reset value is one, so the fitted register holds the
# complement and the first stage is reached through an inversion.
CHAINS = (("uart", "uart_rx", "u_uart|u_serial_rx|rx_meta", "u_uart|u_serial_rx|rx_sync"),)
SYSTEM_CLOCK = fpga_pll_cyclonev.SYSTEM_CLOCK
SYSTEM_NET = fpga_pll_cyclonev.SYSTEM_NET
# The qualified system reset the endpoint's registers clear on: the second stage
# of the clocking wrapper's release chain, reaching the register directly.
RESET_NET = r"\u_clocking|u_reset|sys_release[1]"
REGISTER_MODES = {"is_wysiwyg": '"true"', "power_up": '"low"'}
LUT_MODES = {"extended_lut": '"off"', "shared_arith": '"off"'}
LUT_INPUTS = fpga_lock_cyclonev.LUT_INPUTS
# The endpoint's own memories are M10K atoms; the netlist consumer must know the
# primitive to account for every sink, so it is named with the family's others.
OUTPUTS = {**fpga_lock_cyclonev.OUTPUTS, "cyclonev_ram_block": {"portadataout", "portbdataout"}}
# The fitter may pack a feeder LUT behind the inverter, as it may on MAX 10.
MAX_UNARY_LUTS = fpga_controls.MAX_UNARY_LUTS
# The endpoint's own six stores, as owner -> (depth, width, M10K blocks). They are
# the same six logical stores the DE10-Lite board images carry
# (wiki/src/rtl/uart/MAS_uart.md); only the family's block is larger, so the
# 65,536-bit presence store spans eight M10K blocks instead of eight M9Ks.
STORES = {"u_uart|u_commands|u_load|u_presence|u_presence": (65536, 1, 8),
          "u_uart|u_exchange|stores|banks[0].memory": (268, 8, 1),
          "u_uart|u_exchange|stores|banks[1].memory": (268, 8, 1),
          "u_uart|u_exchange|stores|banks[2].memory": (268, 8, 1),
          "u_uart|u_packet_rx|stores|decoded": (268, 8, 1),
          "u_uart|u_packet_rx|stores|encoded": (270, 8, 1)}
STORE_SUFFIX = "|ram|auto_generated|ALTSYNCRAM"
# The fitted totals those stores add up to, as the fit summary states them.
TOTAL_BLOCKS = sum(blocks for _, _, blocks in STORES.values())
TOTAL_BITS = sum(depth * width for depth, width, _ in STORES.values())


def audit(quote, *, chains=CHAINS):
    return fpga_controls.audit(quote, chains=chains, corners=CORNERS, voltage=VOLTAGE)


def constraints(quote, *, chains=CHAINS):
    return fpga_controls.constraints(quote, chains=chains)


def required_reports(*, chains=CHAINS):
    return fpga_controls.required_reports(chains=chains, corners=CORNERS)


def verify_memory(folder):
    """The fitted memories are the endpoint's six stores and nothing else.

    Each row is bound to its owner, shape, mode, register stage and
    read-during-write behaviour, and the summary totals must be exactly what
    those six add up to. Placement locations are a fitter result and are not
    checked.
    """
    fit = (folder / "output/design.fit.rpt").read_text(encoding=FIT_ENCODING)
    rows = [row for row in fpga_vga.rows(fit) if len(row) == 28 and row[1] == "M10K block"]
    seen = {}
    for row in rows:
        owner = fpga_vga.node(row[0]).removesuffix(STORE_SUFFIX)
        if owner not in STORES or owner in seen:
            raise ValueError("fitted UART store owner differs")
        depth, width, blocks = STORES[owner]
        d, w, bits = str(depth), str(width), str(depth * width)
        if (row[2:12] != ["True Dual Port", "Single Clock", d, w, d, w, "yes", "no", "yes", "no"]
                or row[12:20] != [bits, d, w, d, w, bits, str(blocks), "0"]
                or row[20] != "None"
                or row[22:] != ["Old data", "New data", "New data", "Off", "No", "No - Unsupported Mode"]):
            raise ValueError("fitted UART store shape, registers or read-during-write differs: " + owner)
        seen[owner] = blocks
    if set(seen) != set(STORES):
        raise ValueError("fitted UART store inventory differs")
    summary = (folder / "output/design.fit.summary").read_text(encoding="utf-8")
    for label, expected in (("Total RAM Blocks", f"{TOTAL_BLOCKS} /"),
                            ("Total block memory bits", f"{TOTAL_BITS:,} /")):
        values = re.findall(r"(?m)^" + label + r" : (.+)$", summary)
        if len(values) != 1 or not values[0].startswith(expected):
            raise ValueError("fitted UART memory capacity differs: " + label)
    return {"stores": len(seen), "blocks": TOTAL_BLOCKS, "bits": TOTAL_BITS}


def _live_input(ports, values):
    """The one net a LUT reads that is not a vendor constant, with its polarity."""
    live = set()
    for port in LUT_INPUTS:
        value = ports.get(port, "")
        net = value.removeprefix("!")
        if net in ("gnd", "vcc", ""):
            continue
        if net not in values:
            raise ValueError("control LUT has unrelated inputs")
        live.add(net)
    if len(live) != 1:
        raise ValueError("control LUT does not read exactly one net")
    return live.pop()


def _unary_lut(cells, params, cell, output):
    """Return (input net, inverted) for one LUT computing a unary function.

    Every mode is checked, the mask is evaluated over both values of the single
    live input, and a function that is neither a buffer nor an inverter fails.
    """
    kind, ports = cells[cell]
    modes = params.get(cell, {})
    mask = modes.get("lut_mask", "")
    if (kind != "cyclonev_lcell_comb" or set(modes) != {"extended_lut", "lut_mask", "shared_arith"}
            or any(modes[key] != value for key, value in LUT_MODES.items())
            or not re.fullmatch(r"64'h[0-9A-Fa-f]{16}", mask)
            or ports.get("cin") != "gnd" or ports.get("sharein") != "gnd"
            or any(ports.get(port) != "" for port in ("sumout", "cout", "shareout"))
            or ports.get("combout") != output or ports.get("datag", "gnd") != "gnd"):
        raise ValueError("control unary LUT mode differs")
    source = _live_input(ports, {ports.get(p, "").removeprefix("!") for p in LUT_INPUTS})
    mask = int(mask[4:], 16)
    results = []
    for bit in (0, 1):
        values = {source: bit, "gnd": 0, "vcc": 1, "": 0}
        index = 0
        for shift, port in enumerate(LUT_INPUTS):
            value = ports.get(port, "")
            index |= (values[value.removeprefix("!")] ^ value.startswith("!")) << shift
        results.append((mask >> index) & 1)
    if results not in ([0, 1], [1, 0]):
        raise ValueError("control unary LUT polarity differs")
    return source, results == [1, 0]


def _unary_chain(cells, params, source, target):
    """Walk back from a register input to its source through unary LUTs only."""
    chain = []
    net = target
    while net != source:
        if len(chain) == MAX_UNARY_LUTS:
            raise ValueError("control path does not have a bounded unary LUT chain")
        drivers = [name for name, (kind, ports) in cells.items()
                   if kind == "cyclonev_lcell_comb" and ports.get("combout") == net]
        if len(drivers) != 1:
            raise ValueError("control path does not have one unary LUT")
        cell_input, inverted = _unary_lut(cells, params, drivers[0], net)
        chain.append((drivers[0], inverted, cell_input))
        net = cell_input
    return list(reversed(chain))


def verify(folder, *, chains=CHAINS, top="nano_uart_proof"):
    """Check the corner reports and the fitted structure of every chain here.

    Returns the same shape as the MAX 10 audit: the met slack of each retained
    report, and the LUTs each first stage is reached through.
    """
    if top not in ("nano_uart_proof",):
        raise ValueError("unsupported Cyclone V control synchronizer top")
    result = {"paths": fpga_controls.verify_reports(folder, chains=chains, corners=CORNERS,
                                                    system_clock=SYSTEM_CLOCK),
              "first_stage_sinks": {}}
    text = (folder / "simulation/questa/design.vo").read_text(encoding="utf-8")
    _, cells, params, _declarations, rhs, lhs = fpga_lock.parse_netlist(text, top, outputs=OUTPUTS)

    def contains(net, value):
        # A net name may appear inverted, inside a concatenation or beside
        # another name, so it is matched on its own token boundaries.
        token = re.compile(r"(?<![A-Za-z0-9_$\\|~])" + re.escape(net) + r"(?![A-Za-z0-9_$|~\[])")
        return token.search(value) is not None

    def sinks(net):
        if any(contains(net, value) for value in rhs + lhs):
            raise ValueError("control crossing has an unexpected alias")
        return {(name, port) for name, (kind, ports) in cells.items() for port, value in ports.items()
                if port not in OUTPUTS[kind] and contains(net, value)}

    def selected(register):
        kind, ports = cells[register]
        if (kind != "dffeas" or params.get(register) != REGISTER_MODES
                or ports.get("clk") != SYSTEM_NET or ports.get("clrn") != RESET_NET
                or any(ports.get(port) != value for port, value in
                       {"ena": "vcc", "aload": "gnd", "sclr": "gnd", "prn": "vcc",
                        "devclrn": "devclrn", "devpor": "devpor"}.items())):
            raise ValueError("control synchronizer clock/reset/load/enable differs")
        port = {"gnd": "d", "vcc": "asdata"}.get(ports.get("sload"))
        if port is None:
            raise ValueError("control synchronizer has dynamic selected input")
        return port

    def path(source, register, inverted):
        """One direct edge, or a checked unary LUT chain, with no bypass fanout."""
        port = selected(register)
        target = cells[register][1][port]
        if target == source:
            if inverted or sinks(source) != {(register, port)}:
                raise ValueError("control direct path polarity or fanout differs")
            return []
        chain = _unary_chain(cells, params, source, target)
        if sum(cell_inverted for _, cell_inverted, _ in chain) % 2 != int(inverted):
            raise ValueError("control unary LUT polarity differs")
        consumers = [(register, port)]
        for cell, _, cell_input in reversed(chain):
            if sinks(cells[cell][1]["combout"]) != set(consumers):
                raise ValueError("control unary path has bypass fanout")
            # A Cyclone V LUT carries the inversion on the port expression, so a
            # consumer is matched with that polarity prefix removed.
            consumers = [(cell, p) for p, value in cells[cell][1].items()
                         if p not in OUTPUTS[cells[cell][0]] and value.removeprefix("!") == cell_input]
        if sinks(source) != set(consumers):
            raise ValueError("control unary path has bypass fanout")
        return [cell for cell, _, _ in chain]

    for name, external, first, second in chains:
        buffer = external + "~input"
        if cells.get(buffer, (None,))[0] != "cyclonev_io_ibuf":
            raise ValueError("control external input buffer missing")
        ports = cells[buffer][1]
        if (ports != {"i": external, "ibar": "gnd", "dynamicterminationcontrol": "gnd",
                      "o": "\\" + external + "~input_o"}
                or sinks(external) != {(buffer, "i")}):
            raise ValueError("control external port has bypass or unexpected buffer")
        result["first_stage_sinks"][name] = {
            "external_path": path(ports["o"], first, True),
            "second_path": path(cells[first][1]["q"], second, False), "capture": second}
    return result
