"""Atomic publication failures; native handles supplement portable injection."""
import contextlib
import ctypes
import errno
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.records import atomic_bytes, atomic_text, pid_alive, stale_lock, workspace

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
        for publish in (lambda: atomic_text(self.path, "new"),
                        lambda: atomic_bytes(self.path, b"new")):
            with self.subTest(publish=publish):
                self.path.write_text("old")
                self.hold_open_across_replace(publish)

    def hold_open_across_replace(self, publish):
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
                publish()
            self.assertEqual(sleep.call_count, 1)
            self.assert_preserved("new")
        finally:
            if not closed:
                kernel.CloseHandle(handle)


def dead_pid():
    """A pid the OS has already retired."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid if not pid_alive(process.pid) else dead_pid()


class WorkspaceLockTests(unittest.TestCase):
    """A tag lock holds only while its recorded writer is alive."""
    def setUp(self):
        base = ROOT / "workdir/builds/record-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="lock ", dir=base)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.lock = self.root / "workdir/builds/tag/.lock"
        self.lock.parent.mkdir(parents=True)

    def test_pid_liveness_tracks_the_process(self):
        self.assertTrue(pid_alive(os.getpid()))
        self.assertFalse(pid_alive(dead_pid()))

    def test_dead_writer_lock_is_reclaimed_with_a_notice_and_a_fresh_lock(self):
        pid = dead_pid()
        self.lock.write_text(f"pid={pid}\n")
        self.assertTrue(stale_lock(self.lock))
        notices = []
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            with workspace(self.root, "tag", notices) as build:
                self.assertEqual(build, self.lock.parent)
                self.assertEqual(self.lock.read_text(), f"pid={os.getpid()}\n")
        self.assertEqual(notices, [self.lock])
        self.assertIn(f"reclaimed stale lock {self.lock}: its writer pid {pid} is not alive", stderr.getvalue())
        self.assertFalse(self.lock.exists())

    def test_a_reclaim_that_loses_the_race_never_removes_the_winners_lock(self):
        # B reads the dead owner; before B reclaims, A reclaims the same lock
        # and holds the tag. B must back off and A's live lock must survive.
        import n2m.records as records
        self.lock.write_text(f"pid={dead_pid()}\n")
        holder = contextlib.ExitStack()
        self.addCleanup(holder.close)
        real = records.lock_owner
        raced = []

        def owner_then_lose(lock):
            owner = real(lock)
            if lock == self.lock and not raced:
                raced.append(True)
                holder.enter_context(workspace(self.root, "tag"))
            return owner
        with patch("n2m.records.lock_owner", side_effect=owner_then_lose), \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "tag tag was taken by another writer|tag tag is locked"):
                with workspace(self.root, "tag"):
                    pass
        self.assertEqual(self.lock.read_text(), f"pid={os.getpid()}\n")
        self.assertEqual(sorted(p.name for p in self.lock.parent.iterdir()), [".lock"])
        holder.close()
        self.assertFalse(self.lock.exists())

    def test_a_held_lock_cannot_be_moved_or_removed_by_another_process(self):
        if os.name != "nt":
            self.skipTest("Windows sharing rules")
        with workspace(self.root, "tag"):
            for action in (lambda: os.replace(self.lock, self.lock.with_name("moved")), self.lock.unlink):
                with self.assertRaises(PermissionError):
                    action()
        self.assertFalse(self.lock.exists())

    def test_live_writer_lock_is_refused_by_name(self):
        self.lock.write_text(f"pid={os.getpid()}\n")
        self.assertFalse(stale_lock(self.lock))
        with self.assertRaisesRegex(ValueError, f"tag tag is locked by live pid {os.getpid()}; confirm its writer stopped"):
            with workspace(self.root, "tag"):
                pass
        self.assertEqual(self.lock.read_text(), f"pid={os.getpid()}\n")

    def test_unreadable_lock_is_refused_not_stolen(self):
        for content in ("", "owner=nobody\n", "pid=x\n"):
            with self.subTest(content=content):
                self.lock.write_text(content)
                self.assertFalse(stale_lock(self.lock))
                with self.assertRaisesRegex(ValueError, "tag tag is locked; confirm its writer stopped before removing"):
                    with workspace(self.root, "tag"):
                        pass
                self.assertEqual(self.lock.read_text(), content)
