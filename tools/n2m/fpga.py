"""Explicit MAX 10 builds with retained fit/timing evidence and checked reuse."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import subprocess
import uuid

from .hdl import dependencies
from .records import atomic_json, cache_matches, digest, file_hash, read_json
from . import fpga_pll, fpga_constraints, fpga_vga, fpga_intel_memory, fpga_memory_stores, fpga_adc, fpga_controls, fpga_v05

DEVICE = "10M50DAF484C7G"
REGISTRY = "src/fpga/de10_lite/targets.json"
TOOLS = ("quartus_sh", "quartus_map", "quartus_fit", "quartus_asm", "quartus_sta", "quartus_eda")
REQUIRED_REPORTS = ("design.map.rpt", "design.fit.rpt", "design.fit.summary", "design.asm.rpt", "design.sta.rpt", "design.sta.summary",
                    "design.sof", "unconstrained.rpt", "check_timing.rpt", "ignored.rpt")
SDC_COMMANDS = set("create_clock create_generated_clock derive_clock_uncertainty derive_pll_clocks set_input_delay set_output_delay set_false_path set_multicycle_path set_max_delay set_min_delay set_clock_uncertainty set_clock_groups set_clock_latency set_clock_transition".split())
TIMING_CHECKS = set("no_clock multiple_clock pos_neg_clock_domain generated_clock virtual_clock no_input_delay no_output_delay partial_input_delay partial_output_delay io_min_max_delay_consistency reference_pin generated_io_delay latency_override partial_multicycle multicycle_consistency loops latches pll_cross_check uncertainty partial_min_max_delay clock_assignments_on_output_ports input_delay_assigned_to_clock".split())
ALLOCATOR_NOTICE = "TBBmalloc: skip allocation functions replacement in ucrtbase.dll: unknown prologue for function _msize"
# Quartus 25.1 on Windows can exit 3 before doing any work when its bundled TBB
# allocator fails to replace the ucrtbase.dll hooks behind that notice. Intel
# documents this variable to keep the standard CRT allocator. It is set only in
# the environment of each launched Quartus process; the host is not changed.
ALLOCATOR_OVERRIDE = {"TBB_MALLOC_DISABLE_REPLACEMENT": "1"}
ALLOCATOR_OVERRIDE_NOTICE = ("notice: TBB_MALLOC_DISABLE_REPLACEMENT=1 is set for every launched Quartus process "
                             "(host allocator condition; see wiki/tools/n2m/SPEC.md#quartus-allocator-override)")
# These exact diagnostics do not establish physical readiness. No warning is hidden.
CLASSIFIED = {
    "10905": r"Generated the EDA functional simulation netlist because it is the only supported netlist type for this device\.",
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


def quartus_environment(base=None):
    """Process-only environment for a Quartus launch: the caller's plus the allocator override."""
    environment = dict(os.environ if base is None else base)
    environment.update(ALLOCATOR_OVERRIDE)
    return environment


def tcl_word(value):
    return '"' + str(value).replace('\\', '/').replace('"', '\\"').replace('$', '\\$').replace('[', '\\[').replace(']', '\\]') + '"'


