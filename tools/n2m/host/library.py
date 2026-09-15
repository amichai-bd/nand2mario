"""The sixteen-slot SDRAM game library: slots, menu image, catalogue and verification.

Layout owner: wiki/src/rtl/storage/MAS_sdram.md#address-space-layout. Slot i
is one complete 32 KiB image at i * 32 KiB; index 16 is the menu image; the
catalogue is 17 entries of 32 bytes at 0x88000, little-endian, and the
remainder of its 1 KiB is zero. The copy engine compares CRC-32/ISO-HDLC over
the 32 KiB image with the catalogue crc32, so the host verifies the same
quantity after writing.
"""
import struct
import zlib

from .. import generated_interfaces as abi
from ..interface_codec import SDRAM_LINE

# Layout constants named by the storage contract. They move to the generated
# interface table when cfg/interfaces.json gains the library group.
SLOT_BYTES = abi.PROFILE_ROM_BYTES
GAME_SLOTS = 16
MENU_INDEX = 16
IMAGE_COUNT = 17
CATALOGUE_ADDRESS = 0x88000
ENTRY_BYTES = 32
CATALOGUE_BYTES = 1024
TITLE_START, TITLE_BYTES = 0x134, 16
ENTRY = struct.Struct('<BBHI16s8x')
VALID, EMPTY = 0x01, 0x00

# Package profile name to the generated profile ID the image runs in. The
# packager admits only these profiles, so the catalogue never carries an
# unknown ID.
PROFILE_IDS = {abi.PROFILE_NAME: abi.PROFILE_DIRECT_ID}


def slot_name(index):
    return 'menu' if index == MENU_INDEX else f'slot {index}'


def slot_address(index):
    if type(index) is not int or not 0 <= index < IMAGE_COUNT:
        raise ValueError('library index must be 0..16')
    return index * SLOT_BYTES


def profile_id(name):
    if name not in PROFILE_IDS:
        raise ValueError(f'library refuses images of profile {name!r}')
    return PROFILE_IDS[name]


def image_entry(image, profile):
    """The catalogue entry describing one 32 KiB image."""
    image = bytes(image)
    if len(image) != SLOT_BYTES:
        raise ValueError('library image must be exactly one 32 KiB slot')
    return {'valid': VALID, 'profile': profile, 'length': SLOT_BYTES, 'crc32': zlib.crc32(image),
            'title': image[TITLE_START:TITLE_START + TITLE_BYTES]}


EMPTY_ENTRY = {'valid': EMPTY, 'profile': 0, 'length': 0, 'crc32': 0, 'title': bytes(TITLE_BYTES)}


def pack_entry(entry):
    return ENTRY.pack(entry['valid'], entry['profile'], entry['length'], entry['crc32'], entry['title'])


def unpack_entry(raw):
    if len(raw) != ENTRY_BYTES:
        raise ValueError('catalogue entry must be 32 bytes')
    valid, profile, length, crc32, title = ENTRY.unpack(raw)
    return {'valid': valid, 'profile': profile, 'length': length, 'crc32': crc32, 'title': title,
            'reserved_zero': raw[24:] == bytes(8)}


def build_catalogue(entries):
    """1 KiB catalogue bytes from {index: entry}; every other index is empty."""
    table = b''.join(pack_entry(entries.get(index, EMPTY_ENTRY)) for index in range(IMAGE_COUNT))
    return table + bytes(CATALOGUE_BYTES - len(table))


def parse_catalogue(raw):
    if len(raw) != CATALOGUE_BYTES:
        raise ValueError('catalogue must be 1 KiB')
    return [unpack_entry(raw[index * ENTRY_BYTES:(index + 1) * ENTRY_BYTES]) for index in range(IMAGE_COUNT)]


def title_text(title):
    return title.rstrip(b'\0').decode('ascii', 'replace')


def describe(index, entry):
    """One printable/JSON row of the catalogue as stored."""
    return {'index': index, 'name': slot_name(index), 'valid': entry['valid'], 'profile': entry['profile'],
            'length': entry['length'], 'crc32': f"{entry['crc32']:08x}", 'title': title_text(entry['title'])}


def write_region(client, address, data, notify, name):
    lines = len(data) // SDRAM_LINE
    notify({'stage': 'write', 'name': name, 'completed': 0, 'total': lines})
    for index in range(lines):
        client.sdram_write(address + index * SDRAM_LINE, data[index * SDRAM_LINE:(index + 1) * SDRAM_LINE])
        if index % 256 == 255 or index == lines - 1:
            notify({'stage': 'write', 'name': name, 'completed': index + 1, 'total': lines})


