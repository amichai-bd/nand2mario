"""Read-only readiness evidence. Device enumeration never opens a serial port."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
import uuid

from .records import file_hash
from .simulation import simulate
from .simulator import Simulator
from .questa import write_macro, diagnostic


def execute(argv, cwd, log, timeout=60):
    with (cwd / "commands.log").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(argv) + "\n")
    try:
        result = subprocess.run(argv, cwd=cwd, text=True, encoding="utf-8",
                                errors="replace", stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        output = result.stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        output = getattr(error, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        (cwd / log).write_text(output + "\n" + str(error), encoding="utf-8")
        raise RuntimeError(f"command unavailable or timed out; see {log}") from error
    (cwd / log).write_text(output, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(f"exit {result.returncode}; see {log}")
    return output


def executable(directory, name):
    candidate = str(Path(directory) / (name + (".exe" if os.name == "nt" else ""))) if directory else name
    found = shutil.which(candidate)
    if not found:
        raise RuntimeError(f"missing {name}; select its tool directory explicitly")
    return str(Path(found).resolve())


def warning(output):
    # Questa's zero-warning summary is not a diagnostic.
    return bool(re.search(r"(?im)^.*\bwarning(?:s)?\b(?!\s*:\s*0\b).*$", output))


def questa(root, folder, directory):
    names = {name: executable(directory, name) for name in ("vlib", "vlog", "vsim")}
    version = execute([names["vsim"], "-version"], folder, "version.log")
    execute([names["vlib"], "work"], folder, "library.log")
    compiled = execute([names["vlog"], "-sv", "-work", "work",
                        str(root / "src/dv/builder/builder_smoke.sv")], folder, "compile.log")
    if warning(compiled):
        raise RuntimeError("simulator warning; see compile.log")
    (folder / "waves").mkdir(exist_ok=True)
    write_macro(folder)
    output = execute([names["vsim"], "-c", "-onfinish", "stop", "-wlf", "waves/smoke.wlf",
                      "work.builder_smoke", "+seed=1", "-do", "do run.do"],
                     folder, "sim.log")
    if diagnostic(output) or "PASS builder-smoke seed=1 checks=22" not in output:
        raise RuntimeError("simulation diagnostic or missing checked result; see sim.log")
    return {"version": version.strip(), "tools": names,
            "license": "runtime checkout succeeded for this smoke invocation"}


def quartus(folder, directory):
    tool = executable(directory, "quartus_sh")
    output = execute([tool, "--version"], folder, "version.log")
    if "Quartus" not in output or "Version " not in output:
        raise RuntimeError("unrecognized Quartus version output")
    if warning(output) or any(line.strip() and not line.startswith(("Quartus", "Version ", "Copyright"))
                              for line in output.splitlines()):
        raise RuntimeError("unexplained Quartus diagnostic; see version.log")
    lite = "Lite Edition" in output
    return {"path": tool, "version": output.strip(),
            "license": "Lite requires no license file" if lite else "not verified; synthesis was not run",
            "synthesis": "not tested", "status": "PASS" if lite else "WARNING"}


def parse_jtag(output, cable=None):
    chains = []
    for line in output.splitlines():
        header = re.match(r"^\s*(\d+)\)\s+(.+)$", line)
        if header:
            chains.append({"index": header[1], "name": header[2], "devices": []})
        else:
            device = re.match(r"^\s+([0-9a-fA-F]{8})\s+(.+)$", line)
            if device and chains:
                chains[-1]["devices"].append({"idcode": device[1].upper(), "name": device[2]})
    matches = [chain for chain in chains if "USB-Blaster" in chain["name"]
               and (cable is None or cable == chain["index"])
               and any(re.search(r"\b10M50DA\b", d["name"]) for d in chain["devices"])]
    if len(matches) != 1:
        raise RuntimeError("expected one selected USB-Blaster chain reporting 10M50DA")
    return {"selected": matches[0], "chains": chains,
            "scope": "reported JTAG identity only; no wiring, voltage, or programming proof"}


def select_uart(ports, args):
    matches = []
    for port in ports:
        identity = port.get("PNPDeviceID") or ""
        vid = re.search(r"VID_([0-9A-F]{4})", identity, re.I)
        pid = re.search(r"PID_([0-9A-F]{4})", identity, re.I)
        if (args.uart_port and port.get("DeviceID", "").casefold() != args.uart_port.casefold()
                or args.uart_vid and (not vid or vid[1].casefold() != args.uart_vid.casefold())
                or args.uart_pid and (not pid or pid[1].casefold() != args.uart_pid.casefold())
                or args.uart_identity and identity.casefold() != args.uart_identity.casefold()):
            continue
        matches.append(port)
    if not any((args.uart_port, args.uart_vid, args.uart_pid, args.uart_identity)):
        return {"status": "WARNING", "ports": ports, "detail": "enumerated only; select expected UART identity"}
    if len(matches) != 1:
        raise RuntimeError("UART selection must match exactly one enumerated port")
    if matches[0].get("Status") != "OK" or matches[0].get("ConfigManagerErrorCode") != 0:
        raise RuntimeError("selected UART is not healthy in Windows PnP; see ports.log")
    return {"selected": matches[0], "ports": ports,
            "scope": "OS identity only; port not opened, no DTR/RTS or bytes sent"}


def uart(folder, args):
    if os.name != "nt":
        return {"status": "WARNING", "detail": "UART enumeration supported on Windows only"}
    script = ("$ErrorActionPreference = 'Stop'; "
              "@(Get-CimInstance Win32_PnPEntity -Filter \"PNPClass='Ports'\" | "
              "Select-Object Name,PNPDeviceID,Status,ConfigManagerErrorCode) | ConvertTo-Json -Compress")
    output = execute(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], folder, "ports.log")
    devices = json.loads(output) if output.strip() else []
    devices = [devices] if isinstance(devices, dict) else devices
    ports = []
    for device in devices:
        # PnP Ports includes LPT devices. Require the serial friendly-name suffix;
        # never infer a COM port or hardware serial from a PNP identity tail.
        port = re.search(r"\(COM([1-9][0-9]*)\)$", device.get("Name") or "", re.I)
        if port and device.get("PNPDeviceID"):
            ports.append({**device, "DeviceID": "COM" + port[1]})
    return select_uart(ports, args)


def doctor(root, build, args, provenance):
    checks = {}
    attempt = uuid.uuid4().hex

    def check(name, action):
        folder = build / "doctor" / attempt / name
        folder.mkdir(parents=True, exist_ok=True)
        try:
            checks[name] = {"status": "PASS", **action(folder)}
        except Exception as error:
            checks[name] = {"status": "FAIL", "error": str(error)}
        checks[name]["artifacts"] = {p.relative_to(root).as_posix(): file_hash(p)
                                     for p in folder.rglob("*") if p.is_file()}

    def portable(folder):
        simulator = Simulator(args.sim, args.iverilog, args.vvp, args.wsl_distro)
        result = simulate(root, build, SimpleNamespace(target="builder-smoke", seed=1, rebuild=True), simulator, provenance)
        return {"status": result["status"], "tools": simulator.info,
                "result": str(build / "sim/test/builder-smoke/result.json")}

    check("portable", portable)
    untested = ["Questa", "Quartus", "JTAG", "UART"]
    if args.profile == "environment":
        check("questa", lambda folder: questa(root, folder, args.questa_bin))
        check("quartus", lambda folder: quartus(folder, args.quartus_bin))
        check("jtag", lambda folder: parse_jtag(execute(
            [executable(args.quartus_bin, "jtagconfig")], folder, "chain.log"), args.jtag_cable))
        check("uart", lambda folder: uart(folder, args))
        untested = ["Quartus synthesis", "physical wiring/voltage", "UART communication", "FPGA programming"]
    status = "FAIL" if any(c["status"] == "FAIL" for c in checks.values()) else "PASS"
    if status == "PASS" and any(c["status"] == "WARNING" for c in checks.values()):
        status = "WARNING"
    return {"status": status, "checks": checks,
            "profile": args.profile,
            "inputs": {p.relative_to(root).as_posix(): file_hash(p) for p in
                       [root / "src/dv/builder/builder_smoke.sv", *(root / "tools/n2m").glob("*.py")]},
            "tools": checks["portable"].get("tools", {}), "untested": untested,
            "readiness": "complete" if all(c["status"] == "PASS" for c in checks.values()) else "partial",
            "scope": f"{args.profile} checks only; warnings do not establish readiness"}
