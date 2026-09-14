#!/usr/bin/env python3
"""Compare Quartus netlist identity between two FPGA build trees.

For every target built under both trees, the resource summary, the map and fit
resource-utilization-by-entity hierarchy rows, the map resource usage summary
and the post-fit simulation netlist (when a target retains one) must be
identical. Timestamps and the attempt path are the only permitted differences.
A PASS build with a missing report or missing netlist fails the comparison;
each passing target records the fields that were actually compared.

Usage, from PowerShell in a Windows checkout, after building every target of
src/fpga/de10_lite/targets.json on the baseline and on the head with the same
Quartus installation:

    python tools/fpga_netlist_compare.py --baseline <baseline-checkout> <baseline-tag> --head <head-checkout> <head-tag> [--json <report>]

Each pair names a checkout root and the build tag under its workdir/builds.
Exit status is zero only when every common target matches and no target is
missing from either side.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

REGISTRY = "src/fpga/de10_lite/targets.json"
NETLIST = "simulation/questa/design.vo"
SECTIONS = {
    "map_entity_rows": ("design.map.rpt", "Analysis & Synthesis Resource Utilization by Entity"),
    "fit_entity_rows": ("design.fit.rpt", "Fitter Resource Utilization by Entity"),
    "map_resource_summary": ("design.map.rpt", "Analysis & Synthesis Resource Usage Summary"),
    "fit_resource_summary": ("design.fit.rpt", "Fitter Resource Usage Summary"),
}
DATE = re.compile(r" - [A-Z][a-z]{2} [A-Z][a-z]{2} +\d+ \d\d:\d\d:\d\d \d{4}")


def summary_rows(text):
    """The fit summary without its status timestamp."""
    return [DATE.sub("", line.rstrip()) for line in text.splitlines() if line.strip()]


def table_rows(text, title):
    """The body rows of the named report table, without the box-drawing lines."""
    lines = text.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("; " + title) and line.rstrip().endswith(";")]
    if len(starts) != 1:
        raise ValueError(f"report table '{title}' found {len(starts)} times")
    rows, rules = [], 0
    for line in lines[starts[0] + 1:]:
        if line.startswith("+"):
            rules += 1
            if rules == 3:
                break
            continue
        if line.startswith(";"):
            rows.append(re.sub(r"\s+;", " ;", line.rstrip()))
    if rules < 3:
        raise ValueError(f"report table '{title}' is not terminated")
    return rows


def netlist_digest(path):
    """SHA-256 of the post-fit netlist with its header comment removed.

    The header carries the generation date and the attempt path; the body
    is the fitted cell list and its connectivity.
    """
    body = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not body and (line.startswith("//") or not line.strip()):
            continue
        body.append(line.rstrip())
    return hashlib.sha256("\n".join(body).encode("utf-8")).hexdigest()


def attempt_directory(root, tag, target):
    """The attempt folder and the record status; a deliberate FAIL is still compared."""
    record_path = root / "workdir/builds" / tag / "fpga" / target / "result.json"
    if not record_path.is_file():
        return None, None, "no result.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if record.get("status") not in ("PASS", "FAIL"):
        return None, None, f"status {record.get('status')}"
    if record["status"] == "PASS":
        return root / record["evidence_directory"], record, None
    return (root / record["attempt_result"]).parent, record, None


REQUIRED_REPORTS = ("design.fit.summary", "design.map.rpt", "design.fit.rpt")
NETLIST_SOURCES = ("src/rtl/common/n2m_intel_ram.sv", "src/rtl/input/n2m_adc_backend.sv")


def needs_netlist(definition):
    """The same rule as tools/n2m/fpga.py: PLL, Intel RAM or ADC targets retain design.vo."""
    return "pll" in definition or any(source in definition.get("sources", []) for source in NETLIST_SOURCES)


def identity(folder, record, definition):
    """Every comparable fact of one build, plus the list of fields actually compared.

    A PASS record must have every required report, and design.vo when the
    target retains one; a missing file is a ValueError, never a silent None.
    The *-invalid targets fail by design, so a FAIL record contributes its
    error text and whatever reports Quartus wrote before stopping.
    """
    output = folder / "output"
    passing = record["status"] == "PASS"
    result = {"status": record["status"],
              "error": re.sub(r"attempts[\\/][0-9a-f]+", "attempts/<id>", record.get("error", "")) or None}
    compared = ["status", "error"]
    if passing:
        for name in REQUIRED_REPORTS:
            if not (output / name).is_file():
                raise ValueError(f"missing report {name}")
    summary = output / "design.fit.summary"
    result["fit_summary"] = summary_rows(summary.read_text(encoding="utf-8")) if summary.is_file() else None
    if result["fit_summary"] is not None:
        compared.append("fit_summary")
    reports = {}
    for key, (report, title) in SECTIONS.items():
        if report not in reports:
            path = output / report
            reports[report] = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
        result[key] = table_rows(reports[report], title) if reports[report] is not None else None
        if result[key] is not None:
            compared.append(key)
    netlist = folder / NETLIST
    if passing and needs_netlist(definition) and not netlist.is_file():
        raise ValueError(f"missing post-fit netlist {NETLIST}")
    result["netlist_sha256"] = netlist_digest(netlist) if netlist.is_file() else None
    if result["netlist_sha256"] is not None:
        compared.append("netlist_sha256")
    return result, compared


def first_difference(baseline, head):
    for key in baseline:
        if baseline[key] != head[key]:
            if isinstance(baseline[key], list) and isinstance(head[key], list):
                for index, (left, right) in enumerate(zip(baseline[key], head[key])):
                    if left != right:
                        return key, f"row {index}: {left!r} != {right!r}"
                return key, f"row count {len(baseline[key])} != {len(head[key])}"
            return key, f"{baseline[key]} != {head[key]}"
    return None, None


def compare(baseline_root, baseline_tag, head_root, head_tag):
    definitions = json.loads((head_root / REGISTRY).read_text(encoding="utf-8"))["targets"]
    report = {"baseline": {"root": str(baseline_root), "tag": baseline_tag},
              "head": {"root": str(head_root), "tag": head_tag}, "targets": {}, "status": "PASS"}
    for target in sorted(definitions):
        entry = {"status": "PASS"}
        sides, compared = {}, {}
        for side, root, tag in (("baseline", baseline_root, baseline_tag), ("head", head_root, head_tag)):
            folder, record, problem = attempt_directory(root, tag, target)
            if problem:
                entry.update(status="MISSING", reason=f"{side}: {problem}")
                break
            try:
                sides[side], compared[side] = identity(folder, record, definitions[target])
            except ValueError as error:
                entry.update(status="FAIL", reason=f"{side}: {error}")
                break
            entry[side] = {"attempt": str(folder.relative_to(root)), "build_status": record["status"],
                           "netlist_sha256": sides[side]["netlist_sha256"]}
        if entry["status"] == "PASS":
            entry["compared_fields"] = compared["head"]
            key, detail = first_difference(sides["baseline"], sides["head"])
            if key:
                entry.update(status="FAIL", field=key, detail=detail)
            elif sides["head"]["status"] == "FAIL":
                entry["note"] = "both builds fail identically (deliberate invalid target)"
            elif len(compared["head"]) < 2 + len(SECTIONS) + 1:
                entry.update(status="FAIL", reason="incomplete comparison: " + ", ".join(compared["head"]))
        if entry["status"] != "PASS":
            report["status"] = "FAIL"
        report["targets"][target] = entry
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--baseline", nargs=2, metavar=("ROOT", "TAG"), required=True)
    parser.add_argument("--head", nargs=2, metavar=("ROOT", "TAG"), required=True)
    parser.add_argument("--json", type=Path, help="write the full report here")
    args = parser.parse_args(argv)
    report = compare(Path(args.baseline[0]).resolve(), args.baseline[1], Path(args.head[0]).resolve(), args.head[1])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for target, entry in report["targets"].items():
        detail = entry.get("reason") or (f"{entry.get('field')}: {entry.get('detail')}" if entry["status"] == "FAIL" else "")
        if entry["status"] == "PASS":
            detail = f"compared={len(entry['compared_fields'])} fields" + (" (netlist)" if "netlist_sha256" in entry["compared_fields"] else "")
        print(f"{entry['status']:8} {target} {detail}".rstrip())
    print(f"{report['status']}: netlist identity over {len(report['targets'])} targets")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
