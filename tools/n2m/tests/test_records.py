"""Atomic publication failures; native handles supplement portable injection."""
import ctypes
import errno
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.records import atomic_text

ROOT = Path(__file__).resolve().parents[3]


def denial(code):
    error = PermissionError(errno.EACCES, "injected publication denial")
    error.winerror = code
    return error


class AtomicRecordsTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/record-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="space ", dir=base)
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "result.json"
        self.path.write_text("old")
        self.other = self.path.with_name("unrelated.tmp")
        self.other.write_text("keep")

    def assert_preserved(self, value):
        self.assertEqual(self.path.read_text(), value)
        self.assertEqual(self.other.read_text(), "keep")
        self.assertEqual(list(self.path.parent.glob("result.json.*.tmp")), [])

    def test_transient_windows_denials_preserve_old_until_replace(self):
        real_replace = os.replace
        for code in (5, 32, 33):
            with self.subTest(code=code):
                self.path.write_text("old")
                calls = []
                def replace(source, destination):
                    calls.append(source)
                    self.assertEqual(self.path.read_text(), "old")
                    self.assertEqual(Path(source).read_text(), "new")
                    if len(calls) < 3:
                        raise denial(code)
                    real_replace(source, destination)
                with patch("n2m.records.os.replace", side_effect=replace), patch("time.sleep") as sleep:
                    atomic_text(self.path, "new")
                self.assertEqual(sleep.call_count, 2)
                self.assertEqual(len(set(calls)), 1)
                self.assert_preserved("new")

    def test_permanent_denial_is_bounded_and_cleans_only_owned_temp(self):
        error = denial(5)
        with patch("n2m.records.os.replace", side_effect=error) as replace, patch("time.sleep") as sleep:
            with self.assertRaises(PermissionError) as caught:
                atomic_text(self.path, "new")
        self.assertIs(caught.exception, error)
        self.assertEqual(replace.call_count, 6)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.01, .02, .04, .08, .16])
        self.assert_preserved("old")

    def test_other_errors_fail_without_retry(self):
        for error in (PermissionError(errno.EACCES, "posix denial"), denial(87), OSError(errno.ENOSPC, "full")):
            with self.subTest(error=error), patch("n2m.records.os.replace", side_effect=error), patch("time.sleep") as sleep:
                with self.assertRaises(OSError) as caught:
                    atomic_text(self.path, "new")
                self.assertIs(caught.exception, error)
                sleep.assert_not_called()
                self.assert_preserved("old")

    def test_partial_write_failure_cleans_temp(self):
        def fail(path, *args, **kwargs):
            path.write_bytes(b"partial")
            raise OSError(errno.ENOSPC, "full")
        with patch.object(Path, "write_text", fail):
            with self.assertRaises(OSError):
                atomic_text(self.path, "new")
        self.assert_preserved("old")

    @unittest.skipUnless(os.name == "nt", "requires Windows file sharing")
    def test_native_handle_without_delete_sharing(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        # GENERIC_READ, FILE_SHARE_READ|WRITE (no DELETE), OPEN_EXISTING.
        handle = kernel.CreateFileW(str(self.path), 0x80000000, 3, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        closed = False
        def release(_):
            nonlocal closed
            self.assertEqual(self.path.read_text(), "old")
            self.assertTrue(kernel.CloseHandle(handle))
            closed = True
        try:
            probe = self.path.with_name("probe.tmp")
            probe.write_text("probe")
            with self.assertRaises(PermissionError) as caught:
                os.replace(probe, self.path)
            self.assertIn(caught.exception.winerror, (5, 32, 33))
            print(f"native held-handle os.replace: WinError {caught.exception.winerror}")
            probe.unlink()
            with patch("time.sleep", side_effect=release) as sleep:
                atomic_text(self.path, "new")
            self.assertEqual(sleep.call_count, 1)
            self.assert_preserved("new")
        finally:
            if not closed:
                kernel.CloseHandle(handle)
