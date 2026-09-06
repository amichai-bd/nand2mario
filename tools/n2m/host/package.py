"""Read an immutable successful software attempt, never a loose ROM path."""
import json
import hashlib
from pathlib import Path
import re

from .. import generated_interfaces as abi
from ..records import file_hash
from sw.package import validate_image


def read_package(root, manifest):
    root = root.resolve()
    path = Path(manifest)
    path = path if path.is_absolute() else root / path
    path = path.resolve()
    boundary = root / 'workdir/builds'
    if not path.is_relative_to(boundary) or path.name != 'result.json' or path.parent.parent.name != 'runs':
        raise ValueError('select an immutable tagged sw/build attempt result.json')
    if path.parent.parent.parent.parent.name != 'build' or path.parent.parent.parent.parent.parent.name != 'sw':
        raise ValueError('package must come from sw/build')
    if not re.fullmatch('[0-9a-f]{12}', path.parent.name):
        raise ValueError('invalid immutable package attempt')
    manifest_bytes = path.read_bytes()
    record = json.loads(manifest_bytes)
    if record.get('status') != 'PASS' or record.get('attempt') != path.parent.name:
        raise ValueError('package attempt is not successful or has wrong identity')
    if record.get('profile') != abi.PROFILE_NAME:
        raise ValueError('package profile differs from generated direct profile')
    for name in ('cfg/interfaces.json', 'tools/n2m/generated_interfaces.py'):
        if record.get('inputs', {}).get(name) != file_hash(root / name):
            raise ValueError('package interface inputs are stale')
    artifacts = record.get('artifacts')
    rom_name = record.get('rom')
    if not isinstance(artifacts, dict) or rom_name not in artifacts:
        raise ValueError('package has no inventoried ROM')
    image = None
    for name, digest in artifacts.items():
        artifact = root / name
        if artifact.is_symlink() or artifact.resolve().parent != path.parent or not artifact.is_file():
            raise ValueError('package artifact escapes immutable attempt')
        content = artifact.read_bytes()
        if hashlib.sha256(content).hexdigest() != digest:
            raise ValueError('package artifact hash mismatch')
        if name == rom_name:
            image = content
    if len(image) != abi.PROFILE_ROM_BYTES:
        raise ValueError('package has wrong image size')
    # Reuse the packager's strict header/checksum validator without trusting a
    # mutable target registry. The immutable image carries its own title/version.
    title = image[0x134:0x144].rstrip(b'\0').decode('ascii')
    validate_image(image, record['entry'], title, image[0x14c], record['profile'])
    return image, {'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(), 'rom_sha256': artifacts[rom_name],
                   'profile': record['profile'], 'build_commit': record.get('commit'),
                   'build_fingerprint': record.get('fingerprint')}
