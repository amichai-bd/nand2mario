"""Cyclone IV E clocking: the DE10-Lite's ALTPLL path, on this family's atoms.

ALTPLL serves Cyclone IV E, so nothing here reimplements clock generation or the
lock, metastability, reset-chain and clock-transfer evidence. Every check comes
from [fpga_pll.py](fpga_pll.py); this module states only what the family
genuinely changes:

- the generator's `INTENDED_DEVICE_FAMILY` and the `intended_device_family` the
  generated HDL must state back, which are the family itself;
- the installed simulation atom model, because each family ships its own and its
  hash enters the request fingerprint;
- the netlist primitive table, because the fitted atoms are named `cycloneive_*`
  where MAX 10's are `fiftyfivenm_*`;
- its own supported proof top;
- one extra fitter diagnostic, which this board's single clock pin produces.

Everything else was measured identical on the `de2-clocking` fit: the ALTPLL
wrapper and instance hierarchy, the solved M, N and C counters, the analysed
clock inventory, the reset chain, and the whole parallel lock topology down to
the primitive parameter sets. ALTPLL's own facts therefore stay in one place;
see [the builder contract](../../wiki/tools/n2m/SPEC.md#cyclone-iv-e-altpll).
"""
import re

from . import fpga_lock, fpga_pll

TOOLS_KEY = fpga_pll.TOOLS_KEY
FAMILY = "Cyclone IV E"
# The simulation atom model this family installs, against MAX 10's
# `fiftyfivenm_atoms.v`. Its hash is part of the request fingerprint.
ATOM_MODEL = "eda/sim_lib/cycloneive_atoms.v"
# This board's own proof tops, whose exact `u_clocking` hierarchy these checks
# recognize. Both instantiate the DE10-Lite's ALTPLL wrapper in place, so the
# hierarchy is that board's; the top names are this one's.
SUPPORTED_TOPS = ("de2_clocking_proof", "de2_vga_proof", "de2_system_proof")
# ALTPLL's own facts, reused rather than restated: the report encoding, the reset
# chain audit and its report inventory, and the fitted instance hierarchy each
# check and constraint names. The hierarchy holds because this board fits the
# same `n2m_clocking` wrapper the DE10-Lite does.
FIT_ENCODING = fpga_pll.FIT_ENCODING
CHAINS = fpga_pll.CHAINS
chain_audit = fpga_pll.chain_audit
required_reports = fpga_pll.required_reports
SYSTEM_PLL = fpga_pll.SYSTEM_PLL
PIXEL_PLL = fpga_pll.PIXEL_PLL
SYSTEM_CLOCK = fpga_pll.SYSTEM_CLOCK
PIXEL_CLOCK = fpga_pll.PIXEL_CLOCK
SYSTEM_NET = fpga_pll.SYSTEM_NET
# The same two instances as the Fitter's own entity-qualified names them.
FIT_INSTANCES = fpga_pll.MERGE_PAIR
# The netlist primitives this family's checked functional netlist may contain,
# with their output ports, read from `cycloneive_atoms.v`. Every type and port
# matches MAX 10's but for the name, minus the hardware this family does not
# have: no ADC block and no internal flash. The M9K atom is here because
# `de2-vga` places the frame bridge's three banks; `altsyncram` selects M9K on
# this family exactly as it does on MAX 10, so only the atom's name differs.
OUTPUTS = {
    "dffeas": {"q"},
    "cycloneive_lcell_comb": {"combout", "cout"},
    "cycloneive_clkctrl": {"outclk"},
    "cycloneive_io_ibuf": {"o"},
    "cycloneive_io_obuf": {"o", "obar"},
    "cycloneive_ram_block": {"portadataout", "portbdataout"},
    "cycloneive_pll": {"locked", "clk", "fbout", "phasedone", "scandataout", "scandone",
                       "activeclock", "vcooverrange", "vcounderrange", "clkbad"},
}
PRIMITIVES = fpga_lock.Primitives(OUTPUTS, "cycloneive_pll", "cycloneive_lcell_comb",
                                  "cycloneive_clkctrl")
# The one definition this family supports: the clock contract's 25 MHz system and
# 25.2 MHz pixel clocks from the 50 MHz reference. The single-PLL shape is not
# registered here, so the single-PLL lock checker, which recognizes MAX 10
# primitives only, is never reached.
DEFINITION = {"module": "n2m_pixel_pll", "input_ps": 20000, "multiply": 63, "divide": 125,
              "system_divide": 2}
