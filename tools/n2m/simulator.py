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


class ToolError(RuntimeError):
    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


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
    def __init__(self, backend, *, verilator_bin=None, questa_bin=None, root=None):
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
            self.discover_questa(questa_bin)

    def discover_verilator(self, directory, root=None):
        """Find verilator and the C++ compiler it drives; record both identities."""
        self.tools = {}
        self.info = {"backend": "verilator", "tools": {}, "discovery": []}
        found, source = verilator_executable(directory, root)
        if not found:
            raise ToolError("missing verilator; select the Verilator tool directory explicitly "
                            f"({discovery_note(root)})")
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

    def discover_questa(self, directory):
        """Find the native Questa tools and record each executable identity."""
        self.tools, self.info = questa_tools(directory, QUESTA_SIMULATION_TOOLS, self.run)
        self.compiler, self.runtime = self.tools["vlog"], self.tools["vsim"]

    def run(self, argv, cwd=None, timeout=60, env=None):
        return run_tool(argv, cwd=cwd, timeout=timeout, env=env)

    def path(self, path):
        return str(Path(path).resolve())

    def command(self, argv):
        return argv
