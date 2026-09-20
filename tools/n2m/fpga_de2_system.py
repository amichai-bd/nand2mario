"""The DE2-115 system image: the whole composition bound to one board's pins.

Nothing here changes the composition or any shared RTL. The image is
[`de2_system_proof.sv`](../../src/fpga/de2_115/de2_system_proof.sv) binding
`n2m_clocking` and `n2m_v05_system` to this board, so every clocking, memory,
pixel-path and endpoint check belongs to the module that owns it and reaches
this target through the same checkers the DE10-Lite's composed image uses, one
hierarchy level down.

What this module states is what the board adds:

- the placed and virtual port sets an image someone programs must have, so a
  slipped or dropped pin refuses the build rather than reaching a board;
- the drive strength and slew rate this family's fitter asks for on the
  readout's pins, taken from the standard each pin's own board record supplies;
- the CRC-32 of the carried ROM, reaching the readout as one compiled constant
  and checked against the packager's own record of the image;
- the checked synchronizer chain behind every asynchronous board input, the
  twelve control inputs as well as the reset.

Pin data and the readout scheme live on the
[board page](../../wiki/src/de2-115-board.md); this module never restates a pin
number.
"""
import json
from pathlib import Path
import re

from . import fpga_controls, fpga_vga, fpga_vga_dac

TOP = "de2_system_proof"
# The composition is one instance below this top, so every hierarchy string the
# shared checkers build carries this prefix.
PREFIX = "u_system|"
BRIDGE_PREFIX = PREFIX + "u_bridge|"
# The same identity macro the DE10-Lite's composed images carry: it is the same
# `n2m_v05_system` BUILD_ID, and this board reads it off its own displays
# instead of over a host link.
IDENTITY_MACRO = "N2M_V05_BUILD_ID"
# Both the wrapper and the composition declare BUILD_ID, so the synthesis report
# states the compiled constant twice.
IDENTITY_INSTANCES = 2
# The carried ROM's CRC-32, as one 32-bit compiled constant for the readout. The
# value comes from the packager's own record of the image it wrote, so the
# displayed number cannot be a different image's.
CRC_MACRO = "N2M_DE2_ROM_CRC32"
CRC_PARAMETER = "ROM_CRC32"
DIGITS = 8
SEGMENTS = 7
HEX_PORTS = tuple(f"hex{digit}_n[{segment}]" for digit in range(DIGITS) for segment in range(SEGMENTS))
# Every output pin this image drives: the video DAC's and the readout's.
DRIVE_PORTS = (*fpga_vga_dac.DRIVE_PORTS, *HEX_PORTS)
CONTROL_PORTS = ("board_reset_n", "key_action_n[0]", "key_action_n[1]",
                 *(f"sw_buttons[{i}]" for i in range(8)), *(f"sw_view[{i}]" for i in range(3)))
PLACED = frozenset(("clk_reference", *CONTROL_PORTS, *DRIVE_PORTS))
VIRTUAL = frozenset(("paused", "fault", "display_sequence[*]", "display_epoch[*]"))
# Each asynchronous control input's own two forced synchronizer stages inside the
# shared button filter instance that samples it. KEY[0] is not here: it is the
# reset, and the reset control's own chain is checked with the clocking evidence.
CHAINS = tuple(
    (name, port, f"{instance}|button_meta[{bit}]", f"{instance}|button_sync[{bit}]")
    for name, port, instance, bit in
    [(f"sw{i}", f"sw_buttons[{i}]", "u_switch_low", i) for i in range(4)]
    + [(f"sw{i}", f"sw_buttons[{i}]", "u_switch_high", i - 4) for i in range(4, 8)]
    + [(f"key{i}", f"key_action_n[{i}]", "u_keys", i) for i in range(2)]
    + [(f"view{i}", f"sw_view[{i}]", "u_view", i) for i in range(3)])


def system_target(target):
    """Whether this target is the DE2-115 system image."""
    return target.get("top") == TOP


def validate(target):
    """An image someone programs states exactly this board's ports, and no other.

    The pin numbers are the board page's and the registry's; what is checked here
    is that the image places every port a programmed board needs and leaves only
    the diagnostic outputs virtual, so a dropped readout pin or a picture pin
    moved to a virtual one refuses the build instead of reaching a board.
    """
    if set(target.get("pins", {})) != PLACED or set(target.get("virtual_pins", [])) != VIRTUAL:
        raise ValueError("de2-system requires this board's placed control, picture and readout pins "
                         "with diagnostic-only virtual outputs")


