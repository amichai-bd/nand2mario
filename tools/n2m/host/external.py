"""Pinned freely licensed external images, fetched at run time and never committed."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import urllib.request

from .. import generated_interfaces as abi

PIN_FILE = 'tools/n2m/dependencies.json'
# Ignored private location required by the source and provenance policy.
CACHE = 'workdir/private/external-roms'
FIELDS = ('url', 'sha256', 'size', 'license')


def verify(data, pin, name):
    """Size first, then hash. A mismatch refuses the bytes; it never truncates."""
    if len(data) != pin['size']:
        raise ValueError(f'external image size mismatch: {name}: read {len(data)}, pinned {pin["size"]}')
    if hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError(f'external image hash mismatch: {name}')
    return data


def fetch(pin, path, name):
    """Verify before writing the cache and again after reading it back."""
    if not str(pin['url']).startswith('https://'):
        raise ValueError(f'external pin must use an https source URL: {name}')
    if not path.exists():
        with urllib.request.urlopen(pin['url'], timeout=60) as response:
            # A redirect may downgrade the pinned https URL; the final response must stay https.
            if not str(response.url).startswith('https://'):
                raise ValueError(f'external download was redirected off https: {name}')
            data = response.read(pin['size'] + 1)
        verify(data, pin, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Replace in one step so an interrupted write never leaves a truncated cache behind.
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.', suffix='.part')
        try:
            with os.fdopen(handle, 'wb') as opened:
                opened.write(data)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'external cache is not a regular file: {name}')
    return verify(path.read_bytes(), pin, name)


def read_external(root, name, pin_file=None):
    """Return a verified pinned image and its public provenance record."""
    root = Path(root).resolve()
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,63}', name or ''):
        raise ValueError('external pin name must be lowercase letters, digits and hyphens')
    path = Path(pin_file or PIN_FILE)
    path = path if path.is_absolute() else root / path
    images = json.loads(path.read_text(encoding='utf-8')).get('external_roms', {}).get('images', {})
    if name not in images:
        raise ValueError(f'unknown external image pin: {name}')
    pin = images[name]
    missing = [field for field in FIELDS if field not in pin]
    if missing:
        raise ValueError(f'external pin is missing {", ".join(missing)}: {name}')
    if pin['size'] != abi.PROFILE_ROM_BYTES:
        raise ValueError(f'pinned size differs from the generated direct-profile image size: {name}')
    cache = root / CACHE / name
    image = fetch(pin, cache / 'image.gb', name)
    for notice, item in pin.get('notices', {}).items():
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,63}', notice):
            raise ValueError(f'external notice name is not a plain file name: {name}')
        fetch(item, cache / 'notices' / notice, name + '/' + notice)
    return image, {'pin': name, **{field: pin[field] for field in FIELDS},
                   'notices': sorted(pin.get('notices', {}))}
