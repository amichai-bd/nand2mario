"""The DE2-115's ADV7123 video DAC: the same pixel path, eight bits per channel.

Nothing here generates pixels or changes the frame bridge. The whole VGA proof
evidence is [fpga_vga](fpga_vga.py)'s, reached through its output profile; this
module states only what the board adds:

- the board's output profile: three eight-bit channels, its two sync pins and the
  `cycloneive_ram_block` atom this family fits for the same M9K block;
- the DAC's own clock, blank and sync pins, and the checks that they carry the
  values the [board specification](../../wiki/src/de2-115-board.md#driving-the-vga-dac)
  records from the ADV7123 datasheet;
- two fitter diagnostics this board's DAC produces and the DE10-Lite's resistor
  ladder cannot: the deliberately constant control pins, and the pixel clock
  leaving the fabric to the DAC's clock pin.

The four-to-eight bit alignment is in the RTL
([`de2_vga_proof.sv`](../../src/fpga/de2_115/de2_vga_proof.sv)) and its derivation
is on the board page; this module checks the fitted result of it.
"""
import re

from . import fpga_vga

TOP = "de2_vga_proof"
CHANNELS = ("vga_r", "vga_g", "vga_b")
# The ADV7123 is a triple 10-bit DAC and the board wires the higher eight bits of
# each channel (DE2-115 user manual section 4.10), so eight is the board's width,
# not the part's.
CHANNEL_BITS = 8
SYNC = ("vga_hs", "vga_vs")
# The fitted M9K atom of this family, against MAX 10's `fiftyfivenm_ram_block`.
ATOM = "cycloneive_ram_block"
DAC = fpga_vga.profile(CHANNELS, CHANNEL_BITS, SYNC, atom=ATOM)
# The DAC's two control inputs and the level the datasheet requires on each.
# BLANK at Logic 0 makes the DAC ignore the pixel inputs, so it is held at 1;
# SYNC is tied to Logic 0, the datasheet's value when sync is not encoded on
# green. Reasons and sources: the board specification.
CONTROLS = {"vga_blank_n": 1, "vga_sync_n": 0}
# The DAC's clock pin and the generated clock the SDC creates on it: the pixel
# clock inverted, so the DAC's rising edge falls half a pixel period after the
# fabric drove the data.
CLOCK_PORT = "vga_clk"
CLOCK_NAME = "vga_dac_clk"
# Every pin this target drives, so the project states a drive strength on each.
DRIVE_PORTS = (*DAC.ports, *CONTROLS, CLOCK_PORT)
# Quartus reports a pin held at a constant as one 13024 heading with one
# indented 13410 line per pin, and each of those is its own diagnostic line. Both
# control pins are deliberate documented constants, so all three lines are
# classified against exactly that pin set, each level and the file the port is
# declared in, and nothing wider. The line number moves when the source is
# edited; the file does not.
STUCK = "Warning (13024): Output pins are stuck at VCC or GND"
STUCK_PIN = re.compile(r'Warning \(13410\): Pin "(?P<pin>\w+)" is stuck at (?P<level>VCC|GND)'
                       r' File: (?P<file>\S+) Line: \d+')
STUCK_LEVEL = {1: "VCC", 0: "GND"}
# The registered source that declares this top's ports, as the attempt's own
# project file names it. Reading it from the project file keeps the check exact
# without this module knowing the checkout's path.
def top_source(top=TOP):
    """The project file's own name for the registered source declaring this top."""
    return re.compile(r'(?m)^set_global_assignment -name SYSTEMVERILOG_FILE "(\S+/'
                      + top + r'\.sv)"$')


TOP_SOURCE = top_source()
STUCK_REASON = (
    "Both ADV7123 control pins are documented constants: BLANK stays at Logic 1 because a Logic 0 "
    "makes the DAC ignore the pixel inputs, and SYNC is tied to Logic 0, the datasheet's value when "
    "sync is not encoded on the green channel. A pin stuck at a level this target did not choose "
    "still fails.")
# The pixel clock leaves the fabric to the DAC's clock pin, which is not a
# dedicated PLL output, so the fitter warns about jitter on that route once. The
# generated file's line number is inside vendor HDL whose content the PLL
# evidence already binds by hash; the PLL instance, the output port, the pin and
# the file are all required.
CLOCK_ROUTING = re.compile(
    r'Warning \(15064\): PLL "(?P<pll>\S+)" output port clk\[0\] feeds output pin '
    r'"(?P<pin>\w+)~output" via non-dedicated routing -- jitter performance depends on switching '
    r'rate of other design elements\. Use PLL dedicated clock outputs to ensure jitter performance '
    r'File: (?P<file>\S+) Line: \d+')
