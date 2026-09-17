"""The sixteen-slot SDRAM game library: slots, menu image, catalogue and verification.

Layout owner: wiki/src/rtl/storage/MAS_sdram.md#address-space-layout. Slot i
starts at i * SLOT_BYTES; a 32 KiB image fills one slot and a 64 KiB MBC1
image fills slots i and i + 1 with one catalogue entry at i and an empty entry
at i + 1. MENU_INDEX is the menu image; the catalogue is CATALOGUE_ENTRIES
records of ENTRY_BYTES at CATALOGUE_ADDRESS, little-endian, followed by
CATALOGUE_ENTRIES tagline records of TAGLINE_BYTES at TAGLINE_ADDRESS, and the
remainder of its 1 KiB region is zero. An entry's length is 24 bits, the 16-bit
``length`` word plus ``length_high``, and equals its profile's image length.
The copy engine compares CRC-32/ISO-HDLC over the whole image with the
catalogue crc32, so the host verifies the same quantity after writing.
"""
import re
import zlib

from .. import generated_interfaces as abi
from ..profiles import PROFILE_IDS as PACKAGE_PROFILE_IDS, PROFILE_IMAGE_BYTES, LOADER_PROFILE_NAME
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
# Exact image length of each profile ID the library carries, from the one
# profile table: the direct and loader images are one slot, the MBC1 image
# two. The copy engine accepts an entry only when its length is this value.
PROFILE_BYTES = dict(PROFILE_IMAGE_BYTES)
# The catalogue_entry record: valid 0 is an empty slot; the title fields carry
# header bytes 0x0134-0x0143 verbatim, split into two little-endian words.
EMPTY = 0
ENTRY_FIELDS = {field['name']: field['bits'] // 8 for field in abi.RECORDS['catalogue_entry']}
LENGTH_LOW_BITS = ENTRY_FIELDS['length'] * 8
TITLE_START = 0x134
TITLE_BYTES = ENTRY_FIELDS['title_low'] + ENTRY_FIELDS['title_high']
# The layout reserves one 1 KiB region for the catalogue (entries, the tagline
# table, then zero bytes). The host writes and compares the whole region so a
# stale byte behind the entries cannot survive a load.
CATALOGUE_BYTES = 1024
# The tagline table lives in the same region, right after the entries, so no
# address outside the catalogue moves and the boot copier already carries it.
# Tagline i is TAGLINE_CHARS characters then zero to TAGLINE_BYTES; an all-zero
# record is no tagline, which is what a catalogue built before taglines holds.
TAGLINE_ADDRESS = abi.LIBRARY_TAGLINE_ADDRESS
TAGLINE_BYTES = abi.LIBRARY_TAGLINE_BYTES
TAGLINE_CHARS = abi.LIBRARY_TAGLINE_CHARS
TAGLINE_OFFSET = TAGLINE_ADDRESS - CATALOGUE_ADDRESS
# What the menu font can draw: A-Z, 0-9, space and dash (menu SPEC, Font). Any
# other byte would draw the dash, so an authored tagline carrying one is
# refused here rather than shipped into the catalogue.
TAGLINE_TEXT = re.compile(f'[A-Z0-9 -]{{1,{TAGLINE_CHARS}}}')

# Package profile name to the generated profile ID the image runs in: the
# packager's own table, so the catalogue never carries a name it did not
# build. The menu image names LOADER_PROFILE_NAME and its entry carries
# LOADER_ID; the contract accepts either ID at MENU_INDEX. Every profile of
# the table is carried: one slot for the 32 KiB profiles, two for MBC1.
PROFILE_IDS = dict(PACKAGE_PROFILE_IDS)

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


def image_slots(length):
    """Slots an image of ``length`` bytes occupies: one per SLOT_BYTES."""
    return -(-length // SLOT_BYTES)


def slot_range(index, length):
    """The slot indices an image of ``length`` bytes at ``index`` fills; it must stay inside the game slots or be the menu."""
    last = index + image_slots(length) - 1
    if index == MENU_INDEX:
        limit = MENU_INDEX
    else:
        limit = GAME_SLOTS - 1
    if last > limit:
        raise ValueError(f'a {length}-byte image at {slot_name(index)} would spill past {slot_name(limit)}')
    return range(index, last + 1)


def profile_id(name):
    if name not in PROFILE_IDS:
        raise ValueError(f'library refuses images of profile {name!r}')
    return PROFILE_IDS[name]


def profile_bytes(profile):
    """The exact image length of a profile ID the library carries."""
    if profile not in PROFILE_BYTES:
        raise ValueError(f'library refuses images of profile ID {profile}')
    return PROFILE_BYTES[profile]


def check_tagline(text, where):
    """One authored tagline as catalogue bytes; anything the menu font cannot draw is refused by name."""
    if not isinstance(text, str) or not TAGLINE_TEXT.fullmatch(text):
        raise ValueError(f'tagline must be 1..{TAGLINE_CHARS} upper-case letters, digits, spaces or dashes: {where}')
    return text.encode('ascii')


def pack_tagline(tagline):
    """One tagline record: its characters, then zero to TAGLINE_BYTES. No tagline is an all-zero record."""
    tagline = bytes(tagline or b'')
    if len(tagline) > TAGLINE_CHARS:
        raise ValueError(f'a tagline is at most {TAGLINE_CHARS} characters')
    return tagline.ljust(TAGLINE_BYTES, b'\0')


def unpack_tagline(raw):
    """The authored characters of one tagline record; an all-zero record reads as no tagline."""
    if len(raw) != TAGLINE_BYTES:
        raise ValueError(f'tagline record must be {TAGLINE_BYTES} bytes')
    return raw[:TAGLINE_CHARS].rstrip(b'\0')


def image_entry(image, profile, fallback_title=None, tagline=None):
    """The catalogue entry describing one complete image of ``profile``.

    The image is exactly its profile's length: one slot for DIRECT_ID and
    LOADER_ID, MBC1_ROM_BYTES (two slots) for MBC1_ID. The title is header bytes 0x134-0x143
    verbatim. Only when every one of them is zero does ``fallback_title`` (a
    pinned display title, at most 16 ASCII bytes) stand in; a non-blank header
    is never overridden. ``tagline`` is the authored tagline bytes, or None for
    no tagline. Every catalogue writer goes through here, so a flash image and
    a UART load agree.
    """
    image = bytes(image)
    expected = profile_bytes(profile)
    if len(image) != expected:
        raise ValueError(f'a profile {profile} library image must be exactly {expected} bytes')
    title = image[TITLE_START:TITLE_START + TITLE_BYTES]
    if fallback_title is not None and not any(title):
        fallback_title = bytes(fallback_title)
        if not 0 < len(fallback_title) <= TITLE_BYTES:
            raise ValueError(f'fallback title must be 1..{TITLE_BYTES} bytes')
        title = fallback_title.ljust(TITLE_BYTES, b'\0')
    return {'valid': VALID, 'profile': profile, 'length': len(image), 'crc32': zlib.crc32(image), 'title': title,
            'tagline': bytes(tagline or b'')}


EMPTY_ENTRY = {'valid': EMPTY, 'profile': 0, 'length': 0, 'crc32': 0, 'title': bytes(TITLE_BYTES), 'tagline': b''}


def pack_entry(entry):
    """One generated catalogue_entry record; the title is padded or cut to its field width.

    The length splits into the 16-bit ``length`` word and ``length_high``
    (bits 23:16), so a 32 KiB entry packs exactly as it always did and a
    64 KiB entry carries 0 and 1.
    """
    title = bytes(entry['title'])[:TITLE_BYTES].ljust(TITLE_BYTES, b'\0')
    low = ENTRY_FIELDS['title_low']
    return pack_record('catalogue_entry', {
        'valid': entry['valid'], 'profile': entry['profile'], 'length': entry['length'] & ((1 << LENGTH_LOW_BITS) - 1),
        'length_high': entry['length'] >> LENGTH_LOW_BITS, 'crc32': entry['crc32'],
        'title_low': int.from_bytes(title[:low], 'little'), 'title_high': int.from_bytes(title[low:], 'little'),
        'reserved': 0})


def unpack_entry(raw):
    if len(raw) != ENTRY_BYTES:
        raise ValueError(f'catalogue entry must be {ENTRY_BYTES} bytes')
    fields = unpack_record('catalogue_entry', raw)
    title = (fields['title_low'].to_bytes(ENTRY_FIELDS['title_low'], 'little')
             + fields['title_high'].to_bytes(ENTRY_FIELDS['title_high'], 'little'))
    return {'valid': fields['valid'], 'profile': fields['profile'],
            'length': fields['length'] | (fields['length_high'] << LENGTH_LOW_BITS),
            'crc32': fields['crc32'], 'title': title, 'reserved_zero': fields['reserved'] == 0}


def build_catalogue(entries):
    """1 KiB catalogue bytes from {index: entry}; every other index is empty.

    The entries come first and the tagline table at TAGLINE_OFFSET; the rest of
    the region stays zero. Entries carrying no tagline therefore pack into the
    same bytes a catalogue built before taglines existed did.
    """
    table = b''.join(pack_entry(entries.get(index, EMPTY_ENTRY)) for index in range(IMAGE_COUNT))
    taglines = b''.join(pack_tagline(entries.get(index, EMPTY_ENTRY).get('tagline')) for index in range(IMAGE_COUNT))
    if len(table) > TAGLINE_OFFSET or TAGLINE_OFFSET + len(taglines) > CATALOGUE_BYTES:
        raise ValueError('the catalogue region does not hold the entries and their taglines')
    region = bytearray(CATALOGUE_BYTES)
    region[:len(table)] = table
    region[TAGLINE_OFFSET:TAGLINE_OFFSET + len(taglines)] = taglines
    return bytes(region)


def parse_catalogue(raw):
    """One row per index: the entry fields and the tagline read from the table behind them."""
    if len(raw) != CATALOGUE_BYTES:
        raise ValueError('catalogue must be 1 KiB')
    rows = []
    for index in range(IMAGE_COUNT):
        row = unpack_entry(raw[index * ENTRY_BYTES:(index + 1) * ENTRY_BYTES])
        start = TAGLINE_OFFSET + index * TAGLINE_BYTES
        row['tagline'] = unpack_tagline(raw[start:start + TAGLINE_BYTES])
        rows.append(row)
    return rows


def title_text(title):
    """Printable ASCII only: control and non-ASCII bytes become '?' so catalogue text cannot steer a terminal."""
    return ''.join(chr(byte) if 0x20 <= byte < 0x7f else '?' for byte in title.rstrip(b'\0'))


def describe(index, entry):
    """One printable/JSON row of the catalogue as stored; an entry with no tagline reports an empty one."""
    return {'index': index, 'name': slot_name(index), 'valid': entry['valid'], 'profile': entry['profile'],
            'length': entry['length'], 'crc32': f"{entry['crc32']:08x}", 'title': title_text(entry['title']),
            'tagline': title_text(entry.get('tagline', b''))}


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


def plan_slots(images):
    """{index: (image, entry)} for images placed in order from slot 0.

    A 32 KiB image takes one slot and a 64 KiB image two adjacent ones, so
    the next image starts after the slots the previous one fills; the images
    must fit the GAME_SLOTS together.
    """
    planned = {}
    index = 0
    for image, profile in images:
        image = bytes(image)
        entry = image_entry(image, profile_id(profile))
        if index >= GAME_SLOTS:
            raise ValueError(f'library load takes at most {GAME_SLOTS} slots; a 64 KiB image takes two')
        planned[index] = (image, entry)
        index = slot_range(index, len(image)).stop
    return planned


def load_library(client, images, menu=None, *, progress=None):
    """Write every image, the menu and the catalogue, then read all back and verify.

    ``images`` is a list of (image, profile_name) placed from slot 0 in order,
    each 32 KiB image in one slot and each 64 KiB image in two, together at
    most GAME_SLOTS; ``menu`` is one (image, profile_name) for MENU_INDEX or
    None. Every write completes before the first read so an aliased slot
    cannot pass. Returns the library table with a per-slot verdict; the caller
    decides the exit status from ``mismatch_count``.
    """
    if not 1 <= len(images) <= GAME_SLOTS:
        raise ValueError(f'library load takes 1..{GAME_SLOTS} images')
    notify = progress or (lambda _event: None)
    planned = plan_slots(images)
    if menu is not None:
        planned[MENU_INDEX] = (bytes(menu[0]), image_entry(menu[0], profile_id(menu[1])))
    catalogue = build_catalogue({index: entry for index, (_image, entry) in planned.items()})
    for index, (image, _entry) in planned.items():
        write_region(client, slot_address(index), image, notify, slot_name(index))
    write_region(client, CATALOGUE_ADDRESS, catalogue, notify, 'catalogue')
    slots = []
    mismatches = []
    for index, (image, entry) in planned.items():
        actual = read_region(client, slot_address(index), entry['length'], notify, slot_name(index))
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