def self_contained_sdc(text):
    # A bounded command subset avoids hidden dependency reads through Tcl bodies,
    # variables, aliases or dynamically constructed command names.
    for line in re.sub(r'\\\r?\n', ' ', text).splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.split()[0] not in SDC_COMMANDS or any(c in line for c in '$;\\'):
            raise ValueError("unsupported external/dynamic SDC syntax")
        scalar = re.sub(r'\[(?:get_ports|get_clocks|get_pins|get_cells|get_registers|get_nets|all_inputs|all_outputs|all_registers)\b[^\[\]$;\\]*\]', '', line)
        if '[' in scalar or ']' in scalar:
            raise ValueError("unsupported dynamic or nested SDC expression")


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
    if not isinstance(target, dict) or not fields.issubset(target) or set(target) - fields - {"pll", "timing"} or target["device"] != DEVICE:
        raise ValueError("unknown FPGA target, fields, or device")
    if name == "v05-board":
        fpga_v05.validate_board(target)
    if "pll" in target:
        fpga_pll.validate(target["pll"])
        if target["top"] not in ("clocking_proof", "vga_proof", "ppu_proof", "intel_memory_proof", "controls_proof", "v05_proof", "v05_controls_proof") or "timing" not in target:
            raise ValueError("PLL evidence currently requires the bounded clocking proof target")
    if "timing" in target:
        fpga_constraints.validate(target["timing"])
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
            text = path.read_text(encoding="utf-8")
            if suffix == ".sdc":
                self_contained_sdc(text)
    if not isinstance(target["pins"], dict) or not target["pins"] or not isinstance(target["virtual_pins"], list):
        raise ValueError("invalid FPGA pin assignments")
    for port in [*target["pins"], *target["virtual_pins"]]:
        if not isinstance(port, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*(?:\[(?:\d+|\*)\])?", port):
            raise ValueError("invalid FPGA port")
    if any(not isinstance(pin, str) or not re.fullmatch(r"PIN_[A-Z]+[0-9]+", pin) for pin in target["pins"].values()):
        raise ValueError("invalid FPGA pin")
    if len(set(target["pins"].values())) != len(target["pins"]):
        raise ValueError("duplicate FPGA pin")
    dependencies(root, target["sources"], synthesis=True)
    return target


def prepare(root, folder, target, build_id=None):
    # Configurations are data; quote every value rather than evaluating user Tcl.
    lines = ['set_global_assignment -name FAMILY "MAX 10"',
             f'set_global_assignment -name DEVICE {DEVICE}',
             f'set_global_assignment -name TOP_LEVEL_ENTITY {tcl_word(target["top"])}',
             'set_global_assignment -name NUM_PARALLEL_PROCESSORS 2',
             'set_global_assignment -name VERILOG_MACRO "SYNTHESIS=1"',
             f'set_global_assignment -name SEARCH_PATH {tcl_word(root.resolve())}',
             'set_global_assignment -name PROJECT_OUTPUT_DIRECTORY output']
    if target["top"] == "controls_proof":
        if not isinstance(build_id, str) or not re.fullmatch(r"[0-9a-f]{32}", build_id) or int(build_id, 16) == 0:
            raise ValueError("physical controls build requires a nonzero fingerprint identity")
        lines.append("set_global_assignment -name VERILOG_MACRO " + tcl_word("N2M_CONTROLS_BUILD_ID=128'h" + build_id))
    if fpga_v05.board_target(target):
        fpga_v05.validate_board(target)
        if not isinstance(build_id, str) or not re.fullmatch(r"[0-9a-f]{32}", build_id) or int(build_id, 16) == 0:
            raise ValueError("physical v05 build requires a nonzero fingerprint identity")
        lines.append("set_global_assignment -name VERILOG_MACRO " + tcl_word("N2M_V05_BUILD_ID=128'h" + build_id))
        lines.append('set_global_assignment -name RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"')
    for field, assignment in (("sources", "SYSTEMVERILOG_FILE"), ("constraints", "SDC_FILE")):
        for name in target[field]:
            lines.append(f'set_global_assignment -name {assignment} {tcl_word((root / name).resolve())}')
    if "pll" in target:
        lines.append('set_global_assignment -name VERILOG_FILE n2m_pixel_pll.v')
        if target["pll"].get("system_divide") == 2:
            lines.append('set_global_assignment -name VERILOG_FILE n2m_system_pll.v')
    if "src/rtl/input/n2m_adc_backend.sv" in target["sources"]:
        lines.extend(fpga_adc.assignments())
    if "timing" in target or target["top"] in ("v05_proof", "v05_controls_proof"):
        (folder / "checked.sdc").write_text(checked_constraints(target), encoding="utf-8")
        lines.append('set_global_assignment -name SDC_FILE checked.sdc')
    for port, pin in target["pins"].items():
        lines.extend([f'set_location_assignment {pin} -to {tcl_word(port)}',
                      f'set_instance_assignment -name IO_STANDARD "3.3-V LVTTL" -to {tcl_word(port)}'])
        if target.get("top") in ("vga_proof", "ppu_proof", "controls_proof", "v05_proof", "v05_controls_proof") and port in fpga_vga.PORTS:
            lines.append(f'set_instance_assignment -name CURRENT_STRENGTH_NEW "8MA" -to {tcl_word(port)}')
        if (target["top"] == "controls_proof" or fpga_v05.board_target(target)) and (port == "uart_tx" or re.fullmatch(r"leds\[[0-9]\]", port)):
            lines.append(f'set_instance_assignment -name CURRENT_STRENGTH_NEW "8MA" -to {tcl_word(port)}')
    if target["top"] == "controls_proof" or fpga_v05.board_target(target):
        lines.append('set_instance_assignment -name IO_STANDARD "3.3 V SCHMITT TRIGGER" -to board_reset_n')
    for port in target["virtual_pins"]:
        lines.append(f'set_instance_assignment -name VIRTUAL_PIN ON -to {tcl_word(port)}')
    (folder / "design.qsf").write_text('\n'.join(lines) + '\n', encoding="utf-8")
    (folder / "design.qpf").write_text('PROJECT_REVISION = "design"\n', encoding="utf-8")
    audit = AUDIT
    if "pll" in target:
        audit = audit.replace("project_close", "report_metastability -file output/metastability.rpt\nreport_clock_transfers -file output/clock_transfers.rpt\n" + fpga_pll.chain_audit(tcl_word) + "project_close")
    if target.get("top") in ("vga_proof", "ppu_proof", "controls_proof"):
        audit = audit.replace("project_close", fpga_vga.audit(tcl_word, lcd=target["top"] == "ppu_proof") + "project_close")
    if target.get("top") == "intel_memory_proof":
        audit = audit.replace("project_close", fpga_intel_memory.audit(tcl_word) + "project_close")
    if target["top"] == "controls_proof":
        audit = audit.replace("project_close", fpga_controls.audit(tcl_word) + "project_close")
    if target.get("top") in ("v05_proof", "v05_controls_proof"):
        audit = audit.replace("project_close", fpga_v05.audit(tcl_word, board=fpga_v05.board_target(target), controls=fpga_v05.control_target(target)) + "project_close")
    (folder / "audit.tcl").write_text(audit, encoding="utf-8")


def checked_constraints(target):
    if target.get("top") in ("v05_proof", "v05_controls_proof"):
        return fpga_constraints.generate(target["timing"], tcl_word) + fpga_v05.constraints(tcl_word, board=fpga_v05.board_target(target), controls=fpga_v05.control_target(target))
    text = fpga_constraints.generate(target["timing"], tcl_word)
    if target.get("top") in ("vga_proof", "ppu_proof", "controls_proof"):
        text += fpga_vga.constraints(tcl_word, lcd=target["top"] == "ppu_proof")
    if target["top"] == "controls_proof":
        text += fpga_controls.constraints(tcl_word)
    return text


def diagnostics(output, explained=()):
    classified = []
    for line in output.splitlines():
        line = line.strip()
        if line == ALLOCATOR_NOTICE:
            classified.append({"code": "TBBmalloc", "text": line})
        elif re.match(r"(?:Critical Warning|Warning|Error)(?:\s|:|\()", line, re.I):
            match = re.fullmatch(r"Warning \((\d+)\): (.*)", line)
            known = next((item for item in explained if item["text"] == line), None)
            if known is not None:
                classified.append(known)
            elif match and match[1] in CLASSIFIED and re.fullmatch(CLASSIFIED[match[1]], match[2]):
                classified.append({"code": match[1], "text": line})
            else:
                raise ValueError(f"unexplained Quartus diagnostic: {line}")
    return classified


def execute(argv, folder, log, timeout, record, build):
    command = {"argv": [str(a) for a in argv], "cwd": str(folder), "environment": dict(ALLOCATOR_OVERRIDE)}
    options = {"env": quartus_environment()}
    if os.name != "nt":
        options["start_new_session"] = True
    record["commands"].append(command)
    with (build / "commands.log").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(command) + '\n')
    # Windows timeout cleanup uses taskkill /T, not console control events.
    timed_out = False
    # Give native tools a regular output handle and retain bytes while they run.
    # The matched PLL probe found intermittent crashes with pipe-backed output;
    # this avoids that observed launch condition without claiming its root cause.
    with log.open("wb") as stream:
        process = subprocess.Popen(argv, cwd=folder, stdout=stream, stderr=subprocess.STDOUT, **options)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                if os.name == "nt":
                    cleanup = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=5)
                    command['cleanup_exit_code'] = cleanup.returncode
                    if cleanup.returncode:
                        raise RuntimeError('Quartus process-tree cleanup failed')
                else:
                    import signal
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
                command['cleanup_complete'] = True
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                command['cleanup_complete'] = False
                command['cleanup_error'] = str(error)
                process.kill()
                process.wait(timeout=2)
                raise RuntimeError('Quartus timeout cleanup incomplete') from error
        finally:
            command.update(exit_code=process.returncode, timed_out=timed_out)
    text = log.read_bytes().decode("utf-8", errors="replace")
    if timed_out:
        raise RuntimeError(f"Quartus timeout after {timeout}s; see {log.name}")
    if process.returncode:
        raise RuntimeError(f"Quartus exit {process.returncode}; see {log.name}")
    explained = ()
    if log.name == "compile.log" and record.get("definition", {}).get("top") in ("adc_proof", "controls_proof", "v05_controls_proof"):
        explained = fpga_adc.explained_diagnostics(text, folder, record["tools"]["adc"], record["definition"]["top"])
    if log.name == "compile.log" and "pll" in record.get("definition", {}):
        explained = [*explained, *fpga_pll.explained_diagnostics(text, folder, record["definition"]["pll"])]
    record["classified_diagnostics"].extend(diagnostics(text, explained))
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


