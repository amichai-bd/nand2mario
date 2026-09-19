"""Native simulator discovery and argv-only execution."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

from .verilator import diagnostic as verilator_diagnostic
from .questa import diagnostic as questa_diagnostic
from .verilator_install import discovery_note, installed as installed_verilator


QUESTA_SIMULATION_TOOLS = ("vlib", "vmap", "vlog", "vsim")
# The compile gate elaborates with vopt and never launches vsim.
QUESTA_COMPILE_TOOLS = ("vlib", "vmap", "vlog", "vopt")
# vsim is the only Questa tool a run launches that checks out a runtime license.
# vlib, vmap, vlog and vopt consult none, which is why the compile gate needs no
# license on any host. `vsim -version` prints its banner without a checkout too,
# so identifying vsim proves nothing about running it: the checkout is its own
# fact and this probe is the only way to learn it before a run depends on it.
# The probe loads no design. `-c` starts the console kernel, which forces the
# checkout; `quit -f` leaves at once; `-nolog` writes no transcript into the
# caller's directory; `-lic_noqueue` refuses to wait behind a busy license
# server instead of blocking the probe.
QUESTA_LICENSE_PROBE = ("-c", "-nolog", "-lic_noqueue", "-do", "quit -f")
# Only an unconfigured or unreachable license refuses, because no amount of
# waiting supplies one. These are vsim's CAUSE lines, printed first.
#
# They are matched instead of the terminal lines that follow them, because those
# are generic: `Unable to checkout a license.  Vsim is closing.` and
# `Invalid license environment. Application closing.` are what vsim prints after
# ANY failed startup checkout. libvsim.so carries that pair in the same routine
# as its queue messages, and `-lic_noqueue` skips the queue branch into it, so a
# host whose seats are merely taken prints the same closing pair. Matching it
# would refuse a correctly licensed host and misname the reason. Contention
# (`All ... currently in use`, `Licensed number of users already reached`) must
# reach the run, which queues without `-lic_noqueue` and passes.
# Searched against the whole output, not per line: vsim wraps the unreachable-server
# cause across two lines, so `run 'lmutil lmdiag'` lands on the second one.
QUESTA_LICENSE_UNCONFIGURED = re.compile(
    r"(?is)unable to find the licen[cs]e file"          # nothing configured
    r"|run\s+'lmutil\s+lmdiag'")                        # configured but unreachable
# The generic closing lines. Everything before the first of them is the cause
# vsim actually reported, wrapped or not, and that is what the refusal quotes.
QUESTA_LICENSE_CLOSING = re.compile(
    r"(?i)vsim is closing|invalid licen[cs]e environment|application closing")
QUESTA_LICENSE = ("no Questa runtime license: vsim found no usable license file or server. "
                  "Point SALT_LICENSE_SERVER or LM_LICENSE_FILE at a license that grants "
                  "vsim and retry; the Questa compile gate needs none because it never "
                  "launches vsim")


class ToolError(RuntimeError):
    def __init__(self, message, output="", record=None):
        super().__init__(message)
        self.output = output
        # The probe or command record behind the failure, so a refusal carries
        # the same auditable evidence a pass puts in the discovery log.
        self.record = record


def run_tool(argv, cwd=None, timeout=60, env=None):
    """Run one argv without a shell; a launch failure or timeout is a ToolError."""
    try:
        return subprocess.run(argv, cwd=cwd, env=env, text=True, encoding="utf-8",
                              errors="replace", stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        output = getattr(error, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        raise ToolError(f"command failed: {argv}: {error}", output) from error


def questa_tools(directory, names, run=run_tool):
    """Resolve the named native Questa executables; record path, hash and banner.

    Discovery uses PATH or the explicit directory and never falls back between
    them. vlib has no version query; its path and hash are its identity.
    """
    if directory is not None and (not directory or not Path(directory).is_dir()):
        raise ToolError("--questa-bin must name an existing tool directory")
    tools = {}
    info = {"backend": "questa", "tools": {}, "discovery": []}
    for name in names:
        suffix = ".exe" if os.name == "nt" else ""
        candidate = str(Path(directory) / (name + suffix)) if directory is not None else name
        found = shutil.which(candidate)
        if not found:
            raise ToolError(f"missing {name}; select the Questa tool directory explicitly")
        path = str(Path(found).resolve())
        tools[name] = path
        detail = {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        if name != "vlib":
            result = run([path, "-version"])
            info["discovery"].append({"argv": [path, "-version"], "exit_code": result.returncode,
                                      "output": result.stdout})
            if result.returncode or questa_diagnostic(result.stdout) or "Questa" not in result.stdout:
                raise ToolError(f"could not identify Questa {name}: {result.stdout.strip()}", result.stdout)
            detail["version"] = result.stdout.strip()
        info["tools"][name] = detail
    return tools, info


def questa_license_cause(output):
    """The lines vsim printed before its generic closing pair, as one sentence.

    The cause may wrap across lines, so it is rejoined and its whitespace
    collapsed; quoting one matched line would start mid-sentence.
    """
    lines = []
    for line in output.splitlines():
        if QUESTA_LICENSE_CLOSING.search(line):
            break
        if line.strip():
            lines.append(line.strip())
    return " ".join(lines) or output.strip()


def questa_license(vsim, run=run_tool):
    """Prove vsim can check out a runtime license, and name the license when it cannot.

    Returns the probe record. Refusal needs both halves: a nonzero exit and a
    cause line saying the license is unconfigured or unreachable. The ToolError
    quotes that cause line, so the refusal names why, not just that it failed,
    and carries the record for the failure evidence.

    Everything else passes through. A taken seat, a vsim broken for another
    reason, and a zero exit whose output merely mentions a license all reach the
    run, which reports its own detail and can queue for a seat.
    """
    argv = [vsim, *QUESTA_LICENSE_PROBE]
    result = run(argv)
    output = result.stdout or ""
    unconfigured = bool(QUESTA_LICENSE_UNCONFIGURED.search(output))
    record = {"argv": argv, "exit_code": result.returncode, "output": output,
              "licensed": not (result.returncode and unconfigured)}
    if not record["licensed"]:
        raise ToolError(f"{QUESTA_LICENSE}: {questa_license_cause(output)}",
                        output, record=record)
    return record


def verilator_executable(directory, root=None, which=None):
    """Resolve verilator and say where it came from.

    Order: the explicit directory, then PATH, then the repository's own pinned
    installation under workdir/tools. An operator's PATH tool keeps precedence;
    the pin only removes the need for a PATH edit on a host without one.
    """
    which = which or shutil.which
    if directory is not None:
        if not directory or not Path(directory).is_dir():
            raise ToolError("--verilator-bin must name an existing tool directory")
        return which(str(Path(directory) / "verilator")), "explicit"
    found = which("verilator")
    if found:
        return found, "path"
    pinned = installed_verilator(root)
    return (which(str(pinned / "verilator")) if pinned else None), "pinned"


class Simulator:
    def __init__(self, backend, *, verilator_bin=None, questa_bin=None, root=None,
                 require_license=True):
        if backend not in ("verilator", "questa"):
            raise ToolError(f"unsupported simulator: {backend}; expected verilator or questa")
        if backend == "verilator" and questa_bin is not None:
            raise ToolError("--questa-bin applies only to --sim questa")
        if backend == "questa" and verilator_bin is not None:
            raise ToolError("--verilator-bin applies only to --sim verilator")
        self.backend = backend
        if backend == "verilator":
            self.discover_verilator(verilator_bin, root)
        else:
            self.discover_questa(questa_bin, require_license=require_license)

    def discover_verilator(self, directory, root=None):
        """Find verilator and the C++ compiler it drives; record both identities."""
        self.tools = {}
        self.info = {"backend": "verilator", "tools": {}, "discovery": []}
        found, source = verilator_executable(directory, root)
        if not found:
            raise ToolError(f"missing verilator; {discovery_note(root)}")
        path = str(Path(found).resolve())
        result = self.run([path, "--version"])
        self.info["discovery"].append({"argv": [path, "--version"], "exit_code": result.returncode,
                                       "output": result.stdout})
        match = re.match(r"Verilator (\d+\.\d+)\b", result.stdout.strip())
        if result.returncode or not match or verilator_diagnostic(result.stdout):
            raise ToolError(f"could not identify Verilator: {result.stdout.strip()}", result.stdout)
        self.tools["verilator"] = path
        self.info["tools"]["verilator"] = {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                                           "version": result.stdout.strip(), "release": match[1],
                                           "source": source}
        # Verilator's generated makefile calls this compiler; its identity is
        # part of the binary the run executes, so it enters the fingerprint.
        compiler = shutil.which(os.environ.get("CXX", "g++"))
        if not compiler:
            raise ToolError("missing C++ compiler for Verilator; install g++ or set CXX")
        banner = self.run([compiler, "--version"])
        self.info["discovery"].append({"argv": [compiler, "--version"], "exit_code": banner.returncode,
                                       "output": banner.stdout})
        if banner.returncode or not banner.stdout.strip():
            raise ToolError(f"could not identify the C++ compiler: {banner.stdout.strip()}", banner.stdout)
        compiler = str(Path(compiler).resolve())
        self.tools["cxx"] = compiler
        self.info["tools"]["cxx"] = {"path": compiler, "sha256": hashlib.sha256(Path(compiler).read_bytes()).hexdigest(),
                                     "version": banner.stdout.strip().splitlines()[0]}
        self.compiler = self.runtime = self.tools["verilator"]

    def discover_questa(self, directory, *, require_license=True):
        """Find the native Questa tools, record each identity, and prove the license.

        A simulation launches vsim, so availability is the pair: the executables
        are present and vsim can check out a runtime license. Discovery decides
        both by asking the tools, on whichever host is running.

        `require_license=False` skips only the probe, for `sim prepare`, whose
        host preparation launches no vsim and so consults no license.
        """
        self.tools, self.info = questa_tools(directory, QUESTA_SIMULATION_TOOLS, self.run)
        self.info["license_required"] = require_license
        if require_license:
            # The record joins the log either way: a refusal carries it on the
            # ToolError, because the caller never sees this object.
            self.info["discovery"].append(questa_license(self.tools["vsim"], self.run))
        self.compiler, self.runtime = self.tools["vlog"], self.tools["vsim"]

    def run(self, argv, cwd=None, timeout=60, env=None):
        return run_tool(argv, cwd=cwd, timeout=timeout, env=env)

    def path(self, path):
        return str(Path(path).resolve())

    def command(self, argv):
        return argv
