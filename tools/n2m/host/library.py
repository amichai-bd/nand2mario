"""The sixteen-slot SDRAM game library: slots, menu image, catalogue and verification.

Layout owner: wiki/src/rtl/storage/MAS_sdram.md#address-space-layout. Slot i
is one complete image at i * SLOT_BYTES; MENU_INDEX is the menu image; the
catalogue is CATALOGUE_ENTRIES records of ENTRY_BYTES at CATALOGUE_ADDRESS,
little-endian, and the remainder of its 1 KiB region is zero. The copy engine
compares CRC-32/ISO-HDLC over the whole image with the catalogue crc32, so the
host verifies the same quantity after writing.
"""
import zlib

from .. import generated_interfaces as abi
from ..profiles import PROFILE_IDS as PACKAGE_PROFILE_IDS, IMAGE_BYTES, LOADER_PROFILE_NAME
from ..interface_codec import SDRAM_LINE, pack_record, unpack_record

# Every number below comes from cfg/interfaces.json through the generated
# table, so the host tool and the RTL share one source.
SLOT_BYTES = abi.LIBRARY_SLOT_BYTES
GAME_SLOTS = abi.LIBRARY_SLOTS
MENU_INDEX = abi.LIBRARY_MENU_INDEX
IMAGE_COUNT = abi.LIBRARY_CATALOGUE_ENTRIES
CATALOGUE_ADDRESS = abi.LIBRARY_CATALOGUE_ADDRESS
ENTRY_BYTES = abi.LIBRARY_ENTRY_BYTES
VALID = abi.LIBRARY_CATALOGUE_VALID
# The catalogue_entry record: valid 0 is an empty slot; the title fields carry
# header bytes 0x0134-0x0143 verbatim, split into two little-endian words.
EMPTY = 0
ENTRY_FIELDS = {field['name']: field['bits'] // 8 for field in abi.RECORDS['catalogue_entry']}
TITLE_START = 0x134
TITLE_BYTES = ENTRY_FIELDS['title_low'] + ENTRY_FIELDS['title_high']
# The layout reserves one 1 KiB region for the catalogue (entries then zero
# bytes). The host writes and compares the whole region so a stale byte behind
# the entries cannot survive a load.
CATALOGUE_BYTES = 1024

# Package profile name to the generated profile ID the image runs in: the
# packager's own table, so the catalogue never carries a name it did not
# build. The menu image names LOADER_PROFILE_NAME and its entry carries
# LOADER_ID; the contract accepts either ID at MENU_INDEX.
# Only the profiles whose image is one slot: the 64 KiB MBC1 profile is refused
# by name until the library carries it (#712).
PROFILE_IDS = {name: value for name, value in PACKAGE_PROFILE_IDS.items() if IMAGE_BYTES[name] == SLOT_BYTES}

# LIBRARY_STATUS word fields and names; layout per the loader profile's host
# interaction rule: $A000 in bits 7:0, $A002 in 15:8, $A003 in 23:16, bank in 29:24.
RESULT_NAMES = {abi.LIBRARY_RESULT_NONE: 'NONE', abi.LIBRARY_RESULT_OK: 'OK',
                abi.LIBRARY_RESULT_INVALID_SLOT: 'INVALID_SLOT', abi.LIBRARY_RESULT_CRC_MISMATCH: 'CRC_MISMATCH',
                abi.LIBRARY_RESULT_NOT_READY: 'NOT_READY'}
STATUS_FLAGS = (('copy_busy', abi.LIBRARY_STATUS_COPY_BUSY), ('window_ready', abi.LIBRARY_STATUS_WINDOW_READY),
                ('sdram_ready', abi.LIBRARY_STATUS_SDRAM_READY), ('key1_pending', abi.LIBRARY_STATUS_KEY1_PENDING),
                ('flash_boot', abi.LIBRARY_STATUS_FLASH_BOOT))


def slot_name(index):
    return 'menu' if index == MENU_INDEX else f'slot {index}'


def slot_address(index):
    if type(index) is not int or not 0 <= index < IMAGE_COUNT:
        raise ValueError(f'library index must be 0..{MENU_INDEX}')
    return index * SLOT_BYTES


def profile_id(name):
    if name not in PROFILE_IDS:
        raise ValueError(f'library refuses images of profile {name!r}')
    return PROFILE_IDS[name]


def image_entry(image, profile, fallback_title=None):
    """The catalogue entry describing one complete slot image.

    The title is header bytes 0x134-0x143 verbatim. Only when every one of them
    is zero does ``fallback_title`` (a pinned display title, at most 16 ASCII
    bytes) stand in; a non-blank header is never overridden. Every catalogue
    writer goes through here, so a flash image and a UART load agree.
    """
    image = bytes(image)
    if len(image) != SLOT_BYTES:
        raise ValueError(f'library image must be exactly one {SLOT_BYTES}-byte slot')
    title = image[TITLE_START:TITLE_START + TITLE_BYTES]
    if fallback_title is not None and not any(title):
        fallback_title = bytes(fallback_title)
        if not 0 < len(fallback_title) <= TITLE_BYTES:
            raise ValueError(f'fallback title must be 1..{TITLE_BYTES} bytes')
        title = fallback_title.ljust(TITLE_BYTES, b'\0')
    return {'valid': VALID, 'profile': profile, 'length': SLOT_BYTES, 'crc32': zlib.crc32(image), 'title': title}


EMPTY_ENTRY = {'valid': EMPTY, 'profile': 0, 'length': 0, 'crc32': 0, 'title': bytes(TITLE_BYTES)}


def pack_entry(entry):
    """One generated catalogue_entry record; the title is padded or cut to its field width."""
    title = bytes(entry['title'])[:TITLE_BYTES].ljust(TITLE_BYTES, b'\0')
    low = ENTRY_FIELDS['title_low']
    return pack_record('catalogue_entry', {
        'valid': entry['valid'], 'profile': entry['profile'], 'length': entry['length'], 'crc32': entry['crc32'],
        'title_low': int.from_bytes(title[:low], 'little'), 'title_high': int.from_bytes(title[low:], 'little'),
        'reserved': 0})


def unpack_entry(raw):
    if len(raw) != ENTRY_BYTES:
        raise ValueError(f'catalogue entry must be {ENTRY_BYTES} bytes')
    fields = unpack_record('catalogue_entry', raw)
    title = (fields['title_low'].to_bytes(ENTRY_FIELDS['title_low'], 'little')
             + fields['title_high'].to_bytes(ENTRY_FIELDS['title_high'], 'little'))
    return {'valid': fields['valid'], 'profile': fields['profile'], 'length': fields['length'],
            'crc32': fields['crc32'], 'title': title, 'reserved_zero': fields['reserved'] == 0}


def build_catalogue(entries):
    """1 KiB catalogue bytes from {index: entry}; every other index is empty."""
    table = b''.join(pack_entry(entries.get(index, EMPTY_ENTRY)) for index in range(IMAGE_COUNT))
    return table + bytes(CATALOGUE_BYTES - len(table))


def parse_catalogue(raw):
    if len(raw) != CATALOGUE_BYTES:
        raise ValueError('catalogue must be 1 KiB')
    return [unpack_entry(raw[index * ENTRY_BYTES:(index + 1) * ENTRY_BYTES]) for index in range(IMAGE_COUNT)]


def title_text(title):
    """Printable ASCII only: control and non-ASCII bytes become '?' so a title cannot steer a terminal."""
    return ''.join(chr(byte) if 0x20 <= byte < 0x7f else '?' for byte in title.rstrip(b'\0'))


def describe(index, entry):
    """One printable/JSON row of the catalogue as stored."""
    return {'index': index, 'name': slot_name(index), 'valid': entry['valid'], 'profile': entry['profile'],
            'length': entry['length'], 'crc32': f"{entry['crc32']:08x}", 'title': title_text(entry['title'])}


def write_region(client, address, data, notify, name):
    client.sdram_write_region(address, data, notify, name=name)


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
    """The catalogue as stored, parsed into one row per entry."""
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
    GAME_SLOTS; ``menu`` is one (image, profile_name) for MENU_INDEX or None. Every
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
    """The LIBRARY_STATUS fields the loader profile's host interaction rule names, with generated names."""
    a000, a002, a003 = word & 0xFF, (word >> 8) & 0xFF, (word >> 16) & 0xFF
    return {'word': word, 'a000': a000, 'a002': a002, 'a003': a003, 'bank': (word >> 24) % abi.LIBRARY_WINDOW_BANKS,
            'flags': [name for name, mask in STATUS_FLAGS if a000 & mask],
            'result': RESULT_NAMES.get(a002, 'UNKNOWN')}


# Endpoint STATE and response status names, from the generated table.
STATE_NAMES = {abi.STATE_PAUSED: 'PAUSED', abi.STATE_RUNNING: 'RUNNING', abi.STATE_LOADING: 'LOADING'}
STATUS_NAMES = {getattr(abi, key): key[len('STATUS_'):] for key in vars(abi) if key.startswith('STATUS_')}
# The menu swap lasts at most 3.2 ms (MAS_loader_profile.md#host-interaction).
# One READ_HOST round trip is about 32 framed bytes each way, about 2.8 ms at
# 115200 baud, so a healthy swap settles within one or two reads; 64 reads
# (over 150 ms) bound `--wait` without a wall clock, which also suits the
# simulation peer whose clock is simulation time.
RETURN_STATUS_READS = 64


def read_endpoint(client):
    """STATE by name with its number, PROFILE and IMAGE_VALID: the host `status` view after a swap."""
    state = client.read_host(abi.HOST_REG_STATE)
    return {'STATE': state, 'state_name': STATE_NAMES.get(state, 'UNKNOWN'),
            'PROFILE': client.read_host(abi.HOST_REG_PROFILE), 'IMAGE_VALID': client.read_host(abi.HOST_REG_IMAGE_VALID)}


def return_to_menu(client, *, wait=False):
    """The host-triggered menu return: WRITE_HOST(LIBRARY_CONTROL) = LIBRARY_CONTROL_RETURN.

    The write behaves exactly like `key1_return` and is accepted in PAUSED and
    RUNNING only, so a LOADING endpoint is refused by name before anything is
    sent; a BAD_STATE reply is reported by name too. LIBRARY_STATUS is read once
    after the write, or with ``wait`` until `copy_busy` and `key1_pending` clear
    within RETURN_STATUS_READS reads. The record carries the decoded status and
    the endpoint STATE/PROFILE/IMAGE_VALID after the return; the caller decides
    what the result code means.
    """
    from .client import RejectedCommand
    before = read_endpoint(client)
    if before['STATE'] != abi.STATE_PAUSED and before['STATE'] != abi.STATE_RUNNING:
        raise ValueError(f"library return refused: endpoint is {before['state_name']}, not PAUSED or RUNNING")
    try:
        control = client.write_host(abi.HOST_REG_LIBRARY_CONTROL, abi.LIBRARY_CONTROL_RETURN)
    except RejectedCommand as error:
        raise ValueError(f'library return rejected by the endpoint: {STATUS_NAMES.get(error.status, error.status)}') from error
    reads = 0
    while True:
        status = decode_library_status(client.read_host(abi.HOST_REG_LIBRARY_STATUS))
        reads += 1
        settled = not ({'copy_busy', 'key1_pending'} & set(status['flags']))
        if settled or not wait or reads >= RETURN_STATUS_READS:
            break
    after = read_endpoint(client)
    result = {'control': control, 'library_status': status, 'endpoint': after, 'before': before,
              'status_reads': reads, 'settled': settled}
    if wait and not settled:
        raise ValueError(f'library return did not settle within {reads} status reads: '
                         f"flags {status['flags']}, result {status['result']}")
    return result


def format_return(result):
    """One text summary of a return record."""
    status = result['library_status']
    flags = ','.join(status['flags']) or '-'
    return (f"library return: result {status['result']} flags {flags} bank {status['bank']}; "
            f"endpoint {result['endpoint']['state_name']} profile {result['endpoint']['PROFILE']} "
            f"image_valid {result['endpoint']['IMAGE_VALID']} after {result['status_reads']} status read(s)")


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