def timing_evidence(folder, target, *, build_id=None):
    parallel = target.get("pll", {}).get("system_divide") == 2
    system_profile = {"system_clock": fpga_pll.SYSTEM_CLOCK, "system_net": fpga_pll.SYSTEM_NET} if parallel else {}
    if "timing" in target:
        if (folder / "checked.sdc").read_text(encoding="utf-8") != checked_constraints(target):
            raise ValueError("checked timing assignments differ from target")
    if "pll" in target:
        fpga_pll.verify(folder, target["pll"])
    output = folder / "output"
    for name in REQUIRED_REPORTS:
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
        adc_prefix = "u_controls|" if fpga_v05.control_target(target) else ""
        if target["top"] in ("controls_proof", "v05_controls_proof") and f"{corner} Model Minimum Pulse Width '{adc_prefix}u_adc|u_pll|altpll_component|auto_generated|pll1|clk[0]'" not in slacks:
            raise ValueError("missing ADC PLL pulse-width timing")
        for check in (("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width") if "pll" in target else ("Setup", "Hold", "Minimum Pulse Width")):
            if not any(name.startswith(f"{corner} Model {check} '") for name in slacks):
                raise ValueError(f"missing timing corner/check: {corner} {check}")
            if "pll" in target:
                for clock in (("clk_reference", fpga_pll.SYSTEM_CLOCK, fpga_pll.PIXEL_PLL + "|clk[0]") if parallel else ("clk_sys", fpga_pll.PIXEL_PLL + "|clk[0]")):
                    if f"{corner} Model {check} '{clock}'" not in slacks:
                        raise ValueError(f"missing clock timing: {clock} {corner} {check}")
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
    lock_event = None
    expected_lock_events = (2 if target["top"] in ("controls_proof", "v05_controls_proof") else 1) + int(parallel)
    if "pll" in target:
        if dict(rows).get("no_clock") != str(expected_lock_events):
            raise ValueError("vendor lock event row missing or extra no-clock endpoints")
        lock_event = fpga_pll.verify_lock_event(folder, checks, target["top"], parallel=parallel)
        fpga_pll.verify_fit(folder, target)
    adc_evidence = None
    if target["top"] in ("adc_proof", "controls_proof", "v05_controls_proof"):
        adc_evidence = fpga_adc.verify(folder, target["top"], **({"parallel": True, "system_net": fpga_pll.SYSTEM_NET} if parallel else {}))
        if target["top"] == "adc_proof":
            lock_event = adc_evidence["lock_event"]
    vga_evidence = fpga_vga.verify(folder, lcd=target["top"] == "ppu_proof", controls=target["top"] == "controls_proof", **system_profile) if target.get("top") in ("vga_proof", "ppu_proof", "controls_proof") else None
    memory_evidence = fpga_intel_memory.verify(folder) if target.get("top") == "intel_memory_proof" else None
    if target.get("top") == "n2m_memory_stores":
        memory_evidence = fpga_memory_stores.verify(folder)
    for name, count in rows:
        if name == "no_clock" and int(count) == expected_lock_events and ("pll" in target or adc_evidence is not None):
            continue
        if int(count) and not (name == "virtual_clock" and int(count) == 1 and "No virtual clock was found." in checks):
            raise ValueError(f"structural timing failure: {name}={count}")
    evidence = {"slack_ns": slacks, "fit_summary": fit, "unconstrained": "none", "ignored_constraints": "none", "vendor_lock_event": lock_event, "vga": vga_evidence, "intel_memory": memory_evidence,
            "virtual_clock_check": "No virtual clock required for the physical-clock-referenced fixture" if "No virtual clock was found." in checks else "passed"}
    if target["top"] in ("v05_proof", "v05_controls_proof"):
        evidence["vga_paths"] = fpga_v05.verify_paths(folder, system_clock=fpga_pll.SYSTEM_CLOCK, controls=fpga_v05.control_target(target))
    if adc_evidence is not None:
        evidence["adc"] = adc_evidence
    if target.get("top") == "controls_proof":
        evidence["controls"] = fpga_controls.verify(folder, **system_profile)
        evidence["controls"]["build_id"] = fpga_controls.verify_identity(folder, build_id)
    if fpga_v05.board_target(target):
        evidence["intel_memory"] = fpga_v05.verify_memory(folder, system_net=fpga_pll.SYSTEM_NET, top=target["top"])
        evidence["board_uart"] = fpga_controls.verify(folder, system_clock=fpga_pll.SYSTEM_CLOCK,
            system_net=fpga_pll.SYSTEM_NET, chains=fpga_v05.chains(target), top=target["top"])
        evidence["board_build_id"] = fpga_controls.verify_identity(folder, build_id, macro="N2M_V05_BUILD_ID", instances=3 if fpga_v05.control_target(target) else 2)
    return evidence