CLOCK_ROUTING_REASON = (
    "The ADV7123 latches on the rising edge of its CLOCK input, so the pin carries the 25.2 MHz "
    "pixel clock inverted and reaches it through the fabric rather than a dedicated PLL output pin. "
    "Half a pixel period, 19.8 ns, separates the DAC's sampling edge from the edge that drove the "
    "data, against the part's 0.5 ns setup and 1.5 ns hold, so routed-clock jitter has margin to "
    "spare. Observing a picture is a separate bring-up result.")


def dac_target(target):
    """Whether this target drives the board's video DAC."""
    return target.get("top") == TOP


def stuck_diagnostics(text, folder, top=TOP):
    """Classify the stuck-pin heading and one line per constant DAC control pin.

    `top` names the registered source the constants are written in, because the
    same two documented constants reach the same two pins from the system image's
    own top as well as from the standalone fixture's.
    """
    lines = [line.strip() for line in text.splitlines()
             if line.strip().startswith(("Warning (13024):", "Warning (13410):"))]
    source = top_source(top).findall((folder / "design.qsf").read_text(encoding="utf-8"))
    expected = {port: STUCK_LEVEL[value] for port, value in CONTROLS.items()}
    if len(lines) != 1 + len(expected) or lines[0] != STUCK or len(source) != 1:
        raise ValueError("DAC control pin constant identity/count differs")
    pins = {}
    for line in lines[1:]:
        match = STUCK_PIN.fullmatch(line)
        if not match or match["file"] != source[0] or expected.get(match["pin"]) != match["level"]:
            raise ValueError("DAC control pin constant identity/count differs")
        pins[match["pin"]] = match["level"]
    if pins != expected:
        raise ValueError("DAC control pin constant identity/count differs")
    return [{"code": line.split("(")[1].split(")")[0], "text": line, "reason": STUCK_REASON}
            for line in lines]


def clock_routing_diagnostics(text, folder, pll):
    """Classify the one routed-clock warning the DAC's clock pin produces."""
    lines = [line.strip() for line in text.splitlines() if line.strip().startswith("Warning (15064):")]
    generated = {(folder / "db" / name).resolve().as_posix()
                 for name in ("n2m_pixel_pll_altpll.v", "n2m_system_pll_altpll.v")}
    if len(lines) != 1:
        raise ValueError("DAC clock routing diagnostic identity/count differs")
    match = CLOCK_ROUTING.fullmatch(lines[0])
    if (not match or match["pin"] != CLOCK_PORT or match["file"] not in generated
            or match["pll"] != pll):
        raise ValueError("DAC clock routing diagnostic identity/count differs")
    return [{"code": "15064", "text": lines[0], "reason": CLOCK_ROUTING_REASON}]


def explained_diagnostics(text, folder, pll, top=TOP):
    """Every diagnostic the DAC adds, in the order the fitter reports them."""
    return [*stuck_diagnostics(text, folder, top), *clock_routing_diagnostics(text, folder, pll)]


def verify(folder, *, system_clock, system_net):
    """The shared VGA evidence on this board's profile, plus the DAC's own pins."""
    evidence = fpga_vga.verify(folder, system_clock=system_clock, system_net=system_net, outputs=DAC)
    evidence["dac"] = {"channel_bits": CHANNEL_BITS, "controls": dict(sorted(CONTROLS.items())),
                       "clock_port": CLOCK_PORT, "clock": CLOCK_NAME,
                       **verify_controls(folder)}
    return evidence


def verify_controls(folder):
    """Read the fitted netlist for the level each DAC control pin actually carries.

    A documented constant in the source is not evidence that the constant reached
    the pin. Each control port's output buffer must take its data from the
    constant the board specification records, and the clock pin's buffer must not
    take a constant at all.
    """
    netlist = (folder / "simulation/questa/design.vo").read_text(encoding="utf-8")
    buffers = dict(re.findall(r"cycloneive_io_obuf\s+\\(\w+)~output\s*\((.*?)\);", netlist, re.DOTALL))
    levels = {}
    for port, value in sorted(CONTROLS.items()):
        body = buffers.get(port)
        if body is None:
            raise ValueError(f"missing fitted output buffer for DAC control: {port}")
        data = re.search(r"\.i\(([^)]*)\)", body)
        if data is None or data[1].strip() != ("vcc" if value else "gnd"):
            raise ValueError(f"DAC control pin does not carry its documented level: {port}")
        levels[port] = data[1].strip()
    clock = buffers.get(CLOCK_PORT)
    data = re.search(r"\.i\(([^)]*)\)", clock) if clock is not None else None
    # The DAC's clock pin carries the pixel clock inverted, so the buffer takes
    # the complement of the fitted pixel clock net and not a constant, a divider
    # or the same edge the data leaves on.
    if data is None or data[1].strip() != "!" + fpga_vga.PIXEL_NET:
        raise ValueError("DAC clock pin does not carry the inverted pixel clock")
    return {"control_levels": levels, "clock_driver": data[1].strip()}
