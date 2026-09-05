"""Exclusive controller journal and immutable canonical evidence utilities."""
from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
from .model import canonical, digest, require


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def beneath(root, path):
    require(isinstance(path, str) and not Path(path).is_absolute(), 'relative artifact path')
    result = root / path
    require(result.resolve().is_relative_to(root.resolve()) and not result.is_symlink(),
            'artifact escapes workspace')
    return result


def inventory(root):
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'symlink in evidence')
        if path.is_file():
            require(path.resolve().is_relative_to(root.resolve()), 'evidence escapes workspace')
            result[path.relative_to(root).as_posix()] = file_hash(path)
    require(bool(result), 'empty evidence inventory')
    return result


def freeze(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical(value)
    with path.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    return hashlib.sha256(raw).hexdigest()


@contextmanager
def machine_lock(repository_id):
    """A fixed machine namespace, independent of checkout and remote fields."""
    if os.name == 'nt':
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateMutexW(None, False, f'Global\\nand2mario-trusted-ci-{repository_id}')
        require(bool(handle), 'machine mutex unavailable')
        owned = False
        try:
            owned = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
            require(owned, 'trusted controller already running')
            yield
        finally:
            if owned:
                kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)
    else:
        import fcntl
        path = Path('/tmp') / f'nand2mario-trusted-ci-{repository_id}.lock'
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ValueError('trusted controller already running') from error
            yield
        finally:
            os.close(descriptor)


def consume(state, cfg, req, invocation):
    key = digest({'repository_id': cfg['repository_id'], **req})
    path = state / 'consumed' / (key + '.json')
    try:
        freeze(path, {'request': req, 'invocation': invocation, 'state': 'consumed'})
    except FileExistsError as error:
        raise ValueError('attempt already consumed; require a new remote attempt') from error
    return path


def machine_state(repository_id):
    """Provisioned by activation, never selected by a checkout or remote input."""
    if os.name == 'nt':
        buffer = ctypes.create_unicode_buffer(260)
        result = ctypes.windll.shell32.SHGetFolderPathW(None, 35, None, 0, buffer)
        require(result == 0 and bool(buffer.value), 'machine application-data directory unavailable')
        base = Path(buffer.value)
    else:
        base = Path('/var/lib')
    state = base / 'nand2mario/workdir/trusted-ci' / str(repository_id)
    require(state.is_dir() and not state.is_symlink(),
            'machine journal is unprovisioned; activation belongs to #32')
    return state
