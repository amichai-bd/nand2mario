"""Verilator discovery and argv-only native execution."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess

from .verilator import diagnostic


class ToolError(RuntimeError):
    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


class Simulator:
    def __init__(self, backend="verilator", verilator_bin=None):
        if backend != "verilator":
            raise ToolError(f"unsupported simulator: {backend}; only Verilator is supported")
        self.backend = "verilator"
        self.discover_verilator(verilator_bin)

    def discover_verilator(self, directory):
        """Find verilator and the C++ compiler it drives; record both identities."""
        if directory is not None and (not directory or not Path(directory).is_dir()):
            raise ToolError("--verilator-bin must name an existing tool directory")
        self.tools = {}
        self.info = {"backend": "verilator", "tools": {}, "discovery": []}
        candidate = str(Path(directory) / "verilator") if directory is not None else "verilator"
        found = shutil.which(candidate)
        if not found:
            raise ToolError("missing verilator; select the Verilator tool directory explicitly")
        path = str(Path(found).resolve())
        result = self.run([path, "--version"])
        self.info["discovery"].append({"argv": [path, "--version"], "exit_code": result.returncode,
                                       "output": result.stdout})
        match = re.match(r"Verilator (\d+\.\d+)\b", result.stdout.strip())
        if result.returncode or not match or diagnostic(result.stdout):
            raise ToolError(f"could not identify Verilator: {result.stdout.strip()}", result.stdout)
        self.tools["verilator"] = path
        self.info["tools"]["verilator"] = {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                                           "version": result.stdout.strip(), "release": match[1]}
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

    def run(self, argv, cwd=None, timeout=60, env=None):
        command = argv
        try:
            return subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8",
                                  errors="replace", stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            output = getattr(error, "stdout", "") or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            raise ToolError(f"command failed: {command}: {error}", output) from error

    def path(self, path):
        return str(Path(path).resolve())

    def command(self, argv):
        return argv
