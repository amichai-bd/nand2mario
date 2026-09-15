"""Dependency-free keyboard and bounded-list primitives for the build menu."""
from dataclasses import dataclass
import os
import platform
import select
import sys


BACK = object()
VIEW_ROWS = 10


@dataclass(frozen=True)
class Choice:
    value: object
    label: str
    detail: str = ""


class WindowsConsoleMode:
    """Enable ANSI output on one Windows console and restore its prior mode."""

    STD_OUTPUT_HANDLE = -11
    ENABLE_PROCESSED_OUTPUT = 0x0001
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

    def __init__(self, kernel=None):
        self.kernel = kernel
        self.handle = None
        self.original = None

    def __enter__(self):
        import ctypes
        from ctypes import wintypes
        kernel = self.kernel or ctypes.WinDLL("kernel32", use_last_error=True)
        if self.kernel is None:
            kernel.GetStdHandle.argtypes = [wintypes.DWORD]
            kernel.GetStdHandle.restype = wintypes.HANDLE
            kernel.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel.GetConsoleMode.restype = wintypes.BOOL
            kernel.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.SetConsoleMode.restype = wintypes.BOOL
        handle = kernel.GetStdHandle(wintypes.DWORD(self.STD_OUTPUT_HANDLE))
        mode = wintypes.DWORD()
        if not handle or not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError("stdout is not a Windows console with readable output mode")
        enabled = mode.value | self.ENABLE_PROCESSED_OUTPUT | self.ENABLE_VIRTUAL_TERMINAL_PROCESSING
        if not kernel.SetConsoleMode(handle, enabled):
            raise OSError("could not enable Windows virtual-terminal output")
        self.kernel, self.handle, self.original = kernel, handle, mode.value
        return self

    def __exit__(self, *error):
        if self.handle is not None and not self.kernel.SetConsoleMode(self.handle, self.original):
            raise OSError("could not restore Windows console output mode")


def decode_posix(first, read_more):
    """Decode one POSIX raw-terminal key; ``read_more`` must not block."""
    if first in ("\r", "\n"):
        return "ENTER"
    if first in ("\x7f", "\b"):
        return "BACKSPACE"
    if first != "\x1b":
        return first
    tail = read_more()
    if not tail or tail != "[":
        return "ESC"
    return {"A": "UP", "B": "DOWN", "C": "RIGHT", "D": "LEFT"}.get(read_more(), "ESC")


def decode_windows(first, read_more):
    """Decode one Windows ``msvcrt.getwch`` key sequence."""
    if first in ("\r", "\n"):
        return "ENTER"
    if first == "\x1b":
        return "ESC"
    if first == "\b":
        return "BACKSPACE"
    if first in ("\x00", "\xe0"):
        return {"H": "UP", "P": "DOWN", "M": "RIGHT", "K": "LEFT"}.get(read_more(), "UNKNOWN")
    return first


class Terminal:
    """Small cross-platform raw terminal. Tests provide a scripted double."""

    def __init__(self, stdin=None, stdout=None, system=None, windows_console=None):
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.system = system or platform.system()
        self._saved = None
        self._windows_console = windows_console

    def interactive(self):
        return self.stdin.isatty() and self.stdout.isatty()

    def __enter__(self):
        if self.system == "Windows":
            self._windows_console = self._windows_console or WindowsConsoleMode()
            self._windows_console.__enter__()
        else:
            import termios
            import tty
            self._saved = termios.tcgetattr(self.stdin.fileno())
            tty.setcbreak(self.stdin.fileno())
        try:
            self.stdout.write("\x1b[?25l")
            self.stdout.flush()
        except Exception:
            if self._windows_console is not None:
                self._windows_console.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *error):
        if self._saved is not None:
            import termios
            termios.tcsetattr(self.stdin.fileno(), termios.TCSADRAIN, self._saved)
        try:
            self.stdout.write("\x1b[?25h\x1b[0m\n")
            self.stdout.flush()
        finally:
            if self._windows_console is not None:
                self._windows_console.__exit__(*error)

    def draw(self, lines):
        self.stdout.write("\x1b[2J\x1b[H" + "\n".join(lines) + "\n")
        self.stdout.flush()

    def key(self):
        if self.system == "Windows":
            import msvcrt
            return decode_windows(msvcrt.getwch(), msvcrt.getwch)
        fd = self.stdin.fileno()
        first = os.read(fd, 1).decode("utf-8", errors="ignore")

        def available():
            ready, _, _ = select.select([fd], [], [], 0.03)
            return os.read(fd, 1).decode("utf-8", errors="ignore") if ready else ""
        return decode_posix(first, available)


class Menu:
    def __init__(self, terminal):
        self.terminal = terminal

    def choose(self, title, choices, *, hint="Use arrows and Enter. Type to filter. Escape goes back."):
        choices = list(choices)
        if not choices:
            self.terminal.draw([title, "", "No applicable choices were found.", "", "Press Escape to go back."])
            while self.terminal.key() != "ESC":
                pass
            return BACK
        query, selected = "", 0
        while True:
            shown = [choice for choice in choices if query.casefold() in choice.label.casefold()]
            selected = min(selected, max(0, len(shown) - 1))
            start = max(0, min(selected - VIEW_ROWS // 2, max(0, len(shown) - VIEW_ROWS)))
            rows = [title, "", hint]
            if query:
                rows.append(f"Filter: {query}")
            rows.append("")
            if not shown:
                rows.append("  No matches. Backspace edits the filter.")
            for index, choice in enumerate(shown[start:start + VIEW_ROWS], start):
                mark = ">" if index == selected else " "
                rows.append(f"{mark} {choice.label}")
                if index == selected and choice.detail:
                    rows.append(f"    {choice.detail}")
            if len(shown) > VIEW_ROWS:
                rows.append(f"  {selected + 1}/{len(shown)}")
            self.terminal.draw(rows)
            key = self.terminal.key()
            if key == "UP" and shown:
                selected = (selected - 1) % len(shown)
            elif key == "DOWN" and shown:
                selected = (selected + 1) % len(shown)
            elif key == "ENTER" and shown:
                return shown[selected].value
            elif key == "ESC":
                return BACK
            elif key == "BACKSPACE":
                query = query[:-1]
                selected = 0
            elif isinstance(key, str) and len(key) == 1 and key.isprintable():
                query += key
                selected = 0

    def text(self, title, *, default="", required=True):
        value = ""
        while True:
            shown = value or (f"[{default}]" if default else "")
            self.terminal.draw([title, "", "Type a value. Enter accepts. Escape goes back.", "", "> " + shown])
            key = self.terminal.key()
            if key == "ESC":
                return BACK
            if key == "ENTER":
                accepted = value or str(default or "")
                if accepted or not required:
                    return accepted
            elif key == "BACKSPACE":
                value = value[:-1]
            elif isinstance(key, str) and len(key) == 1 and key.isprintable():
                value += key
