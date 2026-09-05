"""Icarus discovery and argv-only native/WSL execution."""
import os
from pathlib import Path
import shutil
import subprocess


class ToolError(RuntimeError):
    pass


class Simulator:
    def __init__(self, backend="auto", iverilog=None, vvp=None, distro=None):
        if backend == "auto":
            backend = "icarus" if shutil.which(iverilog or "iverilog") else "wsl-icarus"
        self.backend = backend
        self.prefix = []
        if backend == "wsl-icarus":
            if os.name != "nt" or not shutil.which("wsl"):
                raise ToolError("Icarus not found; install pinned tools or select explicit --iverilog/--vvp paths")
            self.prefix = ["wsl", *(["-d", distro] if distro else []), "--exec"]
        self.compiler = iverilog or "iverilog"
        self.runtime = vvp or "vvp"
        self.info = {"backend": backend, "distro": distro, "tools": {}}
        for tool in (self.compiler, self.runtime):
            result = self.run([tool, "-V"])
            lines = result.stdout.splitlines()
            version = next((s for s in lines if "Icarus Verilog" in s and "version" in s), "")
            if result.returncode or not version:
                raise ToolError(f"could not identify {tool}: {result.stdout.strip()}")
            if not self.prefix:
                location = str(Path(shutil.which(tool)).resolve())
            else:
                found = self.run(["which", tool])
                location = found.stdout.strip() if found.returncode == 0 else tool
                resolved = self.run(["readlink", "-f", location])
                if resolved.returncode == 0:
                    location = resolved.stdout.strip()
            self.info["tools"][tool] = {"path": location, "version": version}
            if tool == self.compiler:
                self.compiler = location
            else:
                self.runtime = location

    def run(self, argv, cwd=None, timeout=60):
        command = self.prefix + argv
        try:
            # WSL inherits the Windows working directory; all paths passed to
            # its compiler/runtime are translated individually, without a shell.
            return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8",
                                  errors="replace", stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ToolError(f"command failed: {command}: {error}") from error

    def path(self, path):
        path = str(Path(path).resolve())
        if not self.prefix:
            return path
        result = self.run(["wslpath", "-a", "-u", path])
        if result.returncode:
            raise ToolError(f"cannot translate path {path}: {result.stdout}")
        return result.stdout.strip()

    def command(self, argv):
        return self.prefix + argv

