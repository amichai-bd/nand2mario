"""Small, flushed terminal progress for interactive builder commands."""
from contextlib import contextmanager
from pathlib import Path
import re
import sys
import time


class Progress:
    """Emit truthful stage transitions without changing machine records."""

    def __init__(self, enabled=True, stream=None, clock=None):
        self.enabled = enabled
        self.stream = stream or sys.stdout
        self.clock = clock or time.monotonic

    def line(self, text=""):
        if self.enabled:
            print(text, file=self.stream, flush=True)

    def begin(self, label, detail=None):
        suffix = f" — {detail}" if detail else ""
        self.line(f"[....] {label}{suffix}")
        return self.clock()

    def finish(self, label, started, status="done", detail=None):
        suffix = f" — {detail}" if detail else ""
        self.line(f"[{status}] {label} ({self.clock() - started:.1f}s){suffix}")

    @contextmanager
    def stage(self, label, detail=None, success="done"):
        """Print start and completion lines around one real operation."""
        started = self.begin(label, detail)
        try:
            yield
        except Exception:
            self.finish(label, started, "FAIL", detail)
            raise
        else:
            self.finish(label, started, success, detail)

    def cached(self, label, detail=None):
        """Name reused evidence without implying that the stage just ran."""
        suffix = f" — {detail}" if detail else ""
        self.line(f"[CACHED] {label} — reused checked result{suffix}")


def display_path(root, path):
    """Prefer a stable repository-relative path in human output."""
    path = Path(path)
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return str(path)


def powershell_command(argv):
    """Quote an argument vector so paths with spaces remain PowerShell-safe."""
    def quote(value):
        value = str(value)
        if re.fullmatch(r"[A-Za-z0-9_./:\\=-]+", value):
            return value
        return "'" + value.replace("'", "''") + "'"

    return " ".join(quote(value) for value in argv)
