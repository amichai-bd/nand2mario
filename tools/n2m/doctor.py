"""Read-only readiness evidence. Device enumeration never opens a serial port."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

from .fpga import ALLOCATOR_NOTICE, ALLOCATOR_OVERRIDE, ALLOCATOR_OVERRIDE_NOTICE, quartus_environment
from .records import file_hash
from .questa import diagnostic as questa_diagnostic, write_macro
from .simulator import QUESTA_COMPILE_TOOLS, ToolError, questa_tools, verilator_executable
from .verilator_install import discovery_note

SMOKE = "src/dv/builder/builder_smoke.sv"
SMOKE_SIGNATURE = "PASS builder-smoke seed=1 checks=22"
SMOKE_FAULT = "count cycle=3 expected=7 actual=3 seed=1"
# Verilator consults no license. The check removes these so a PASS cannot depend on them.
LICENSE_VARIABLES = ("SALT_LICENSE_FILE", "SALT_LICENSE_SERVER", "LM_LICENSE_FILE", "MGLS_LICENSE_FILE")


def execute(argv, cwd, log, timeout=60, env=None, expect_failure=False):
    with (cwd / "commands.log").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(argv) + "\n")
    try:
        # env=None inherits the caller's environment unchanged. Quartus passes its allocator
        # override; Verilator passes the environment with license variables removed.
        result = subprocess.run(argv, cwd=cwd, text=True, encoding="utf-8",
                                errors="replace", stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout, env=env)
        output = result.stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        output = getattr(error, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        (cwd / log).write_text(output + "\n" + str(error), encoding="utf-8")
        raise RuntimeError(f"command unavailable or timed out; see {log}") from error
    (cwd / log).write_text(output, encoding="utf-8")
    if expect_failure:
        if not result.returncode:
            raise RuntimeError(f"expected a nonzero exit; see {log}")
        return output
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
    # A zero-warning summary line is not a diagnostic.
    return bool(re.search(r"(?im)^.*\bwarning(?:s)?\b(?!\s*:\s*0\b).*$", output))


def verilator_diagnostic(output):
    # Verilator prefixes lint and runtime diagnostics with %Warning, %Error or %Fatal.
    return bool(re.search(r"%(?:Warning|Error|Fatal)\b", output))


def unlicensed_environment():
    return {k: v for k, v in os.environ.items() if k not in LICENSE_VARIABLES}


def verilator(root, folder, directory):
    found, source = verilator_executable(directory, root)
    if not found:
        raise RuntimeError("missing verilator; select its tool directory explicitly "
                           f"({discovery_note(root)})")
    tool = str(Path(found).resolve())
    env = unlicensed_environment()
    version = execute([tool, "--version"], folder, "version.log", env=env)
    match = re.match(r"Verilator (\d+\.\d+)", version.strip())
    if not match or verilator_diagnostic(version):
        raise RuntimeError("unrecognized Verilator version or diagnostic; see version.log")
    # --binary compiles and elaborates the smoke into obj_dir/smoke; lint warnings fail the build.
    compiled = execute([tool, "--binary", "--timing", "--trace-vcd", "--x-initial", "unique",
                        "-j", "0", "--Mdir", "obj_dir", "-o", "smoke", str(root / SMOKE)],
                       folder, "compile.log", timeout=300, env=env)
    if verilator_diagnostic(compiled):
        raise RuntimeError("simulator diagnostic; see compile.log")
    (folder / "waves").mkdir(exist_ok=True)
    binary = str(folder / "obj_dir" / "smoke")
    output = execute([binary, "+seed=1", "+verilator+rand+reset+2"], folder, "sim.log", env=env)
    if SMOKE_SIGNATURE not in output or verilator_diagnostic(output):
        raise RuntimeError("simulation diagnostic or missing checked result; see sim.log")
    # The same binary must also be able to fail: the injected mismatch exits nonzero.
    fault = execute([binary, "+seed=1", "+verilator+rand+reset+2", "+inject_failure"],
                    folder, "fault.log", env=env, expect_failure=True)
    if SMOKE_FAULT not in fault or SMOKE_SIGNATURE in fault:
        raise RuntimeError("injected fault was not reported; see fault.log")
    return {"version": version.strip(), "release": match[1], "tools": {"verilator": tool},
            "discovery": source,
            "license": "none consulted; " + ", ".join(LICENSE_VARIABLES) + " removed from the check environment",
            "fault": {"expected": SMOKE_FAULT, "detected": True}}


def questa(root, folder, directory):
    """Compile, elaborate, run and fault-check the smoke under native Questa."""
    names = {name: executable(directory, name) for name in ("vlib", "vmap", "vlog", "vsim")}
    version = execute([names["vsim"], "-version"], folder, "version.log")
    if "Questa" not in version or questa_diagnostic(version):
        raise RuntimeError("unrecognized Questa version or diagnostic; see version.log")
    execute([names["vmap"], "-c"], folder, "ini.log")
    library = execute([names["vlib"], "work"], folder, "library.log")
    if questa_diagnostic(library):
        raise RuntimeError("simulator diagnostic; see library.log")
    compiled = execute([names["vlog"], "-sv", "-work", "work", str(root / SMOKE)],
                       folder, "compile.log")
    if questa_diagnostic(compiled):
        raise RuntimeError("simulator diagnostic; see compile.log")
    (folder / "waves").mkdir(exist_ok=True)
    write_macro(folder)
    base = [names["vsim"], "-c", "-onfinish", "stop", "-wlf"]
    output = execute([*base, "waves/smoke.wlf", "work.builder_smoke", "+seed=1",
                      "-do", "do run.do"], folder, "sim.log")
    if SMOKE_SIGNATURE not in output or questa_diagnostic(output):
        raise RuntimeError("simulation diagnostic or missing checked result; see sim.log")
    fault = execute([*base, "waves/fault.wlf", "work.builder_smoke", "+seed=1",
                     "+inject_failure", "-do", "do run.do"], folder, "fault.log",
                    expect_failure=True)
    if SMOKE_FAULT not in fault or SMOKE_SIGNATURE in fault or questa_diagnostic(fault, SMOKE_FAULT):
        raise RuntimeError("injected fault was not reported; see fault.log")
    return {"version": version.strip(), "tools": names,
            "license": "runtime checkout succeeded for this smoke invocation",
            "fault": {"expected": SMOKE_FAULT, "detected": True}}


def questa_lint(folder, directory):
    """Report that the compile gate's tools are present; the gate itself is not run."""
    try:
        tools, info = questa_tools(directory, QUESTA_COMPILE_TOOLS,
                                   lambda argv: _record(argv, folder))
    except ToolError as error:
        raise RuntimeError(str(error)) from error
    return {"tools": tools, "versions": {name: detail.get("version") for name, detail in info["tools"].items()
                                          if "version" in detail},
            "command": "python tools/build.py lint questa --tag <tag> --json",
            "license": "none required; vlog and vopt only",
            "scope": "tool availability only; run the command for compile evidence"}


