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
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    rom = destination / 'preload-rom.mif'
    presence = destination / 'preload-presence.mif'
    rom.write_text('DEPTH = 32768;\nWIDTH = 8;\nADDRESS_RADIX = HEX;\nDATA_RADIX = HEX;\nCONTENT BEGIN\n'
                   + ''.join(f'{address:04X} : {value:02X};\n' for address, value in enumerate(image))
                   + 'END;\n', encoding='ascii')
    presence.write_text('DEPTH = 32768;\nWIDTH = 1;\nADDRESS_RADIX = HEX;\nDATA_RADIX = BIN;\n'
                        'CONTENT BEGIN\n[0000..7FFF] : 1;\nEND;\n', encoding='ascii')
    record = {'schema_version': 1, 'mode': 'preloaded-execution',
              'image_sha256': digest, 'image_bytes': len(image),
              'image_crc32': zlib.crc32(image), 'entry': entry,
              'title': title, 'version': image[0x14c],
              'files': {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (rom, presence)}}
    (destination / 'preload.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return record