def hierarchy(text):
    """Rewrite a shared checker's `u_bridge|` strings into this composition's."""
    return text.replace("u_bridge|", BRIDGE_PREFIX)


def constraints(quote):
    """The composed pixel path's checked collections and the control chains'.

    `lcd` selects the blank-control profile. The standalone DAC fixture generates
    its own pixels and asserts no blank, so it does not need it; this image is the
    whole composition, whose PPU asserts blank, and that assertion crosses from
    the pixel clock to the system clock. Without the profile that crossing is the
    one path in the image with no exception, and the fit fails setup on it at
    every corner while everything else keeps more than 5 ns.
    """
    return (hierarchy(fpga_vga.constraints(quote, lcd=True, outputs=fpga_vga_dac.DAC))
            + fpga_controls.constraints(quote, chains=CHAINS))


def audit(quote):
    return (hierarchy(fpga_vga.audit(quote, lcd=True, outputs=fpga_vga_dac.DAC))
            + fpga_controls.audit(quote, chains=CHAINS))


def required_reports():
    return (fpga_vga.required_reports(lcd=True, outputs=fpga_vga_dac.DAC)
            + fpga_controls.required_reports(chains=CHAINS))


def image_crc(folder):
    """The carried image's CRC-32, from the packager's record in this attempt."""
    record = json.loads((Path(folder) / "preload.json").read_text(encoding="utf-8"))
    value = record["image_crc32"]
    if not isinstance(value, int) or not 0 <= value <= 0xffffffff:
        raise ValueError("carried ROM image CRC-32 is not a 32-bit value")
    return value


def assignments(folder):
    """The readout's ROM CRC macro, from the packaged image in this attempt."""
    return [f"""set_global_assignment -name VERILOG_MACRO "{CRC_MACRO}=32'h{image_crc(folder):08x}\""""]


def verify_rom_crc(folder):
    """The displayed CRC is the packaged image's, in the project and as compiled.

    A constant in the source is not evidence that the constant reached the
    design, so both ends are read: the generated project states the packager's
    value exactly once, and the synthesis report states the same 32 bits as the
    parameter the readout selects.
    """
    folder = Path(folder)
    expected = image_crc(folder)
    line = f"""set_global_assignment -name VERILOG_MACRO "{CRC_MACRO}=32'h{expected:08x}\""""
    qsf = (folder / "design.qsf").read_text(encoding="utf-8")
    if [text for text in qsf.splitlines() if CRC_MACRO in text] != [line]:
        raise ValueError("generated ROM CRC macro differs from the packaged image's")
    report = (folder / "output/design.map.rpt").read_text(encoding="utf-8")
    values = re.findall(rf";\s*{CRC_PARAMETER}\s*;\s*([01]+)\s*;\s*Unsigned Binary\s*;", report)
    if values != [f"{expected:032b}"]:
        raise ValueError("compiled ROM CRC constant differs from the packaged image's")
    return f"{expected:08x}"


def verify(folder, *, system_clock, system_net):
    """The board side of this image: its picture path, its DAC and its chains."""
    folder = Path(folder)
    reports = {}
    for name in fpga_vga.required_reports(lcd=True, outputs=fpga_vga_dac.DAC):
        path = folder / "output" / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("missing composed VGA path evidence: " + name)
        reports[name] = path.read_text(encoding="utf-8")
    evidence = {"vga_paths": fpga_vga.verify_paths(reports, lcd=True, system_clock=system_clock,
                                                  bridge_prefix=BRIDGE_PREFIX,
                                                  outputs=fpga_vga_dac.DAC),
                "dac": {"channel_bits": fpga_vga_dac.CHANNEL_BITS,
                        "controls": dict(sorted(fpga_vga_dac.CONTROLS.items())),
                        "clock_port": fpga_vga_dac.CLOCK_PORT, "clock": fpga_vga_dac.CLOCK_NAME,
                        **fpga_vga_dac.verify_controls(folder)},
                "controls": fpga_controls.verify_reports(folder, chains=CHAINS, system_clock=system_clock),
                "readout": {"digits": DIGITS, "segments": SEGMENTS,
                            "polarity": "a segment lights on a low level (common anode)",
                            "views": 8, "selector": "sw_view[2:0]"}}
    return evidence