# The fitter's compensation caution, which this board cannot avoid: the DE2-115
# brings its 50 MHz reference to one dedicated clock input, and this composition
# has two PLLs, so one of them reaches the pin over the remote dedicated path the
# fitter cannot fully compensate. Both still take the pin over a dedicated path,
# which `verify_fit` requires as `Inclk0 signal type: Dedicated Pin`; forcing the
# remote PLL to a location the pin does not reach that way replaces its dedicated
# clock path with a routed one instead of removing the fact.
COMPENSATION = re.compile(r'Critical Warning \(176598\): PLL "(\S+)" input clock inclk\[0\] is not '
                          r'fully compensated because it is fed by a remote clock pin "Pin_(\w+)"'
                          r' File: \S+ Line: \d+')
COMPENSATION_REASON = (
    "The board routes its 50 MHz reference to one dedicated clock input, so with two PLLs the "
    "fitter places one of them where the pin arrives over the remote dedicated path. Both PLLs "
    "still take the pin directly (Inclk0 signal type: Dedicated Pin) and no timing relationship "
    "in this design references the reference pin, so the uncompensated share of its pad delay "
    "reaches nothing the analysis checks.")
LOCATION = re.compile(r'(?m)^set_location_assignment PIN_(\w+) -to "clk_reference"$')


def validate(definition):
    """The one supported definition; anything else refuses before a tool launches."""
    if definition != DEFINITION:
        raise ValueError("unsupported PLL definition")
    fpga_pll.validate(definition)


def generated_sources(definition):
    validate(definition)
    return fpga_pll.generated_sources(definition)


def assignments(definition):
    validate(definition)
    return fpga_pll.assignments(definition)


def cache_files(definition):
    validate(definition)
    return fpga_pll.cache_files(definition)


def timed_clocks(target):
    return fpga_pll.timed_clocks(target)


def corner_slacks(target, corner):
    return fpga_pll.corner_slacks(target, corner)


def no_clock_rows(target):
    """Two ALTPLL lock event latches, one per instance, as MAX 10 names them."""
    if target["top"] not in SUPPORTED_TOPS:
        raise ValueError("unsupported Cyclone IV E PLL proof top")
    return fpga_pll.no_clock_rows(target)


def lock_event_count(target):
    return len(no_clock_rows(target))


def identity(directory):
    return fpga_pll.identity(directory, atom_model=ATOM_MODEL)


def generation_command(identity, definition):
    validate(definition)
    return fpga_pll.generation_command(identity, definition, FAMILY)


def generate(folder, identity, definition, execute, timeout, record, build, *, device=None):
    validate(definition)
    return fpga_pll.generate(folder, identity, definition, execute, timeout, record, build,
                             device=device, family=FAMILY)


def verify(folder, definition=None):
    """The generated HDL states this family back, not the one it was copied from."""
    validate(DEFINITION if definition is None else definition)
    return fpga_pll.verify(folder, DEFINITION if definition is None else definition, family=FAMILY)


def verify_fit(folder, target):
    return fpga_pll.verify_fit(folder, target)


def verify_lock_event(folder, checks, top=SUPPORTED_TOPS[0], *, parallel=False, rows=()):
    if top not in SUPPORTED_TOPS:
        raise ValueError("unsupported Cyclone IV E PLL proof top")
    if not parallel:
        raise ValueError("Cyclone IV E clocking registers both PLLs; there is no single-PLL target")
    return fpga_pll.verify_lock_event(folder, checks, top, parallel=True,
                                      rows=rows, primitives=PRIMITIVES)


def explained_diagnostics(text, folder, definition):
    """ALTPLL's merge refusal, plus this board's one compensation caution.

    The caution is added here rather than in the shared ALTPLL module so MAX 10,
    whose clock pin feeds both its PLLs locally, keeps refusing it. Exactly one
    line is accepted, it must name one of this composition's two fitted PLLs, and the
    pin it names must be the one this attempt's own project file assigns to
    `clk_reference`, so a caution about a different pin or a third PLL still
    fails the build.
    """
    explained = list(fpga_pll.explained_diagnostics(text, folder, definition, family=FAMILY))
    lines = [line.strip() for line in text.splitlines()
             if line.strip().startswith("Critical Warning (176598):")]
    if not lines:
        return explained
    located = LOCATION.findall((folder / "design.qsf").read_text(encoding="utf-8"))
    match = COMPENSATION.fullmatch(lines[0])
    if (len(lines) != 1 or len(located) != 1 or not match
            or match[1] not in FIT_INSTANCES or match[2] != located[0]):
        raise ValueError("PLL input compensation diagnostic identity/count differs")
    return explained + [{"code": "176598", "text": lines[0], "reason": COMPENSATION_REASON}]
