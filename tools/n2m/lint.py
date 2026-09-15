"""Questa compile gate: vlog every product source, vopt every FPGA top, no vsim.

The gate proves a second front end accepts the RTL that Verilator and Quartus
already see. It needs no runtime license because vsim is never launched.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import uuid

from .fpga import REGISTRY, target_definition
from .hdl import dependencies
from .progress import Progress
from .questa import diagnostic
from .records import atomic_json, file_hash
from .simulator import QUESTA_COMPILE_TOOLS, ToolError, questa_tools, run_tool

RTL = "src/rtl"
# Vendor units Quartus generates or installs at build time. The gate binds the
# repository RTL to their ports through these empty stand-ins; it never claims
# vendor behavior. The file declares exactly the units listed here.
STAND_INS = "src/dv/builder/questa_lint_vendor.sv"
STAND_IN_UNITS = ("n2m_system_pll", "n2m_pixel_pll", "n2m_adc_pll", "altera_modular_adc_control", "altsyncram")
# --inject-fault adds this module: Verilator accepts it and Questa rejects it.
FAULT = "src/dv/builder/questa_lint_fault.sv"
FAULT_TOP = "questa_lint_fault"
TOOL_TIMEOUT = 300
ERROR_LINE = re.compile(r"(?im)^.*\*\* (?:Error|Fatal)\b.*$")
SOURCE_NAME = re.compile(r"(?<![A-Za-z0-9_./-])((?:[A-Za-z]:)?[^\s\"'()]*?[A-Za-z0-9_]+\.svh?)(?:\((\d+)\))?")


def product_sources(root):
    """Every SystemVerilog file under src/rtl, in a stable order."""
    return sorted(path.relative_to(root).as_posix() for path in (root / RTL).rglob("*.sv")
                  if path.is_file() and not path.is_symlink())


def fpga_tops(root):
    """Map each registered FPGA top to its registry targets and synthesis sources."""
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    tops = {}
    for name in sorted(registry.get("targets", {})):
        target = target_definition(root, name)
        entry = tops.setdefault(target["top"], {"targets": [], "sources": []})
        entry["targets"].append(name)
        entry["sources"].extend(source for source in target["sources"] if source not in entry["sources"])
    return tops


def package_order(root, sources):
    """Packages first, each after the packages it names; then the rest sorted.

    vlog resolves a package reference only against a package compiled earlier
    in the same invocation, so file order is part of the command.
    """
    packages = {}
    for source in sources:
        text = strip_comments((root / source).read_text(encoding="utf-8"))
        match = re.search(r"^\s*package\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", text, re.M)
        if match:
            packages[match[1]] = (source, text)
    ordered = []
    placed = set()

    def place(name, trail):
        if name in placed:
            return
        if name in trail:
            raise ValueError("cyclic package reference: " + " -> ".join([*trail, name]))
        source, text = packages[name]
        for other in sorted(packages):
            if other != name and re.search(r"\b" + re.escape(other) + r"\s*::", text):
                place(other, [*trail, name])
        placed.add(name)
        ordered.append(source)

    for name in sorted(packages):
        place(name, [])
    return ordered + [source for source in sources if source not in ordered]


def strip_comments(text):
    return re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else " ", text)


def stand_in_units(root):
    text = strip_comments((root / STAND_INS).read_text(encoding="utf-8"))
    return tuple(re.findall(r"^\s*module\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M))


def plan(root, inject_fault=False):
    """The ordered compile set and the tops to elaborate; validated before any tool runs."""
    if stand_in_units(root) != STAND_IN_UNITS:
        raise ValueError(f"{STAND_INS} must declare exactly {', '.join(STAND_IN_UNITS)}")
    sources = product_sources(root)
    if not sources:
        raise ValueError(f"no SystemVerilog sources under {RTL}")
    tops = fpga_tops(root)
    for entry in tops.values():
        sources.extend(source for source in entry["sources"] if source not in sources)
    sources.append(STAND_INS)
    if inject_fault:
        sources.append(FAULT)
        tops[FAULT_TOP] = {"targets": [], "sources": [FAULT], "injected": True}
    closure = dependencies(root, sources)
    return {"sources": package_order(root, sources), "tops": tops,
            "inputs": {name: file_hash(root / name) for name in closure}}


def named_errors(output):
    """Every error line, with the source files and modules it names."""
    lines = ERROR_LINE.findall(output)
    names = []
    for line in lines:
        for path, _ in SOURCE_NAME.findall(line):
            names.append(Path(path.replace("\\", "/")).name)
        names.extend(re.findall(r"(?:module|design unit|Module|Design unit)\s+'([A-Za-z_][A-Za-z0-9_]*)'", line))
    return lines, sorted(set(names))


def lint_questa(root, build, args, provenance, progress=None):
    progress = progress or Progress(False)
    started = time.monotonic()
    attempt = build / "lint" / "questa" / uuid.uuid4().hex[:12]
    attempt.mkdir(parents=True)
    report = {"status": "FAIL", "stage": "lint questa", "provenance": provenance,
              "attempt": attempt.relative_to(root).as_posix(),
              "attempt_result": (attempt / "result.json").relative_to(root).as_posix(),
              "inject_fault": bool(getattr(args, "inject_fault", False)),
              "started": datetime.now(timezone.utc).isoformat(), "commands": [],
              "stand_ins": list(STAND_IN_UNITS), "simulation": "none; vsim is never launched"}
    try:
        # The tree is validated before any tool is probed, so a bad plan never
        # spends a tool launch and a missing tool never hides a bad plan.
        selected = plan(root, report["inject_fault"])
        report.update(sources=selected["sources"], inputs=selected["inputs"],
                      tops={top: entry for top, entry in selected["tops"].items()})
        with progress.stage("Discover Questa compile tools"):
            tools, info = questa_tools(getattr(args, "questa_bin", None), QUESTA_COMPILE_TOOLS)
        report["tools"] = info["tools"]
        progress.line(f"Questa compile gate: {len(selected['sources'])} sources, {len(selected['tops'])} tops")
        library = (attempt / "work").as_posix()

        def execute(label, argv, log):
            record = {"label": label, "argv": argv, "cwd": attempt.relative_to(root).as_posix(),
                      "log": (attempt / log).relative_to(root).as_posix()}
            with (attempt / "commands.log").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(argv) + "\n")
            begin = time.monotonic()
            try:
                result = run_tool(argv, cwd=attempt, timeout=TOOL_TIMEOUT)
                output, code = result.stdout, result.returncode
            except ToolError as error:
                output, code = error.output + "\n" + str(error) + "\n", None
            (attempt / log).write_text(output, encoding="utf-8")
            record.update(exit_code=code, elapsed_seconds=round(time.monotonic() - begin, 3))
            report["commands"].append(record)
            lines, names = named_errors(output)
            problem = diagnostic(output) if code == 0 else f"exit {code}"
            if problem:
                report["failure"] = {"label": label, "problem": problem, "errors": lines, "names": names,
                                     "log": record["log"]}
                summary = f"{label}: {problem}"
                if names:
                    summary += "; names " + ", ".join(names)
                if lines:
                    summary += "; first " + lines[0].strip()
                raise RuntimeError(summary)
            return output

        with progress.stage("Create the isolated work library"):
            execute("vmap -c", [tools["vmap"], "-c"], "ini.log")
            execute("vlib", [tools["vlib"], "work"], "library.log")
            execute("vmap", [tools["vmap"], "work", library], "map.log")
        with progress.stage(f"vlog {len(selected['sources'])} sources"):
            execute("vlog", [tools["vlog"], "-sv", "-work", "work", "+incdir+" + str(root.resolve()),
                             *[str((root / source).resolve()) for source in selected["sources"]]],
                    "compile.log")
        for top in sorted(selected["tops"]):
            with progress.stage(f"vopt {top}"):
                execute(f"vopt {top}", [tools["vopt"], "-work", "work", top, "-o", top + "_opt"],
                        f"elaborate-{top}.log")
        report["status"] = "PASS"
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    if report["inject_fault"]:
        # The injected fault must be the reason for the FAIL. A clean run, or a
        # failure elsewhere, means the fixture did not prove detection.
        names = report.get("failure", {}).get("names", [])
        report["fault_detected"] = Path(FAULT).name in names
        if report["status"] == "PASS":
            report.update(status="FAIL", error=f"fault injection not detected: {FAULT} compiled and elaborated clean")
    report["elapsed_seconds"] = round(time.monotonic() - started, 3)
    report["artifacts"] = {p.relative_to(root).as_posix(): file_hash(p)
                           for p in attempt.rglob("*") if p.is_file() and "work" not in p.relative_to(attempt).parts}
    atomic_json(attempt / "result.json", report)
    return report
