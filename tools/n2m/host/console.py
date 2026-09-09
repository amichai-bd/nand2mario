"""Foreground classic Windows console events, without global keyboard capture."""
import ctypes
import os
from ctypes import wintypes as w


class Key(ctypes.Structure):
    _fields_ = [('down', w.BOOL), ('repeat', w.WORD), ('code', w.WORD),
                ('scan', w.WORD), ('character', w.WCHAR), ('modifiers', w.DWORD)]


class Data(ctypes.Union):
    _fields_ = [('key', Key), ('focus', w.BOOL), ('raw', ctypes.c_byte * 16)]


class Record(ctypes.Structure):
    _fields_ = [('kind', w.WORD), ('data', Data)]


class Console:
    def __enter__(self):
        if os.name != 'nt':
            raise RuntimeError('keyboard requires a local Windows classic console')
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        signatures = (
            (self.kernel, 'GetStdHandle', [w.DWORD], w.HANDLE),
            (self.kernel, 'GetConsoleWindow', [], w.HWND),
            (self.kernel, 'GetConsoleMode', [w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
            (self.kernel, 'SetConsoleMode', [w.HANDLE, w.DWORD], w.BOOL),
            (self.kernel, 'WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD),
            (self.kernel, 'ReadConsoleInputW', [w.HANDLE, ctypes.POINTER(Record), w.DWORD, ctypes.POINTER(w.DWORD)], w.BOOL),
            (self.kernel, 'GetNumberOfConsoleInputEvents', [w.HANDLE, ctypes.POINTER(w.DWORD)], w.BOOL),
            (self.user, 'GetForegroundWindow', [], w.HWND),
            (self.user, 'IsWindowVisible', [w.HWND], w.BOOL),
        )
        for library, name, arguments, result in signatures:
            function = getattr(library, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.kernel.GetStdHandle(-10)
        self.window = self.kernel.GetConsoleWindow()
        self.mode = w.DWORD()
        if not (self.kernel.GetConsoleMode(self.handle, ctypes.byref(self.mode))
                and self.window and self.user.IsWindowVisible(self.window)
                and self.focused()):
            raise RuntimeError('use a visible foreground classic console; redirected input and Windows Terminal are unsupported')
        # Disable cooked input, Ctrl+C signals and Quick Edit suspension. All
        # changes belong to this console and are restored, not global defaults.
        if not self.kernel.SetConsoleMode(self.handle, (self.mode.value | 0x80) & ~0x47):
            raise ctypes.WinError(ctypes.get_last_error())
        self.blocked = set()
        try:
            self.discard_pending()
        except BaseException:
            self.__exit__()
            raise
        return self

    def focused(self):
        return self.user.GetForegroundWindow() == self.window

    def discard_pending(self):
        """Discard pre-capture edges; a queued held key needs its release first."""
        from .keyboard import KEYS
        held = set(self.blocked)
        self.blocked = set()
        drained = 0
        while True:
            if not self.focused():
                raise RuntimeError('console lost foreground before capture')
            count = w.DWORD()
            if not self.kernel.GetNumberOfConsoleInputEvents(self.handle, ctypes.byref(count)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not count.value:
                break
            drained += 1
            if drained > 256:
                raise RuntimeError('console startup queue exceeded 256 events')
            event = self.next_event()
            if event and event[0] == 'focus-lost':
                raise RuntimeError('queued console focus loss before capture')
            if event and event[0] == 'key' and event[1] in KEYS:
                if event[2]: held.add(event[1])
                else: held.discard(event[1])
        self.blocked = held

    def next_event(self):
        if not self.focused():
            return ('focus-lost',)
        waited = self.kernel.WaitForSingleObject(self.handle, 20)
        if waited == 258:
            return None
        if waited != 0:
            raise RuntimeError('console input wait failed')
        if not self.focused():
            return ('focus-lost',)
        count = w.DWORD()
        if not self.kernel.GetNumberOfConsoleInputEvents(self.handle, ctypes.byref(count)):
            raise ctypes.WinError(ctypes.get_last_error())
        if count.value > 256:
            raise RuntimeError('console input backlog exceeded 256 events')
        record = Record()
        if not self.kernel.ReadConsoleInputW(self.handle, ctypes.byref(record), 1, ctypes.byref(count)) or count.value != 1:
            raise RuntimeError('console input read failed')
        if record.kind == 1:
            key = record.data.key
            code = 0xa1 if key.code == 0x10 and key.scan == 0x36 else key.code
            if code in self.blocked:
                if not key.down:
                    self.blocked.remove(code)
                return None
            return ('key', code, bool(key.down), key.modifiers)
        if record.kind == 0x10 and not record.data.focus:
            return ('focus-lost',)
        return None

    def __exit__(self, *_):
        if not self.kernel.SetConsoleMode(self.handle, self.mode.value):
            # Restoring a local console mode cannot create wire uncertainty.
            raise RuntimeError('failed to restore console input mode')
