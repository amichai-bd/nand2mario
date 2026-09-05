"""Explicit MAX 10 builds with retained fit/timing evidence and checked reuse."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import uuid

from .records import atomic_json, cache_matches, digest, file_hash, read_json

DEVICE = "10M50DAF484C7G"
REGISTRY = "src/fpga/de10_lite/targets.json"
TOOLS = ("quartus_sh", "quartus_map", "quartus_fit", "quartus_asm", "quartus_sta")
TIMING_CHECKS = set("no_clock multiple_clock pos_neg_clock_domain generated_clock virtual_clock no_input_delay no_output_delay partial_input_delay partial_output_delay io_min_max_delay_consistency reference_pin generated_io_delay latency_override partial_multicycle multicycle_consistency loops latches pll_cross_check uncertainty partial_min_max_delay clock_assignments_on_output_ports input_delay_assigned_to_clock".split())
ALLOCATOR_NOTICE = "TBBmalloc: skip allocation functions replacement in ucrtbase.dll: unknown prologue for function _msize"
# These exact diagnostics do not establish physical readiness. No warning is hidden.
CLASSIFIED = {
    "292013": r"Feature LogicLock is only available with a valid subscription license\. You can purchase a software subscription to gain full access to this feature\.",
    "169177": r"\d+ pins must meet Intel FPGA requirements for 3\.3-, 3\.0-, and 2\.5-V interfaces\. For more information, refer to AN 447: Interfacing MAX 10 Devices with 3\.3/3\.0/2\.5-V LVTTL/LVCMOS I/O Systems\.",
}
AUDIT = """project_open design
create_timing_netlist
read_sdc
update_timing_netlist
report_ucp -file output/unconstrained.rpt
check_timing -file output/check_timing.rpt
report_sdc -ignored -file output/ignored.rpt
project_close
"""


def tcl_word(value):
    return '"' + str(value).replace('\\', '/').replace('"', '\\"').replace('$', '\\$').replace('[', '\\[').replace(']', '\\]') + '"'


def target_definition(root, name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("invalid FPGA target name")
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    if (not isinstance(registry, dict) or set(registry) != {"schema_version", "targets"}
            or type(registry["schema_version"]) is not int or registry["schema_version"] != 1
            or not isinstance(registry["targets"], dict)):
        raise ValueError("unsupported FPGA registry schema")
    target = registry["targets"].get(name)
    fields = {"device", "top", "sources", "constraints", "pins", "virtual_pins"}
    if not isinstance(target, dict) or set(target) != fields or target["device"] != DEVICE:
        raise ValueError("unknown FPGA target, fields, or device")
    if not isinstance(target["top"], str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target["top"]):
        raise ValueError("invalid FPGA top")
    for field, suffix in (("sources", ".sv"), ("constraints", ".sdc")):
        paths = target[field]
        if not isinstance(paths, list) or not paths or any(not isinstance(p, str) for p in paths) or len(set(paths)) != len(paths):
            raise ValueError(f"invalid FPGA {field}")
        for name in paths:
            path = root / name
            if (not name.startswith("src/") or ".." in Path(name).parts or '\\' in name or any(ord(c) < 32 for c in name)
                    or path.suffix != suffix or not path.is_file() or path.is_symlink()
                    or not path.resolve().is_relative_to(root.resolve())):
                raise ValueError(f"missing or unsafe FPGA input: {name}")
            # This first target format deliberately supports self-contained inputs.
            # Add an explicit dependency model before accepting includes/IP/data files.
            text = path.read_text(encoding="utf-8")
            if suffix == ".sv" and re.search(r'`include\b|\$(?:readmemh|readmemb|fopen)\b', text):
                raise ValueError(f"external FPGA source dependencies are unsupported: {name}")
            if suffix == ".sdc" and re.search(r'(?:^|[;\[])\s*(?:source|read_sdc|open|exec|load|eval)\b', text, re.M):
                raise ValueError(f"external or dynamic SDC dependencies are unsupported: {name}")
    if not isinstance(target["pins"], dict) or not target["pins"] or not isinstance(target["virtual_pins"], list):
        raise ValueError("invalid FPGA pin assignments")
    for port in [*target["pins"], *target["virtual_pins"]]:
        if not isinstance(port, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\[(?:\d+|\*)\])?", port):
            raise ValueError("invalid FPGA port")
    if any(not isinstance(pin, str) or not re.fullmatch(r"PIN_[A-Z]+[0-9]+", pin) for pin in target["pins"].values()):
        raise ValueError("invalid FPGA pin")
    if len(set(target["pins"].values())) != len(target["pins"]):
        raise ValueError("duplicate FPGA pin")
    return target


def prepare(root, folder, target):
    # Configurations are data; quote every value rather than evaluating user Tcl.
    lines = ['set_global_assignment -name FAMILY "MAX 10"',
             f'set_global_assignment -name DEVICE {DEVICE}',
             f'set_global_assignment -name TOP_LEVEL_ENTITY {tcl_word(target["top"])}',
             'set_global_assignment -name NUM_PARALLEL_PROCESSORS 2',
             'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output']
    for field, assignment in (("sources", "SYSTEMVERILOG_FILE"), ("constraints", "SDC_FILE")):
        for name in target[field]:
            lines.append(f'set_global_assignment -name {assignment} {tcl_word((root / name).resolve())}')
    for port, pin in target["pins"].items():
        lines.extend([f'set_location_assignment {pin} -to {tcl_word(port)}',
                      f'set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to {tcl_word(port)}'])
    for port in target["virtual_pins"]:
        lines.append(f'set_instance_assignment -name VIRTUAL_PIN ON -to {tcl_word(port)}')
    (folder / "design.qsf").write_text('\n'.join(lines) + '\n', encoding="utf-8")
    (folder / "design.qpf").write_text('PROJECT_REVISION = "design"\n', encoding="utf-8")
    (folder / "audit.tcl").write_text(AUDIT, encoding="utf-8")


def diagnostics(output):
    classified = []
    for line in output.splitlines():
        line = line.strip()
        if line == ALLOCATOR_NOTICE:
            classified.append({"code": "TBBmalloc", "text": line})
        elif re.match(r"(?:Critical Warning|Warning|Error)(?:\s|:|\()", line, re.I):
            match = re.fullmatch(r"Warning \((\d+)\): (.*)", line)
            if match and match[1] in CLASSIFIED and re.fullmatch(CLASSIFIED[match[1]], match[2]):
                classified.append({"code": match[1], "text": line})
            else:
                raise ValueError(f"unexplained Quartus diagnostic: {line}")
    return classified


def execute(argv, folder, log, timeout, record, build):
    command = {"argv": [str(a) for a in argv], "cwd": str(folder)}
    record["commands"].append(command)
    with (build / "commands.log").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(command) + '\n')
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(argv, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **options)
    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        else:
            import signal
            os.killpg(process.pid, signal.SIGKILL)
        output, _ = process.communicate()
    text = output.decode("utf-8", errors="replace")
    log.write_text(text, encoding="utf-8")
    command.update(exit_code=process.returncode, timed_out=timed_out)
    if timed_out:
        raise RuntimeError(f"Quartus timeout after {timeout}s; see {log.name}")
    if process.returncode:
        raise RuntimeError(f"Quartus exit {process.returncode}; see {log.name}")
    record["classified_diagnostics"].extend(diagnostics(text))
    return text


def tools(directory, folder, record, build, timeout):
    directory = Path(directory).resolve()
    identities = {}
    for name in TOOLS:
        path = directory / (name + (".exe" if os.name == "nt" else ""))
        if not path.is_file():
            raise ValueError(f"missing explicit Quartus tool: {name}")
        output = execute([str(path), "--version"], folder, folder / f"{name}-version.log", timeout, record, build)
        version = re.search(r"(?m)^Version (.+)$", output)
        if not version or "Quartus" not in output:
            raise ValueError(f"unrecognized Quartus tool version: {name}")
        identities[name] = {"path": str(path), "sha256": file_hash(path), "version": version[1].strip()}
    if len({info["version"] for info in identities.values()}) != 1:
        raise ValueError("Quartus executable versions differ")
    return identities


def timing_evidence(folder, target):
    output = folder / "output"
    required = ["design.map.rpt", "design.fit.rpt", "design.fit.summary", "design.asm.rpt", "design.sta.rpt", "design.sta.summary",
                "design.sof", "unconstrained.rpt", "check_timing.rpt", "ignored.rpt"]
    for name in required:
        if not (output / name).is_file() or not (output / name).stat().st_size:
            raise ValueError(f"missing FPGA evidence: {name}")
    fit = (output / "design.fit.summary").read_text(encoding="utf-8")
    if not re.search(r"(?m)^Fitter Status : Successful", fit) or f"Device : {target['device']}" not in fit or "Timing Models : Final" not in fit:
        raise ValueError("fit status, target identity, or final timing model mismatch")
    summary = (output / "design.sta.summary").read_text(encoding="utf-8")
    entries = re.findall(r"Type\s*:\s*([^\r\n]+)\s+Slack\s*:\s*(\S+)\s+TNS\s*:\s*(\S+)", summary)
    if not entries or len(entries) != len(re.findall(r"(?m)^Type\s*:", summary)):
        raise ValueError("missing or malformed timing summary")
    slacks = {}
    for name, slack, tns in entries:
        slack, tns = float(slack), float(tns)
        if not math.isfinite(slack) or not math.isfinite(tns) or slack < 0 or tns != 0:
            raise ValueError(f"timing failure: {name}, slack={slack}, TNS={tns}")
        slacks[name] = slack
    for corner in ("Slow 1200mV 85C", "Slow 1200mV 0C", "Fast 1200mV 0C"):
        for check in ("Setup", "Hold", "Minimum Pulse Width"):
            if not any(name.startswith(f"{corner} Model {check} '") for name in slacks):
                raise ValueError(f"missing timing corner/check: {corner} {check}")
    ucp = (output / "unconstrained.rpt").read_text(encoding="utf-8")
    rows = re.findall(r";\s*(Illegal Clocks|Unconstrained [^;]+?)\s*;\s*(\d+)\s*;\s*(\d+)\s*;", ucp)
    expected = {"Illegal Clocks", "Unconstrained Clocks", "Unconstrained Input Ports", "Unconstrained Input Port Paths", "Unconstrained Output Ports", "Unconstrained Output Port Paths"}
    if {name for name, _, _ in rows} != expected or any(int(a) or int(b) for _, a, b in rows):
        raise ValueError("unconstrained paths or missing unconstrained-path summary")
    ignored = (output / "ignored.rpt").read_text(encoding="utf-8")
    if "No constraints were ignored." not in ignored:
        raise ValueError("ignored or missing SDC assignments evidence")
    checks = (output / "check_timing.rpt").read_text(encoding="utf-8")
    rows = re.findall(r";\s*([a-z_]+)\s*;\s*(\d+)\s*;", checks)
    if not TIMING_CHECKS.issubset(dict(rows)) or len(dict(rows)) != len(rows):
        raise ValueError("missing structural timing checks")
    for name, count in rows:
        if int(count) and not (name == "virtual_clock" and int(count) == 1 and "No virtual clock was found." in checks):
            raise ValueError(f"structural timing failure: {name}={count}")
    return {"slack_ns": slacks, "fit_summary": fit, "unconstrained": "none", "ignored_constraints": "none",
            "virtual_clock_check": "No virtual clock required for the physical-clock-referenced fixture" if "No virtual clock was found." in checks else "passed"}


def build_fpga(root, build, args, provenance=None):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.target):
        raise ValueError("invalid FPGA target name")
    stage = build / "fpga" / args.target
    if not stage.resolve().is_relative_to(build.resolve()):
        raise ValueError("FPGA stage escapes tagged build")
    current = stage / "result.json"
    old = read_json(current)
    folder = stage / "attempts" / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    record = {"status": "RUNNING", "cache": "BUILT", "target": args.target, "device": DEVICE,
              "commands": [], "artifacts": {}, "classified_diagnostics": [], "provenance": provenance or {},
              "started": datetime.now(timezone.utc).isoformat()}
    # Even invalid definitions or missing tools invalidate an earlier successful request.
    atomic_json(current, record)
    try:
        if not 1 <= args.timeout <= 3600:
            raise ValueError("FPGA stage timeout must be between 1 and 3600 seconds")
        target = target_definition(root, args.target)
        inputs = [REGISTRY, "tools/build.py", *target["sources"], *target["constraints"]]
        inputs += [p.relative_to(root).as_posix() for p in (root / "tools/n2m").glob("*.py")]
        record["inputs"] = {p: file_hash(root / p) for p in inputs}
        record["tools"] = tools(args.quartus_bin, folder, record, build, min(args.timeout, 60))
        record["definition"] = target
        record["fingerprint"] = digest({"inputs": record["inputs"], "tools": record["tools"], "definition": target, "timeout": args.timeout})
        if not args.rebuild and cache_matches(old, record["fingerprint"], root, build):
            record.update(status="PASS", cache="CACHED", reused_result=old["attempt_result"], evidence=old["evidence"])
            record["artifacts"].update(old["artifacts"])
        else:
            prepare(root, folder, target)
            execute([record["tools"]["quartus_sh"]["path"], "--flow", "compile", "design"], folder, folder / "compile.log", args.timeout, record, build)
            execute([record["tools"]["quartus_sta"]["path"], "-t", "audit.tcl"], folder, folder / "audit.log", args.timeout, record, build)
            record["evidence"] = timing_evidence(folder, target)
            record["status"] = "PASS"
    except Exception as error:
        record.update(status="FAIL", error=str(error))
        (folder / "failure.log").write_text(str(error) + '\n', encoding="utf-8")
    record["finished"] = datetime.now(timezone.utc).isoformat()
    # Preserve databases too: generated settings and every report/image remain under the attempt.
    record["artifacts"].update({p.relative_to(root).as_posix(): file_hash(p) for p in folder.rglob("*") if p.is_file()})
    record["attempt_result"] = (folder / "result.json").relative_to(root).as_posix()
    atomic_json(folder / "result.json", record)
    atomic_json(current, record)
    return record
