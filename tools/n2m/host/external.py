"""Pinned freely licensed external images, fetched at run time and never committed."""
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

from .. import generated_interfaces as abi
from ..records import atomic_bytes, published_bytes
from ..profiles import PROFILE_IDS, IMAGE_BYTES, DIRECT_PROFILE_NAME, MBC1_PROFILE_NAME

PIN_FILE = 'tools/n2m/dependencies.json'
# Ignored private location required by the source and provenance policy. The cache
# lives outside the checkout so every worktree on a host reads the same verified
# bytes; CACHE remains the per-checkout location earlier runs filled.
CACHE = 'workdir/private/external-roms'
CACHE_VARIABLE = 'N2M_EXTERNAL_ROM_CACHE'
CACHE_FOLDER = ('nand2mario', 'external-roms')
SEED_COMMAND = 'python tools/build.py sw library --tag <tag>'
WINDOWS = os.name == 'nt'
FIELDS = ('url', 'sha256', 'size', 'license')
# Package profile name a pin runs in; absent means the 32 KiB direct profile.
# The loader profile is the menu's own image and never a pin.
PROFILE_NAMES = {name: (PROFILE_IDS[name], IMAGE_BYTES[name]) for name in (DIRECT_PROFILE_NAME, MBC1_PROFILE_NAME)}
# A pinned display title stands in for an all-zero header title: the menu
# font's own alphabet, so the catalogue never carries a byte it cannot draw.
TITLE = re.compile('[A-Z0-9][A-Z0-9 -]{0,15}')


def cache_root(root, environment=None):
    """Where this host keeps the verified pinned images, outside any checkout.

    ``N2M_EXTERNAL_ROM_CACHE`` wins when it names a path; otherwise the per-user
    default under the platform cache folder. A relative variable is resolved
    against the checkout so a caller cannot land the cache on an unknown path.
    """
    environment = os.environ if environment is None else environment
    override = (environment.get(CACHE_VARIABLE) or '').strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else Path(root).resolve() / path
    base = (environment.get('XDG_CACHE_HOME') or '').strip()
    if not base and WINDOWS:
        base = (environment.get('LOCALAPPDATA') or '').strip()
    base = Path(base).expanduser() if base else Path(environment.get('HOME') or Path.home()).expanduser() / '.cache'
    return base.joinpath(*CACHE_FOLDER)


def adopt(path, legacy, pin, name):
    """Publish a verified per-checkout image into the shared cache.

    An earlier per-checkout run keeps its value: the legacy bytes are verified
    against the pin exactly like a download before they are shared, and a
    mismatch is left alone for the caller to fetch or refuse.
    """
    if path.exists() or legacy is None or legacy.is_symlink() or not legacy.is_file():
        return False
    try:
        data = verify(published_bytes(legacy), pin, name)
    except (ValueError, OSError):
        return False
    atomic_bytes(path, data)
    return True


def fallback_title(pin, name):
    """The pin's `title` as catalogue bytes, or None when the pin has none."""
    if 'title' not in pin:
        return None
    title = pin['title']
    if not isinstance(title, str) or not TITLE.fullmatch(title):
        raise ValueError(f'external pin title must be 1-16 upper-case letters, digits, spaces or dashes: {name}')
    return title.encode('ascii')


def verify(data, pin, name):
    """Size first, then hash. A mismatch refuses the bytes; it never truncates."""
    if len(data) != pin['size']:
        raise ValueError(f'external image size mismatch: {name}: read {len(data)}, pinned {pin["size"]}')
    if hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError(f'external image hash mismatch: {name}')
    return data


def fetch(pin, path, name, offline=False, legacy=None, cache=None):
    """Verify before writing the cache and again after reading it back.

    ``offline`` never opens the network: a missing cache is refused by name so
    an FPGA build cannot stall on a download. ``legacy`` is the per-checkout
    path an earlier run may have filled; its bytes are adopted once verified.
    ``cache`` is the shared cache root the missing-image message names.
    """
    if not str(pin['url']).startswith('https://'):
        raise ValueError(f'external pin must use an https source URL: {name}')
    adopt(path, legacy, pin, name)
    if not path.exists():
        if offline:
            raise ValueError(f'external image is not cached: {name}; run `{SEED_COMMAND}` online once on this '
                             f'host to seed {cache}, or set {CACHE_VARIABLE} to a seeded cache')
        with urllib.request.urlopen(pin['url'], timeout=60) as response:
            # A redirect may downgrade the pinned https URL; the final response must stay https.
            if not str(response.url).startswith('https://'):
                raise ValueError(f'external download was redirected off https: {name}')
            data = response.read(pin['size'] + 1)
        verify(data, pin, name)
        # Replace in one step so an interrupted write never leaves a truncated cache
        # behind, retrying the Windows denials a concurrent reader causes.
        atomic_bytes(path, data)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f'external cache is not a regular file: {name}')
    # A concurrent publication leaves the cache briefly unopenable on Windows.
    return verify(published_bytes(path), pin, name)


def read_external(root, name, pin_file=None, offline=False):
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
    profile = pin.get('profile', DIRECT_PROFILE_NAME)
    if profile not in PROFILE_NAMES:
        raise ValueError(f'external pin names an unknown profile: {name}')
    profile_id, image_bytes = PROFILE_NAMES[profile]
    if pin['size'] != image_bytes:
        raise ValueError(f'pinned size differs from the generated image size of profile {profile}: {name}')
    shared = cache_root(root)
    cache = shared / name
    legacy = root / CACHE / name
    image = fetch(pin, cache / 'image.gb', name, offline, legacy / 'image.gb', shared)
    for notice, item in pin.get('notices', {}).items():
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,63}', notice):
            raise ValueError(f'external notice name is not a plain file name: {name}')
        fetch(item, cache / 'notices' / notice, name + '/' + notice, offline, legacy / 'notices' / notice, shared)
    return image, {'pin': name, **{field: pin[field] for field in FIELDS}, 'profile': profile, 'profile_id': profile_id,
                   'title': fallback_title(pin, name), 'notices': sorted(pin.get('notices', {}))}
