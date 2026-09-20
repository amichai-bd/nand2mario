"""Select a device family's clocking evidence implementation, or refuse the build.

Clock generation and every clocking check are family-specific: the vendor IP,
its instance hierarchy, its fit-report shape and its netlist primitives all
differ. Each supported family owns one implementation module with the surface
`fpga.py` uses. A family without one has no clocking evidence, so its build is
refused here rather than continuing with the checks skipped.

The reset chain audit and its report check are the family-neutral part: the
chain register and pin names come from `n2m_reset_control`, which is shared RTL.
"""
import math
import re

# Every family with a clocking evidence implementation, and the module that owns it.
# Two of them are ALTPLL families and share one implementation's checks through
# their own modules; adding a family is still an explicit entry here, never a
# lookup that falls back to another family's checks.
IMPLEMENTATIONS = {"MAX 10": "fpga_pll", "Cyclone V": "fpga_pll_cyclonev",
                   "Cyclone IV E": "fpga_pll_cycloneive"}
CHAINS = ("board_release", "lock_samples", "sys_release", "pix_release")
# Quartus writes design.fit.rpt in cp1252 on every host; the MAX 10 and
# Cyclone IV E reports both carry the degree sign (0xb0) in their junction
# temperatures, which utf-8 refuses. The encoding belongs to Quartus, not to the
# host, so every family reads the report through this one fact.
FIT_ENCODING = "cp1252"


def implementation(family):
    """The clocking implementation for this device family.

    Raises for any family without one. No caller may treat a missing
    implementation as "no checks needed": a target that declares generated
    clocks and cannot be checked must fail.
    """
    if not isinstance(family, str) or family not in IMPLEMENTATIONS:
        raise ValueError(f"no clocking evidence implementation for FPGA family: {family!r}")
    from importlib import import_module
    return import_module("." + IMPLEMENTATIONS[family], __package__)


def chain_audit(quote):
    """Tcl that binds each reset chain stage and times the path between them."""
    lines = []
    for name in CHAINS:
        for i in (0, 1):
            endpoint = quote(f"u_clocking|u_reset|{name}[{i}]")
            message = quote(f"missing reset stage: {name}[{i}]")
            lines.extend([f"set chain_{i} [get_registers {endpoint}]",
                          f'if {{[get_collection_size $chain_{i}] != 1}} {{error {message}}}'])
        for check in ("setup", "hold"):
            lines.append(f"report_timing -from $chain_0 -to $chain_1 -{check} -npaths 1 -detail full_path -file output/chain_{name}_{check}.rpt")
    return "\n".join(lines) + "\n"


def required_reports():
    """The metastability, clock transfer and reset chain reports every family keeps."""
    return ["metastability.rpt", "clock_transfers.rpt"] + [f"chain_{name}_{check}.rpt" for name in CHAINS for check in ("setup", "hold")]


def verify_reports(folder, message):
    """Every required report exists, is non-empty, and each chain path is timed and met."""
    for name in required_reports():
        path = folder / "output" / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"missing clocking analysis: {name}")
        if not name.startswith("chain_"):
            continue
        chain, check = name.removeprefix("chain_").removesuffix(".rpt").rsplit("_", 1)
        text = path.read_text(encoding="utf-8")
        result = re.findall(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)\.  Worst case slack is (\S+)", text)
        if (len(result) != 1 or not math.isfinite(float(result[0])) or float(result[0]) < 0
                or any(f"u_reset|{chain}[{i}]" not in text for i in (0, 1))):
            raise ValueError(f"{message}: {name}")