def _record(argv, folder):
    from types import SimpleNamespace
    output = execute(argv, folder, Path(argv[0]).stem + "-version.log")
    return SimpleNamespace(returncode=0, stdout=output)


def quartus(folder, directory):
    tool = executable(directory, "quartus_sh")
    # Same process-only override as the build flow, so both see the same Quartus behavior.
    output = execute([tool, "--version"], folder, "version.log", env=quartus_environment())
    if "Quartus" not in output or "Version " not in output:
        raise RuntimeError("unrecognized Quartus version output")
    # The fitter owns this pinned text; only that exact notice is explained here.
    explained = [line.strip() for line in output.splitlines() if line.strip() == ALLOCATOR_NOTICE]
    if warning(output) or any(line.strip() and line.strip() != ALLOCATOR_NOTICE
                              and not line.startswith(("Quartus", "Version ", "Copyright"))
                              for line in output.splitlines()):
        raise RuntimeError("unexplained Quartus diagnostic; see version.log")
    lite = "Lite Edition" in output
    return {"path": tool, "version": output.strip(),
            "license": "Lite requires no license file" if lite else "not verified; synthesis was not run",
            "explained_diagnostics": [{"code": "TBBmalloc", "text": line} for line in explained],
            "environment": dict(ALLOCATOR_OVERRIDE), "notice": ALLOCATOR_OVERRIDE_NOTICE,
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
        raise RuntimeError("selected UART is not healthy in the OS device inventory; see ports.log")
    return {"selected": matches[0], "ports": ports,
            "scope": "OS identity only; port not opened, no DTR/RTS or bytes sent"}


def windows_ports(folder):
    """The Windows CIM PnP Ports inventory; a read-only query that opens nothing."""
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
    return ports


# udev's stable serial naming and the sysfs USB attributes behind it. Both are
# read; nothing is opened, and no device node is written.
SERIAL_BY_ID = Path("/dev/serial/by-id")
TTY_CLASS = Path("/sys/class/tty")
USB_ATTRIBUTES = ("idVendor", "idProduct", "serial", "manufacturer", "product")
# How far up the sysfs device chain the owning USB device may sit: the tty, its
# interface, the device. The bound is a stop, not an expectation.
USB_DEPTH = 6


def node_state(path):
    """Classify one device node as the port inventory's health, without opening it.

    Healthy means the udev name still resolves to a character device this user
    can read and write. Each refusal names what it found.
    """
    try:
        mode = os.stat(path).st_mode
    except OSError as error:
        return "Error", 1, f"device node unavailable: {error.strerror or error}"
    if not stat.S_ISCHR(mode):
        return "Error", 2, "not a character device"
    if not os.access(path, os.R_OK | os.W_OK):
        return "Error", 3, "no read and write permission on the device node"
    return "OK", 0, ""


def usb_attributes(node_name, tty_class=None):
    """Read the owning USB device's pinned sysfs attributes for one tty name.

    Walks up from the tty's bound device to the first ancestor carrying
    `idVendor`, which is the USB device itself rather than its interface.
    """
    base = Path(tty_class or TTY_CLASS) / node_name / "device"
    try:
        current = Path(os.path.realpath(base))
    except OSError:
        return None
    for _ in range(USB_DEPTH):
        if (current / "idVendor").is_file():
            values = {}
            for name in USB_ATTRIBUTES:
                try:
                    values[name] = (current / name).read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    values[name] = ""
            values["path"] = str(current)
            return values
        if current.parent == current:
            break
        current = current.parent
    return None


def linux_identity(vid, pid, link_name):
    """The stable OS identity: the USB ids udev matched, then its own stable name.

    Same shape as the Windows PnP identity so one selection rule serves both
    hosts; the tail is udev's `/dev/serial/by-id` name, which survives replug
    and renumbering.
    """
    tail = link_name[4:] if link_name.startswith("usb-") else link_name
    return f"USB\\VID_{vid.upper()}&PID_{pid.upper()}\\{tail}"


def linux_ports(folder):
    """Enumerate Linux serial ports from udev's by-id links and sysfs; open nothing.

    Only ports udev gave a stable `/dev/serial/by-id` name and a USB
    vendor/product identity are reported: without both there is nothing to
    select by. The records carry the keys the selection rule reads on either
    host, plus the Linux facts they were derived from.
    """
    ports = []
    links = sorted(SERIAL_BY_ID.iterdir()) if SERIAL_BY_ID.is_dir() else []
    for link in links:
        node = Path(os.path.realpath(link))
        attributes = usb_attributes(node.name)
        if not attributes or not attributes.get("idVendor") or not attributes.get("idProduct"):
            continue
        status, code, detail = node_state(node)
        name = " ".join(part for part in (attributes.get("manufacturer"), attributes.get("product")) if part)
        ports.append({"Name": f"{name} ({node})" if name else str(node),
                      "PNPDeviceID": linux_identity(attributes["idVendor"], attributes["idProduct"], link.name),
                      "Status": status, "ConfigManagerErrorCode": code, "Detail": detail,
                      "DeviceID": str(node), "ByIdPath": str(link), "SysfsPath": attributes["path"],
                      "Serial": attributes.get("serial", ""),
                      "Manufacturer": attributes.get("manufacturer", ""),
                      "Product": attributes.get("product", "")})
    (folder / "ports.log").write_text(json.dumps({"by_id": str(SERIAL_BY_ID), "ports": ports},
                                                 indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ports


def uart(folder, args):
    """Enumerate serial ports on this host and apply the one selection rule."""
    if os.name == "nt":
        return select_uart(windows_ports(folder), args)
    if sys.platform.startswith("linux"):
        return select_uart(linux_ports(folder), args)
    return {"status": "WARNING", "detail": "UART enumeration supported on Windows and Linux only"}


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

    backend = args.sim
    if backend == "verilator":
        check(backend, lambda folder: verilator(root, folder, args.verilator_bin))
    else:
        check(backend, lambda folder: questa(root, folder, args.questa_bin))
        check("questa-lint", lambda folder: questa_lint(folder, args.questa_bin))
    untested = ["Quartus", "JTAG", "UART"]
    if args.profile == "environment":
        check("quartus", lambda folder: quartus(folder, args.quartus_bin))
        check("jtag", lambda folder: parse_jtag(execute(
            [executable(args.quartus_bin, "jtagconfig")], folder, "chain.log"), args.jtag_cable))
        check("uart", lambda folder: uart(folder, args))
        untested = ["Quartus synthesis", "physical wiring/voltage", "UART communication", "FPGA programming"]
    applicable = [c["status"] for c in checks.values()]
    status = "FAIL" if "FAIL" in applicable else "WARNING" if "WARNING" in applicable else "PASS"
    return {"status": status, "checks": checks,
            "profile": args.profile, "simulator": backend,
            "inputs": {p.relative_to(root).as_posix(): file_hash(p) for p in
                       [root / SMOKE, *(root / "tools/n2m").glob("*.py")]},
            "tools": checks[backend].get("tools", {}), "untested": untested,
            "readiness": "complete" if applicable and all(s == "PASS" for s in applicable) else "partial",
            "scope": f"{args.profile} checks only; warnings do not establish readiness"}
