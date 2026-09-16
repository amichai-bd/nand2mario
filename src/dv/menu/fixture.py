"""Fixture library and scripted frames for the menu Verilator targets.

`build` is the registered `menu` preload builder: it builds the menu image
through the software pipeline, lays out a seventeen-image SDRAM library
around it (eight stub games, one empty slot, one entry that is valid but
has a foreign length, the rest empty) and writes the bytes the testbench
reads with `$readmemh`, plus the reference frames of the scripted scenario.
The catalogue entry layout is the `catalogue_entry_t` record of
cfg/interfaces.json: valid, profile, length, crc32, title, 8 reserved bytes.
"""
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference  # noqa: E402

SLOT_BYTES, IMAGES, MENU = 32768, 17, 16
CATALOGUE_ADDRESS, ENTRY_BYTES = 0x88000, 32
LIBRARY_BYTES = 0x8C000
ENTRY = struct.Struct('<BBHI16s8x')
PROFILE_DIRECT, PROFILE_LOADER = 1, 2
# Eight stub games: the three registered titles, a title with digits and
# dashes, a fifteen-byte title with the CGB flag at header 0x143, a full
# sixteen-character title, a padded title with the CGB-only flag and one on
# the last row, so nine rows (with the short slot) are valid and the empty
# rows are the minority.
GAMES = {0: b'SPRINGTRAIL', 1: b'STACKDROP', 2: b'V05 BUTTONS', 5: b'ABC-123 XYZ 789',
         6: b'CGB FLAGGED ROW\x80', 7: b'SIXTEEN CHAR ROW', 8: b'CGB ONLY TITLE\x00\xC0',
         15: b'LAST SLOT'}
# Slot 4 is valid to the menu (valid byte 1) but the engine refuses its
# foreign length; slot 3 is the empty slot the refused-selection scenario uses.
SHORT_SLOT, EMPTY_SLOT = 4, 3
# Scripted frames in `menu-frames.hex` order.
SCENARIO = [dict(cursor=0), dict(cursor=1), dict(cursor=2), dict(cursor=3),
            dict(cursor=3, result=reference.RESULT_INVALID_SLOT, index=3),
            dict(cursor=2, result=reference.RESULT_INVALID_SLOT, index=3)]


def game_image(index, title):
    """A stub game: NOP; JP $0150; JR $0150, its title (str or bytes) in the header, a slot-specific pattern elsewhere."""
    if isinstance(title, str):
        title = title.encode('ascii')
    image = bytearray(((index * 37 + offset * 11 + (offset >> 7) * 5) ^ (offset >> 12)) & 255 for offset in range(SLOT_BYTES))
    image[0x100:0x150] = bytes(0x50)
    image[0x100:0x104] = bytes([0x00, 0xC3, 0x50, 0x01])
    image[0x134:0x144] = title.ljust(16, b'\0')
    image[0x14a] = 1
    image[0x150:0x152] = bytes([0x18, 0xFE])
    return bytes(image)


def entries(menu_image):
    """Seventeen catalogue rows shaped like n2m.host.library.unpack_entry."""
    rows = []
    for index in range(IMAGES):
        row = {'valid': 0, 'profile': 0, 'length': 0, 'crc32': 0, 'title': bytes(16)}
        if index == MENU:
            image = menu_image
            row.update(valid=1, profile=PROFILE_LOADER, length=SLOT_BYTES)
        elif index in GAMES:
            image = game_image(index, GAMES[index])
            row.update(valid=1, profile=PROFILE_DIRECT, length=SLOT_BYTES)
        elif index == SHORT_SLOT:
            image = game_image(index, b'SHORT IMAGE')
            row.update(valid=1, profile=PROFILE_DIRECT, length=16384)
        else:
            rows.append(row)
            continue
        row.update(crc32=zlib.crc32(image), title=image[0x134:0x144])
        rows.append(row)
    return rows


def image_bytes(index, menu_image):
    if index == MENU:
        return menu_image
    if index in GAMES:
        return game_image(index, GAMES[index])
    if index == SHORT_SLOT:
        return game_image(index, b'SHORT IMAGE')
    return bytes(SLOT_BYTES)


def library_bytes(menu_image):
    if len(menu_image) != SLOT_BYTES:
        raise ValueError('menu image must be one 32 KiB slot')
    rows = entries(menu_image)
    table = b''.join(ENTRY.pack(row['valid'], row['profile'], row['length'], row['crc32'], row['title']) for row in rows)
    library = b''.join(image_bytes(index, menu_image) for index in range(IMAGES)) + table
    return library.ljust(LIBRARY_BYTES, b'\0')


def scenario_frames(menu_image):
    rows = entries(menu_image)
    return [reference.frame(rows, **state) for state in SCENARIO]


def hex_lines(data):
    return ''.join(f'{byte:02x}\n' for byte in data)


def build(root, destination):
    """Build the menu image and write the library and frame files beside it."""
    from types import SimpleNamespace
    sys.path.insert(0, str(root / 'tools'))
    from n2m.records import git_state
    from sw.rom_build import build_target
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    report = build_target(root, destination / 'sw', SimpleNamespace(target='menu', rebuild=True), git_state(root))
    if report['status'] != 'PASS' or report['profile'] != 'dmg-loader-v1':
        raise ValueError('menu preload software build failed')
    image = (root / report['rom']).read_bytes()
    (destination / 'menu-library.hex').write_text(hex_lines(library_bytes(image)), encoding='ascii')
    (destination / 'menu-frames.hex').write_text(''.join(hex_lines(frame) for frame in scenario_frames(image)), encoding='ascii')
    (destination / 'program.gb').write_bytes(image)
    return image


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[3], Path(__file__).resolve().parents[3] / 'workdir/builds/menu-fixture')
