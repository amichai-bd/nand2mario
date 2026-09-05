"""Explicit simulator discovery and argv-only native/WSL execution."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from .questa import diagnostic


class ToolError(RuntimeError):
    def __init__(self, message, output=""):
        super().__init__(message)
        self.output = output


class Simulator:
    def __init__(self, backend="auto", iverilog=None, vvp=None, distro=None, questa_bin=None):
        if backend == "questa":
            if any(value is not None for value in (iverilog, vvp, distro)):
                raise ToolError("Questa does not accept Icarus or WSL tool options")
            self.backend, self.prefix = "questa", []
            self.discover_questa(questa_bin)
            return
        if questa_bin is not None:
            raise ToolError("--questa-bin requires explicit --sim questa")
        if backend not in ("auto", "icarus", "wsl-icarus"):
            raise ToolError(f"unsupported simulator: {backend}")
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

    def discover_questa(self, directory):
        if directory is not None and (not directory or not Path(directory).is_dir()):
            raise ToolError("--questa-bin must name an existing tool directory")
        self.tools = {}
        self.info = {"backend": "questa", "tools": {}, "discovery": []}
        for name in ("vlib", "vmap", "vlog", "vsim"):
            candidate = str(Path(directory) / (name + (".exe" if os.name == "nt" else ""))) \
                if directory is not None else name
            found = shutil.which(candidate)
            if not found:
                raise ToolError(f"missing {name}; select the Questa tool directory explicitly")
            path = str(Path(found).resolve())
            self.tools[name] = path
            detail = {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
            # vlib does not expose -version; retain its executable identity.
            if name != "vlib":
                result = self.run([path, "-version"])
                self.info["discovery"].append({"argv": [path, "-version"],
                                               "exit_code": result.returncode, "output": result.stdout})
                if result.returncode or diagnostic(result.stdout) or "Questa" not in result.stdout:
                    raise ToolError(f"could not identify Questa {name}: {result.stdout.strip()}", result.stdout)
                detail["version"] = result.stdout.strip()
            self.info["tools"][name] = detail
        self.compiler, self.runtime = self.tools["vlog"], self.tools["vsim"]

    def run(self, argv, cwd=None, timeout=60):
        command = self.prefix + argv
        try:
            # WSL inherits the Windows working directory; all paths passed to
            # its compiler/runtime are translated individually, without a shell.
            return subprocess.run(command, cwd=cwd, text=True, encoding="utf-8",
                                  errors="replace", stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            output = getattr(error, "stdout", "") or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            raise ToolError(f"command failed: {command}: {error}", output) from error

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