def read_region(client, address, size, notify, name):
    lines = size // SDRAM_LINE
    result = bytearray()
    notify({'stage': 'read', 'name': name, 'completed': 0, 'total': lines})
    for index in range(0, lines, abi.SDRAM_READ_MAX_LINES):
        count = min(abi.SDRAM_READ_MAX_LINES, lines - index)
        result.extend(client.sdram_read(address + index * SDRAM_LINE, count))
        done = index + count
        if done % (abi.SDRAM_READ_MAX_LINES * 32) < abi.SDRAM_READ_MAX_LINES or done == lines:
            notify({'stage': 'read', 'name': name, 'completed': done, 'total': lines})
    return bytes(result)


def read_catalogue(client, *, progress=None):
    """The catalogue as stored, parsed into 17 rows."""
    raw = read_region(client, CATALOGUE_ADDRESS, CATALOGUE_BYTES, progress or (lambda _e: None), 'catalogue')
    return raw, [describe(index, entry) for index, entry in enumerate(parse_catalogue(raw))]


def compare(expected, actual):
    """PASS/FAIL with the first differing offset; bytes stay out of the record."""
    if actual == expected:
        return {'status': 'PASS', 'first_mismatch': None}
    offset = next(i for i, (want, got) in enumerate(zip(expected, actual)) if want != got)
    return {'status': 'FAIL', 'first_mismatch': offset}


def load_library(client, images, menu=None, *, progress=None):
    """Write every image, the menu and the catalogue, then read all back and verify.

    ``images`` is a list of (image, profile_name) for slots 0..N-1, at most
    16; ``menu`` is one (image, profile_name) for index 16 or None. Every
    write completes before the first read so an aliased slot cannot pass.
    Returns the library table with a per-slot verdict; the caller decides the
    exit status from ``mismatch_count``.
    """
    if not 1 <= len(images) <= GAME_SLOTS:
        raise ValueError(f'library load takes 1..{GAME_SLOTS} images')
    notify = progress or (lambda _event: None)
    planned = {index: (bytes(image), image_entry(image, profile_id(profile)))
               for index, (image, profile) in enumerate(images)}
    if menu is not None:
        planned[MENU_INDEX] = (bytes(menu[0]), image_entry(menu[0], profile_id(menu[1])))
    catalogue = build_catalogue({index: entry for index, (_image, entry) in planned.items()})
    for index, (image, _entry) in planned.items():
        write_region(client, slot_address(index), image, notify, slot_name(index))
    write_region(client, CATALOGUE_ADDRESS, catalogue, notify, 'catalogue')
    slots = []
    mismatches = []
    for index, (image, entry) in planned.items():
        actual = read_region(client, slot_address(index), SLOT_BYTES, notify, slot_name(index))
        row = describe(index, entry)
        row.update(compare(image, actual), readback_crc32=f'{zlib.crc32(actual):08x}')
        row['crc32_match'] = row['readback_crc32'] == row['crc32']
        if row['status'] != 'PASS' or not row['crc32_match']:
            row['status'] = 'FAIL'
            mismatches.append(f"{row['name']} ({row['title']})")
        slots.append(row)
    stored = read_region(client, CATALOGUE_ADDRESS, CATALOGUE_BYTES, notify, 'catalogue')
    table = {'address': CATALOGUE_ADDRESS, 'bytes': CATALOGUE_BYTES, **compare(catalogue, stored)}
    if table['status'] != 'PASS':
        mismatches.append('catalogue')
    return {'slots': slots, 'catalogue': table, 'images': len(planned), 'mismatches': mismatches,
            'mismatch_count': len(mismatches), 'status': 'PASS' if not mismatches else 'FAIL'}


def decode_library_status(word):
    """The LIBRARY_STATUS fields the loader profile's host interaction rule names."""
    return {'word': word, 'a000': word & 0xFF, 'a002': (word >> 8) & 0xFF,
            'a003': (word >> 16) & 0xFF, 'bank': (word >> 24) & 0x3F}


def format_table(rows, verified=False):
    """Fixed-column text of the library table."""
    header = ['index', 'name', 'valid', 'profile', 'length', 'crc32', 'title']
    if verified:
        header += ['readback', 'status']
    lines = [header]
    for row in rows:
        cells = [row['index'], row['name'], row['valid'], row['profile'], row['length'], row['crc32'], row['title']]
        if verified:
            cells += [row['readback_crc32'], row['status']]
        lines.append([str(cell) for cell in cells])
    widths = [max(len(line[column]) for line in lines) for column in range(len(header))]
    return '\n'.join('  '.join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip() for line in lines)
