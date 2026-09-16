"""Validate a built original ROM and emit supported Intel initialization files."""
import hashlib
import json
from pathlib import Path
import re
import zlib

from . import generated_interfaces as abi


from .profiles import IMAGE_BYTES, PROFILE_IDS, DIRECT_PROFILE_NAME


def prepare(image, expected_sha256, destination, profile=DIRECT_PROFILE_NAME):
    """The caller supplies the hash recorded by its software build."""
    from sw.package import validate_image

    if profile not in IMAGE_BYTES:
        raise ValueError('preload requires a package profile')
    if not isinstance(image, bytes) or len(image) != IMAGE_BYTES[profile]:
        raise ValueError('preload requires the complete built ROM')
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('preload requires a lowercase SHA256 from the software build')
    digest = hashlib.sha256(image).hexdigest()
    if digest != expected_sha256:
        raise ValueError('preload ROM SHA256 differs from the software build')
    entry = int.from_bytes(image[0x102:0x104], 'little')
    title = image[0x134:0x144].rstrip(b'\0').decode('ascii')
    validate_image(image, entry, title, image[0x14c], profile)
    return emit(image, destination, digest, entry, title, image[0x14c], profile=profile)


def emit(image, destination, digest, entry, title, version, *, fixture=None, profile=DIRECT_PROFILE_NAME):
    """Common encoding after the caller's original or named-fixture validation."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rom = destination / 'preload-rom.mif'
    presence = destination / 'preload-presence.mif'
    crc = destination / 'preload-crc.hex'
    # Both files address the whole ROM store; the image occupies its first
    # PROFILE_ROM_BYTES and the presence bitmap is zero above them.
    store = abi.PROFILE_STORE_BYTES
    rom.write_text(f'DEPTH = {store};\nWIDTH = 8;\nADDRESS_RADIX = HEX;\nDATA_RADIX = HEX;\nCONTENT BEGIN\n'
                   + ''.join(f'{address:04X} : {value:02X};\n' for address, value in enumerate(image))
                   + 'END;\n', encoding='ascii')
    absent = f'[{len(image):04X}..{store - 1:04X}] : 0;\n' if len(image) < store else ''
    presence.write_text(f'DEPTH = {store};\nWIDTH = 1;\nADDRESS_RADIX = HEX;\nDATA_RADIX = BIN;\n'
                        f'CONTENT BEGIN\n[0000..{len(image) - 1:04X}] : 1;\n{absent}END;\n', encoding='ascii')
    crc.write_text(f'{zlib.crc32(image):08x}\n', encoding='ascii')
    record = {'schema_version': 1, 'mode': 'preloaded-execution', 'profile': profile,
              'profile_id': PROFILE_IDS[profile],
              'image_sha256': digest, 'image_bytes': len(image),
              'image_crc32': zlib.crc32(image), 'entry': entry,
              'title': title, 'version': version,
              'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (rom, presence, crc)}}
    if fixture is not None:
        record['fixture'] = fixture
    (destination / 'preload.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record


def verify(destination):
    """Recheck generated inputs immediately before simulator launch."""
    destination = Path(destination)
    record = json.loads((destination / 'preload.json').read_text(encoding='utf-8'))
    if record.get('mode') != 'preloaded-execution' or record.get('schema_version') != 1:
        raise ValueError('invalid preload manifest')
    image = (destination / 'program.gb').read_bytes()
    profile = record.get('profile', DIRECT_PROFILE_NAME)
    if profile not in IMAGE_BYTES or record.get('profile_id', abi.PROFILE_DIRECT_ID) != PROFILE_IDS[profile]:
        raise ValueError('preload manifest names an unknown profile')
    if len(image) != IMAGE_BYTES[profile] or hashlib.sha256(image).hexdigest() != record.get('image_sha256'):
        raise ValueError('preload image changed after preparation')
    if 'fixture' in record:
        from .mooneye import validate_image, selections
        root = Path(__file__).resolve().parents[2]
        if record['fixture'] not in selections(root):
            raise ValueError('unknown preload fixture')
        build = json.loads((destination / 'mooneye-build.json').read_text())
        validate_image(root, image,
                       (destination / 'program.sym').read_text(),
                       backend=build['host_tools'].get('backend', 'windows'), fixture=record['fixture'])
    required = {'preload-rom.mif', 'preload-presence.mif', 'preload-crc.hex'}
    if set(record.get('files', {})) != required:
        raise ValueError('incomplete preload files')
    for name, digest in record['files'].items():
        if hashlib.sha256((destination / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'preload file changed after preparation: {name}')
    return record


def adopt(client, record):
    """Real commands establish metadata; no transport or owner state is set."""
    from .interface_codec import pack_record

    client.request('LOAD_BEGIN', pack_record('load_begin', {
        'profile': record.get('profile_id', abi.PROFILE_DIRECT_ID), 'size': record['image_bytes'],
        'crc32': record['image_crc32']}))
    client.request('LOAD_END')
    return {'mode': 'preloaded-execution', 'image_sha256': record['image_sha256'],
            'crc_scanned_bytes': record['image_bytes'],
            'initial_state': observe_initial(client, record.get('profile_id', abi.PROFILE_DIRECT_ID))}


def observe_initial(client, profile_id=abi.PROFILE_DIRECT_ID):
    """The same public expectation applies after either loading mode; PROFILE is the session's profile."""
    fields = {'STATE': abi.STATE_PAUSED, 'IMAGE_VALID': 1,
              'PROFILE': profile_id, 'DOT_LO': 0, 'DOT_HI': 0,
              'RETIRE_LO': 0, 'RETIRE_HI': 0, 'INPUT': 0,
              'INPUT_SOURCE': abi.INPUT_SOURCE_UART, 'INPUT_EFFECTIVE': 0,
              'SNAPSHOT_VALID': 0}
    observed = {name: client.read_host(getattr(abi, 'HOST_REG_' + name)) for name in fields}
    if observed != fields:
        raise ValueError(f'preload initial public state mismatch: {observed}')
    return observed
