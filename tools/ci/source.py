"""Verify checkout contents against authorized Git objects, not index shortcuts."""
from pathlib import Path
import subprocess
from .model import require
from .storage import file_hash


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def verify_sources(root, sha):
    require(git(root, 'rev-parse', 'HEAD') == sha, 'checkout source SHA')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'checkout is not clean')
    flags = git(root, 'ls-files', '-v', '-z').split('\0')
    require(all(item.startswith('H ') for item in flags if item), 'hidden index flags are unsupported')
    tree = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', '--full-tree', sha])
    entries = []
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode('ascii').split()
        require(mode in ('100644', '100755') and kind == 'blob', 'non-file controller source')
        entries.append((name.decode('utf-8'), blob))
    require({item[2:] for item in flags if item} == {name for name, _ in entries}, 'index/commit file inventory')
    batch = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'],
                           input=('\n'.join(blob for _, blob in entries) + '\n').encode('ascii'),
                           capture_output=True, check=True).stdout
    offset = 0
    hashes = {}
    for name, expected_blob in entries:
        end = batch.index(b'\n', offset)
        blob, kind, size = batch[offset:end].decode('ascii').split()
        require(blob == expected_blob and kind == 'blob', 'authorized Git blob identity')
        start = end + 1; offset = start + int(size) + 1
        expected = batch[start:offset - 1]
        path = root / name
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'source path boundary')
        actual = path.read_bytes()
        require(actual == expected or (b'\0' not in expected and actual.replace(b'\r\n', b'\n') == expected),
                'source bytes differ from authorized Git blob: ' + name)
        hashes[name] = file_hash(path)
    require(offset == len(batch), 'complete Git blob stream')
    return hashes
