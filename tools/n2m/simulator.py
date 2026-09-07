"""Questa discovery and argv-only native execution."""
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
    def __init__(self, backend="questa", questa_bin=None):
        if backend != "questa":
            raise ToolError(f"unsupported simulator: {backend}; only Questa is supported")
        self.backend = "questa"
        self.discover_questa(questa_bin)

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
