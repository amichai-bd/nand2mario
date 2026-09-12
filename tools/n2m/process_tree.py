"""Launch a tool as an owned process tree that timeout cleanup can reap whole.

`taskkill /T` walks a snapshot of the process table, so a descendant created
while taskkill is starting escapes the kill while the caller still records a
complete cleanup. A Windows job object has no such window: the child starts
suspended, joins the job before its first instruction, and every descendant
inherits membership as it is created. `TerminateJobObject` then stops all of
them at once, and the job's active-process count proves when they are gone.
Closing the job also kills the tree, so a killed builder cannot leak Quartus.
POSIX keeps a session group and `killpg`, which has the same atomicity.
"""
import ctypes
import os
import signal
import subprocess
import time

CREATE_SUSPENDED = 0x4
THREAD_SUSPEND_RESUME = 0x2
TH32CS_SNAPTHREAD = 0x4
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_EXTENDED_LIMIT = 9
JOB_OBJECT_BASIC_ACCOUNTING = 1
JOB_OBJECT_BASIC_PROCESS_ID_LIST = 3
ERROR_MORE_DATA = 234

if os.name == "nt":
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                     "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class BASIC_ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    def process_id_list(capacity):
        class PROCESS_ID_LIST(ctypes.Structure):
            _fields_ = [("NumberOfAssignedProcesses", wintypes.DWORD), ("NumberOfProcessIdsInList", wintypes.DWORD),
                        ("ProcessIdList", ctypes.c_size_t * capacity)]
        return PROCESS_ID_LIST()

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ThreadID", wintypes.DWORD),
                    ("th32OwnerProcessID", wintypes.DWORD), ("tpBasePri", wintypes.LONG),
                    ("tpDeltaPri", wintypes.LONG), ("dwFlags", wintypes.DWORD)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD,
                                                 wintypes.LPDWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Thread32First.argtypes = kernel.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(THREADENTRY32)]
    kernel.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenThread.restype = wintypes.HANDLE
    kernel.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel.ResumeThread.restype = wintypes.DWORD


def _checked(result, what):
    if not result:
        raise OSError(ctypes.get_last_error(), f"{what} failed")
    return result


def _resume(pid):
    """Resume the suspended initial thread of a process launched with CREATE_SUSPENDED."""
    snapshot = _checked(kernel.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0), "thread snapshot")
    try:
        entry = THREADENTRY32(dwSize=ctypes.sizeof(THREADENTRY32))
        resumed = 0
        found = kernel.Thread32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.th32OwnerProcessID == pid:
                thread = _checked(kernel.OpenThread(THREAD_SUSPEND_RESUME, False, entry.th32ThreadID), "OpenThread")
                try:
                    if kernel.ResumeThread(thread) != 0xFFFFFFFF:
                        resumed += 1
                finally:
                    kernel.CloseHandle(thread)
            found = kernel.Thread32Next(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    if not resumed:
        raise OSError("no thread of the launched process could be resumed")


class Tree:
    """One launched process plus every descendant, terminated as a unit."""

    def __init__(self, argv, **options):
        self.job = None
        if os.name == "nt":
            self.job = _checked(kernel.CreateJobObjectW(None, None), "CreateJobObject")
            try:
                self._launch(argv, options)
            except BaseException:
                self.close()
                raise
        else:
            self.process = subprocess.Popen(argv, start_new_session=True, **options)

    def _launch(self, argv, options):
        limits = EXTENDED_LIMIT()
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        _checked(kernel.SetInformationJobObject(self.job, JOB_OBJECT_EXTENDED_LIMIT, ctypes.byref(limits),
                                                ctypes.sizeof(limits)), "SetInformationJobObject")
        flags = options.pop("creationflags", 0) | CREATE_SUSPENDED
        self.process = subprocess.Popen(argv, creationflags=flags, **options)
        try:
            _checked(kernel.AssignProcessToJobObject(self.job, int(self.process._handle)),
                     "AssignProcessToJobObject")
            _resume(self.process.pid)
        except OSError:
            self.process.kill()
            self.process.wait(timeout=5)
            raise

    def active(self):
        """Processes still alive in the job; None where jobs do not exist."""
        if self.job is None:
            return None
        accounting = BASIC_ACCOUNTING()
        _checked(kernel.QueryInformationJobObject(self.job, JOB_OBJECT_BASIC_ACCOUNTING, ctypes.byref(accounting),
                                                  ctypes.sizeof(accounting), None), "QueryInformationJobObject")
        return accounting.ActiveProcesses

    def survivors(self):
        """Pids of members still in the job, for naming what cleanup left; None without jobs."""
        if self.job is None:
            return None
        capacity = 64
        while True:
            members = process_id_list(capacity)
            if kernel.QueryInformationJobObject(self.job, JOB_OBJECT_BASIC_PROCESS_ID_LIST, ctypes.byref(members),
                                                ctypes.sizeof(members), None):
                return [int(pid) for pid in members.ProcessIdList[:members.NumberOfProcessIdsInList]]
            if ctypes.get_last_error() != ERROR_MORE_DATA:
                raise OSError(ctypes.get_last_error(), "QueryInformationJobObject failed")
            capacity *= 4

    def terminate(self, timeout):
        """Kill the whole tree and return once no member is alive, or raise."""
        if self.job is None:
            os.killpg(self.process.pid, signal.SIGKILL)
            return
        _checked(kernel.TerminateJobObject(self.job, 1), "TerminateJobObject")
        deadline = time.monotonic() + timeout
        while self.active():
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.process.args, timeout)
            time.sleep(0.01)

    def close(self):
        if self.job is not None:
            kernel.CloseHandle(self.job)
            self.job = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
