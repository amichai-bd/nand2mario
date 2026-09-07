"""Validate a built original ROM and emit supported Intel initialization files."""
import hashlib
import json
from pathlib import Path
import re
import zlib

from . import generated_interfaces as abi


def prepare(image, expected_sha256, destination):
    """The caller supplies the hash recorded by its software build."""
    from sw.package import validate_image

    if not isinstance(image, bytes) or len(image) != abi.PROFILE_ROM_BYTES:
        raise ValueError('preload requires the complete built ROM')
    if not isinstance(expected_sha256, str) or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise ValueError('preload requires a lowercase SHA256 from the software build')
    digest = hashlib.sha256(image).hexdigest()
    if digest != expected_sha256:
        raise ValueError('preload ROM SHA256 differs from the software build')
    entry = int.from_bytes(image[0x102:0x104], 'little')
    title = image[0x134:0x144].rstrip(b'\0').decode('ascii')
    validate_image(image, entry, title, image[0x14c])
    return emit(image, destination, digest, entry, title, image[0x14c])


def emit(image, destination, digest, entry, title, version, *, fixture=None):
    """Common encoding after the caller's original or named-fixture validation."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rom = destination / 'preload-rom.mif'
    presence = destination / 'preload-presence.mif'
    crc = destination / 'preload-crc.hex'
    rom.write_text('DEPTH = 32768;\nWIDTH = 8;\nADDRESS_RADIX = HEX;\nDATA_RADIX = HEX;\nCONTENT BEGIN\n'
                   + ''.join(f'{address:04X} : {value:02X};\n' for address, value in enumerate(image))
                   + 'END;\n', encoding='ascii')
    presence.write_text('DEPTH = 32768;\nWIDTH = 1;\nADDRESS_RADIX = HEX;\nDATA_RADIX = BIN;\n'
                        'CONTENT BEGIN\n[0000..7FFF] : 1;\nEND;\n', encoding='ascii')
    crc.write_text(f'{zlib.crc32(image):08x}\n', encoding='ascii')
    record = {'schema_version': 1, 'mode': 'preloaded-execution',
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
    if len(image) != abi.PROFILE_ROM_BYTES or hashlib.sha256(image).hexdigest() != record.get('image_sha256'):
        raise ValueError('preload image changed after preparation')
    if 'fixture' in record:
        if record['fixture'] != 'mooneye-reg-f':
            raise ValueError('unknown preload fixture')
        from .mooneye import validate_image
        validate_image(Path(__file__).resolve().parents[2], image,
                       (destination / 'program.sym').read_text())
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
        'profile': abi.PROFILE_DIRECT_ID, 'size': record['image_bytes'],
        'crc32': record['image_crc32']}))
    client.request('LOAD_END')
    return {'mode': 'preloaded-execution', 'image_sha256': record['image_sha256'],
            'crc_scanned_bytes': record['image_bytes'], 'initial_state': observe_initial(client)}


def observe_initial(client):
    """The same public expectation applies after either loading mode."""
    fields = {'STATE': abi.STATE_PAUSED, 'IMAGE_VALID': 1,
              'PROFILE': abi.PROFILE_DIRECT_ID, 'DOT_LO': 0, 'DOT_HI': 0,
              'RETIRE_LO': 0, 'RETIRE_HI': 0, 'INPUT': 0,
              'INPUT_SOURCE': abi.INPUT_SOURCE_UART, 'INPUT_EFFECTIVE': 0,
              'SNAPSHOT_VALID': 0}
    observed = {name: client.read_host(getattr(abi, 'HOST_REG_' + name)) for name in fields}
    if observed != fields:
        raise ValueError(f'preload initial public state mismatch: {observed}')
    return observed