def complete_cache(record, fingerprint, root, build, target):
    if not cache_matches(record, fingerprint, root, build):
        return False
    try:
        immutable = (root / record["attempt_result"]).resolve()
        folder = (root / record["evidence_directory"]).resolve()
        if not immutable.is_relative_to(build.resolve()) or not folder.is_relative_to(build.resolve()):
            return False
        if read_json(immutable) != record:
            return False
        required = [folder / "output" / name for name in REQUIRED_REPORTS]
        if "pll" in target:
            required += [folder / "n2m_pixel_pll.v", folder / "generate-pll.log"]
            if target["pll"].get("system_divide") == 2:
                required += [folder / "n2m_system_pll.v", folder / "generate-system-pll.log"]
            required += [folder / "output" / name for name in fpga_pll.required_reports()]
        if "src/rtl/input/n2m_adc_backend.sv" in target.get("sources", []):
            required += [folder / name for name in (*fpga_adc.CONTROL, "n2m_adc_pll.v", "generate-adc-pll.log")]
        if "pll" in target or any(p in target["sources"] for p in ("src/rtl/common/n2m_intel_ram.sv", "src/rtl/input/n2m_adc_backend.sv")):
            required += [folder / "simulation/questa/design.vo", folder / "netlist.log"]
        required += [folder / name for name in ("design.qpf", "design.qsf", "audit.tcl", "compile.log", "audit.log")]
        if "timing" in target or target.get("top") in ("v05_proof", "v05_controls_proof"):
            required.append(folder / "checked.sdc")
        if target.get("top") in ("vga_proof", "ppu_proof", "controls_proof"):
            required += [folder / "output" / name for name in fpga_vga.required_reports(lcd=target["top"] == "ppu_proof")]
        if target.get("top") == "controls_proof":
            required += [folder / "output" / name for name in fpga_controls.required_reports()]
        if target.get("top") == "intel_memory_proof":
            required.append(folder / "output/intel_memory_inputs.rpt")
        if target.get("top") in ("v05_proof", "v05_controls_proof"):
            required += [folder / "output" / name for name in fpga_vga.required_reports(lcd=True)]
        if fpga_v05.board_target(target):
            required += [folder / "output" / name for name in fpga_controls.required_reports(chains=fpga_v05.chains(target))]
        if any(p.relative_to(root).as_posix() not in record["artifacts"] for p in required):
            return False
        if (target.get("top") == "controls_proof" or fpga_v05.board_target(target)) and record.get("build_id") != fingerprint[:32]:
            return False
        return timing_evidence(folder, target, build_id=record.get("build_id")) == record["evidence"]
    except (KeyError, TypeError, ValueError, OSError):
        return False


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
              "environment": dict(ALLOCATOR_OVERRIDE), "notices": [ALLOCATOR_OVERRIDE_NOTICE],
              "started": datetime.now(timezone.utc).isoformat()}
    # Even invalid definitions or missing tools invalidate an earlier successful request.
    atomic_json(current, record)
    try:
        if not 1 <= args.timeout <= 3600:
            raise ValueError("FPGA stage timeout must be between 1 and 3600 seconds")
        target = target_definition(root, args.target)
        inputs = [REGISTRY, "tools/build.py", *dependencies(root, target["sources"], synthesis=True), *target["constraints"]]
        inputs += [p.relative_to(root).as_posix() for p in (root / "tools/n2m").glob("*.py")]
        record["inputs"] = {p: file_hash(root / p) for p in inputs}
        record["tools"] = tools(args.quartus_bin, folder, record, build, min(args.timeout, 60))
        if "pll" in target:
            record["tools"]["altpll"] = fpga_pll.identity(args.quartus_bin)
        if "src/rtl/common/n2m_intel_ram.sv" in target["sources"]:
            record["tools"]["altsyncram"] = fpga_intel_memory.identity(args.quartus_bin)
        if "src/rtl/input/n2m_adc_backend.sv" in target["sources"]:
            record["tools"]["adc"] = fpga_adc.identity(args.quartus_bin)
        record["definition"] = target
        record["fingerprint"] = digest({"inputs": record["inputs"], "tools": record["tools"], "definition": target, "timeout": args.timeout})
        if target["top"] == "controls_proof" or fpga_v05.board_target(target):
            record["build_id"] = record["fingerprint"][:32]
        if not args.rebuild and complete_cache(old, record["fingerprint"], root, build, target):
            record.update(status="PASS", cache="CACHED", reused_result=old["attempt_result"], evidence=old["evidence"], evidence_directory=old["evidence_directory"])
            record["artifacts"].update(old["artifacts"])
        else:
            if "adc" in record["tools"]:
                fpga_adc.generate(folder, record["tools"]["adc"], execute, args.timeout, record, build)
            if "pll" in target:
                fpga_pll.generate(folder, record["tools"]["altpll"], target["pll"], execute, args.timeout, record, build)
            prepare(root, folder, target, build_id=record.get("build_id"))
            execute([record["tools"]["quartus_sh"]["path"], "--flow", "compile", "design"], folder, folder / "compile.log", args.timeout, record, build)
            execute([record["tools"]["quartus_sta"]["path"], "-t", "audit.tcl"], folder, folder / "audit.log", args.timeout, record, build)
            if "pll" in target or "adc" in record["tools"] or "src/rtl/common/n2m_intel_ram.sv" in target["sources"]:
                execute([record["tools"]["quartus_eda"]["path"], "--simulation", "--tool=modelsim", "--format=verilog", "design"], folder, folder / "netlist.log", args.timeout, record, build)
            record["evidence"] = timing_evidence(folder, target, build_id=record.get("build_id"))
            record["evidence_directory"] = folder.relative_to(root).as_posix()
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
