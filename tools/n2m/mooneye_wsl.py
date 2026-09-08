"""Explicit WSL host identity and argument conversion for the locked fixture."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def timeout_seconds(limit):
    deadline = os.environ.get('N2M_TEST_EXECUTION_DEADLINE')
    # Let GNU timeout kill its Linux group before the Windows supervisor expires.
    seconds = min(limit, float(deadline) - time.time() - 5) if deadline else limit
    if seconds < 1:
        raise ValueError('MOONEYE_WSL_BUILD_DEADLINE')
    return str(int(seconds))


def linux_path(path):
    return subprocess.check_output(['wsl.exe', '--exec', 'wslpath', '-a', '-u', str(path)],
                                   text=True, timeout=10).strip()


def snapshot():
    """Hash compiler inputs, build modules, link libraries and executable tools."""
    tools = {name: shutil.which(name) for name in ('gcc', 'ar', 'as', 'ld', 'cmake', 'make', 'sh', 'python3', 'timeout')}
    if not all(tools.values()):
        raise ValueError('MOONEYE_WSL_MISSING_TOOL')
    roots = [Path('/usr/include'), Path('/usr/lib/gcc'), Path('/usr/lib/x86_64-linux-gnu')]
    roots += sorted(Path('/usr/share').glob('cmake-*'))
    files = {str(Path(path).resolve()): hashlib.sha256(Path(path).read_bytes()).hexdigest()
             for path in tools.values()}
    trees = {}
    for root in roots:
        digest = hashlib.sha256()
        count = 0
        for path in sorted(root.rglob('*')):
            if path.is_file():
                digest.update(str(path.relative_to(root)).encode() + b'\0')
                digest.update(hashlib.sha256(path.read_bytes()).digest())
                count += 1
        trees[str(root)] = {'sha256': digest.hexdigest(), 'files': count}
    versions = {name: subprocess.check_output([tools[name], '--version'], text=True).splitlines()[0]
                for name in ('gcc', 'ar', 'ld', 'cmake', 'make', 'python3', 'timeout')}
    return {'backend': 'wsl', 'tools': tools, 'files': files, 'trees': trees, 'versions': versions}


def identity():
    helper = linux_path(Path(__file__).resolve())
    return json.loads(subprocess.check_output(['wsl.exe', '--exec', 'timeout', '--kill-after=2', timeout_seconds(60),
                                               'python3', helper], text=True, timeout=65))


def identity_hash(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()


def command(argv, cwd):
    converted = [linux_path(value) if isinstance(value, Path) else str(value) for value in argv]
    return ['wsl.exe', '--cd', linux_path(cwd), '--exec', 'timeout', '--kill-after=2', timeout_seconds(110), *converted]


if __name__ == '__main__':
    if os.name != 'posix':
        raise SystemExit('Run identity collection inside WSL')
    print(json.dumps(snapshot(), sort_keys=True))
