"""Worst hold paths of the system and SDRAM clocks, retained per corner.

The timing summary keeps one hold slack per clock; the fitter only pushes hold
to a non-negative value, so a shrinking slack has no visible endpoint until it
fails. These reports name the few worst paths captured by each clock so the
pair can be watched across fits. They are evidence only: pass/fail stays with
the summary and structural checks in fpga.timing_evidence.
"""
import re

from . import fpga_pll, fpga_vga

NPATHS = 5
# label -> destination clock. TimeQuest attributes a hold check to its latch
# clock, so -to_clock names the same paths the summary's per-clock entry does.
CLOCKS = {"system": fpga_pll.SYSTEM_CLOCK, "sdram": fpga_pll.SDRAM_CLOCK}
MODELS = {corner: f"{model.title()} 1200mV {temperature}C Model" for corner, model, temperature in fpga_vga.CORNERS}
FOUND = re.compile(r"Report Timing: Found (\d+) hold paths \((\d+) violated\)\.\s+Worst case slack is (\S+)")
EMPTY = "Report Timing: No paths to report."
COLUMNS = ("slack_ns", "from", "to", "launch_clock", "latch_clock", "relationship_ns", "clock_skew_ns", "data_delay_ns")


def report_name(corner, label):
    return f"hold_{corner}_{label}.rpt"


def required_reports():
    return [report_name(corner, label) for corner, _, _ in fpga_vga.CORNERS for label in CLOCKS]


def audit(quote):
    """Tcl appended to the audit: per corner, the worst hold paths into each clock."""
    lines = []
    for corner, model, temperature in fpga_vga.CORNERS:
        lines += [f"set_operating_conditions -model {model} -voltage 1200 -temperature {temperature}", "update_timing_netlist"]
        for label, clock in CLOCKS.items():
            lines += [f"set hold_{label} [get_clocks {quote(clock)}]",
                      f'if {{[get_collection_size $hold_{label}] != 1}} {{error "hold audit clock mismatch: {label}"}}',
                      f"report_timing -to_clock $hold_{label} -hold -npaths {NPATHS} -detail full_path -file output/{report_name(corner, label)}"]
    return "\n".join(lines) + "\n"


def parse(text, *, corner, clock):
    """Rows of one report: found/violated counts and the summary-table paths.

    The report must be for the expected delay model and destination clock;
    the table must agree with its header. Slack signs are recorded, not judged.
    """
    if f"Delay Model:\n    {MODELS[corner]}" not in text.replace("\r\n", "\n"):
        raise ValueError(f"hold path report corner differs: {corner}")
    if EMPTY in text:
        return {"found": 0, "violated": 0, "worst_slack_ns": None, "paths": []}
    header = FOUND.findall(text)
    if len(header) != 1:
        raise ValueError("missing or malformed hold path report header")
    found, violated, worst = int(header[0][0]), int(header[0][1]), fpga_vga.number(header[0][2])
    rows = [r for r in fpga_vga.rows(fpga_vga.summary(text)) if len(r) == len(COLUMNS) and r[0] != "Slack"]
    if len(rows) != found or not 0 < found <= NPATHS:
        raise ValueError("hold path report table and header disagree")
    paths = []
    for row in rows:
        path = {"slack_ns": fpga_vga.number(row[0]), "from": fpga_vga.node(row[1]), "to": fpga_vga.node(row[2]),
                "launch_clock": row[3], "latch_clock": row[4], "relationship_ns": fpga_vga.number(row[5]),
                "clock_skew_ns": fpga_vga.number(row[6]), "data_delay_ns": fpga_vga.number(row[7])}
        if path["latch_clock"] != clock:
            raise ValueError("hold path latched by another clock")
        paths.append(path)
    if paths[0]["slack_ns"] != worst or any(a["slack_ns"] > b["slack_ns"] for a, b in zip(paths, paths[1:])):
        raise ValueError("hold path report is not ordered from the worst slack")
    if sum(p["slack_ns"] < 0 for p in paths) != violated:
        raise ValueError("hold path violation count differs from its rows")
    return {"found": found, "violated": violated, "worst_slack_ns": worst, "paths": paths}


def verify(folder):
    """Read every retained hold report; return the per-clock corners and the worst path of each clock."""
    output = folder / "output"
    clocks = {}
    for label, clock in CLOCKS.items():
        corners = {}
        worst = None
        for corner, _, _ in fpga_vga.CORNERS:
            name = report_name(corner, label)
            path = output / name
            if not path.is_file() or not path.stat().st_size:
                raise ValueError("missing hold path report: " + name)
            parsed = parse(path.read_text(encoding="utf-8"), corner=corner, clock=clock)
            corners[corner] = {"report": name, **parsed}
            if parsed["paths"] and (worst is None or parsed["worst_slack_ns"] < worst["slack_ns"]):
                worst = {"corner": corner, "report": name, **parsed["paths"][0]}
        clocks[label] = {"clock": clock, "worst": worst, "corners": corners}
    return {"npaths": NPATHS, "clocks": clocks}


def summary_lines(evidence):
    """Human-readable worst hold path per clock for the build's text output."""
    lines = []
    for label, entry in (evidence or {}).get("clocks", {}).items():
        worst = entry.get("worst")
        if worst is None:
            lines.append(f"Worst hold ({label} {entry['clock']}): no paths reported")
            continue
        lines.append(f"Worst hold ({label} {entry['clock']}): {worst['slack_ns']:.3f} ns at {worst['corner']}, "
                     f"{worst['from']} -> {worst['to']} ({worst['report']})")
    return lines
