"""Fixture library and scripted frames for the menu Verilator targets.

`build` is the registered `menu` preload builder: it builds the menu image
and the `exit-demo` game through the software pipeline, lays out a
sixteen-slot SDRAM library around them (seven 32 KiB stub games, the built
`exit-demo` image in slot 1, one 64 KiB MBC1 stub game in two slots, one
empty slot, one entry that is valid but has a foreign length, the rest
empty) and writes the bytes the testbench reads with `$readmemh`, plus the
reference frames of the scripted scenario and the `exit-demo` game frame. The catalogue entry layout is
the `catalogue_entry_t` record of cfg/interfaces.json: valid, profile,
length (bits 15:0), crc32, title, length_high (bits 23:16), 7 reserved bytes.
"""
import json
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parent))
import reference  # noqa: E402

SLOT_BYTES, IMAGES, MENU = 32768, 17, 16
MBC1_BYTES = 65536
CATALOGUE_ADDRESS, ENTRY_BYTES = 0x88000, 32
LIBRARY_BYTES = 0x8C000
ENTRY = struct.Struct('<BBHI16sB7x')
PROFILE_DIRECT, PROFILE_LOADER, PROFILE_MBC1 = 1, 2, 3
GAME_EXIT_VALUE = 0x10
# Seven 32 KiB stub games: two registered titles, a full
# sixteen-character title, a padded title with the CGB-only flag, a title
# with digits and dashes, a fifteen-byte title with the CGB flag at header
# 0x143 and one on the last row, so ten rows (with the exit demo, the short
# slot and the 64 KiB game) are valid and the empty rows are the minority.
GAMES = {0: b'SPRINGTRAIL', 2: b'V05 BUTTONS', 7: b'SIXTEEN CHAR ROW',
         8: b'CGB ONLY TITLE\x00\xC0', 9: b'ABC-123 XYZ 789', 10: b'CGB FLAGGED ROW\x80',
         15: b'LAST SLOT'}
# Slot 1 holds the built `exit-demo` image (title EXIT DEMO, one Down from
# the boot cursor): a solid bar on map row eight, and while Start is held
# it writes the game exit value. Without the build (host-only tests) a stub
# with the same title stands in, so the menu reference frames are equal.
EXIT_SLOT, EXIT_TITLE, EXIT_TARGET = 1, b'EXIT DEMO', 'exit-demo'
BAR_ROW = 8
# Slot 4 is valid to the menu (valid byte 1) but the engine refuses its
# foreign length; slot 3 is the empty slot the refused-selection scenario uses.
SHORT_SLOT, EMPTY_SLOT = 4, 3
# The 64 KiB MBC1 stub game fills slots 5 and 6 under one entry at 5; the
# menu lists it once and shows slot 6 as empty.
MBC1_SLOT, MBC1_TITLE = 5, b'BANKED GAME'
# Scripted frames in `menu-frames.hex` order.
SCENARIO = [dict(cursor=0), dict(cursor=1), dict(cursor=2), dict(cursor=3),
            dict(cursor=3, result=reference.RESULT_INVALID_SLOT, index=3),
            dict(cursor=2, result=reference.RESULT_INVALID_SLOT, index=3),
            dict(cursor=MBC1_SLOT)]
# The exit-demo game frame and the nudge phase frame follow the scenario
# frames in `menu-frames.hex`.
GAME_FRAME = len(SCENARIO)
PHASE_FRAME = GAME_FRAME + 1


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


def mbc1_image():
    """The 64 KiB MBC1 stub: its entry selects ROM bank 2 and jumps into the window.

    Bank 1, the window after reset, only loops there; bank 2 (the upper half
    of the image) writes the game exit value, so a return to the menu proves
    the second slot was copied and the bank switch mapped it.
    """
    image = bytearray(((MBC1_SLOT * 37 + offset * 11 + (offset >> 7) * 5) ^ (offset >> 12)) & 255 for offset in range(MBC1_BYTES))
    image[0x100:0x150] = bytes(0x50)
    image[0x100:0x104] = bytes([0x00, 0xC3, 0x50, 0x01])                    # nop; jp $0150
    image[0x134:0x144] = MBC1_TITLE.ljust(16, b'\0')
    image[0x147], image[0x148], image[0x14a] = 0x01, 0x01, 1                 # MBC1, 64 KiB
    image[0x150:0x158] = bytes([0x3E, 0x02, 0xEA, 0x00, 0x20, 0xC3, 0x00, 0x40])  # ld a,2; ld ($2000),a; jp $4000
    image[0x4000:0x4002] = bytes([0x18, 0xFE])                                # bank 1: jr $4000
    image[0x8000:0x8007] = bytes([0x3E, GAME_EXIT_VALUE, 0xEA, 0x00, 0x60, 0x18, 0xFE])  # bank 2: exit; jr
    return bytes(image)


def exit_stub():
    return game_image(EXIT_SLOT, EXIT_TITLE)


def exit_frame():
    """The exit-demo screen: shade 3 on the eight pixel rows of map row BAR_ROW, shade 0 elsewhere."""
    return bytes(3 if BAR_ROW * 8 <= y < BAR_ROW * 8 + 8 else 0 for y in range(reference.HEIGHT) for _x in range(reference.WIDTH))


def pack(pixels):
    """Shade bytes to the packed `host snapshot` layout: four 2-bit pixels per byte, first pixel low."""
    return bytes(sum(pixels[i + k] << (2 * k) for k in range(4)) for i in range(0, len(pixels), 4))


def entries(menu_image, exit_image=None):
    """Seventeen catalogue rows shaped like n2m.host.library.unpack_entry."""
    rows = []
    for index in range(IMAGES):
        row = {'valid': 0, 'profile': 0, 'length': 0, 'crc32': 0, 'title': bytes(16)}
        if index == MENU:
            image = menu_image
            row.update(valid=1, profile=PROFILE_LOADER, length=SLOT_BYTES)
        elif index == EXIT_SLOT:
            image = exit_stub() if exit_image is None else exit_image
            row.update(valid=1, profile=PROFILE_DIRECT, length=SLOT_BYTES)
        elif index in GAMES:
            image = game_image(index, GAMES[index])
            row.update(valid=1, profile=PROFILE_DIRECT, length=SLOT_BYTES)
        elif index == MBC1_SLOT:
            image = mbc1_image()
            row.update(valid=1, profile=PROFILE_MBC1, length=MBC1_BYTES)
        elif index == SHORT_SLOT:
            image = game_image(index, b'SHORT IMAGE')
            row.update(valid=1, profile=PROFILE_DIRECT, length=16384)
        else:
            rows.append(row)
            continue
        row.update(crc32=zlib.crc32(image), title=image[0x134:0x144])
        rows.append(row)
    return rows


def image_bytes(index, menu_image, exit_image=None):
    """The 32 KiB of slot `index`; the MBC1 image spans MBC1_SLOT and the slot after it."""
    if index == MENU:
        return menu_image
    if index == EXIT_SLOT:
        return exit_stub() if exit_image is None else exit_image
    if index in GAMES:
        return game_image(index, GAMES[index])
    if index == SHORT_SLOT:
        return game_image(index, b'SHORT IMAGE')
    if index in (MBC1_SLOT, MBC1_SLOT + 1):
        start = (index - MBC1_SLOT) * SLOT_BYTES
        return mbc1_image()[start:start + SLOT_BYTES]
    return bytes(SLOT_BYTES)


def pack_entry(row):
    """The 32 catalogue bytes of one row: the length split into its low word and high byte."""
    return ENTRY.pack(row['valid'], row['profile'], row['length'] & 0xFFFF, row['crc32'], row['title'], row['length'] >> 16)


def library_bytes(menu_image, exit_image=None):
    if len(menu_image) != SLOT_BYTES:
        raise ValueError('menu image must be one 32 KiB slot')
    if exit_image is not None and (len(exit_image) != SLOT_BYTES or exit_image[0x134:0x144] != EXIT_TITLE.ljust(16, b'\0')):
        raise ValueError('exit-demo image must be one 32 KiB slot titled EXIT DEMO')
    rows = entries(menu_image, exit_image)
    table = b''.join(pack_entry(row) for row in rows)
    library = b''.join(image_bytes(index, menu_image, exit_image) for index in range(IMAGES)) + table
    return library.ljust(LIBRARY_BYTES, b'\0')


def scenario_frames(menu_image):
    """The scripted menu frames, the exit-demo game frame at GAME_FRAME, then the boot frame in nudge phase 1."""
    rows = entries(menu_image)
    return ([reference.frame(rows, **state) for state in SCENARIO]
            + [exit_frame(), reference.frame(rows, phase=1)])


def frame_marks(run):
    """The `Frame` address and the address after its `CALL WaitVBlank`.

    The testbench measures the menu's VBlank work between those two points,
    so the marks come from the build's own symbol and listing records rather
    than from a constant that could drift with the image.
    """
    run = Path(run)
    symbols = json.loads((run / 'symbols.json').read_text(encoding='utf-8'))['symbols']
    frame = next(row['value'] for row in symbols if row['symbol'] == 'Frame')
    lines = json.loads((run / 'listing.json').read_text(encoding='utf-8'))['lines']
    call = next(row for row in lines if row['address'] == frame and row['instruction'])
    return frame, frame + call['size']


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
    game = build_target(root, destination / 'sw', SimpleNamespace(target=EXIT_TARGET, rebuild=True), git_state(root))
    if game['status'] != 'PASS' or game['profile'] != 'dmg-direct-v1':
        raise ValueError('exit-demo preload software build failed')
    exit_image = (root / game['rom']).read_bytes()
    (destination / 'menu-library.hex').write_text(hex_lines(library_bytes(image, exit_image)), encoding='ascii')
    marks = frame_marks((Path(root) / report['rom']).parent)
    (destination / 'menu-marks.hex').write_text(
        hex_lines(bytes([marks[0] & 255, marks[0] >> 8, marks[1] & 255, marks[1] >> 8])), encoding='ascii')
    (destination / 'menu-frames.hex').write_text(''.join(hex_lines(frame) for frame in scenario_frames(image)), encoding='ascii')
    (destination / 'program.gb').write_bytes(image)
    return image


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[3], Path(__file__).resolve().parents[3] / 'workdir/builds/menu-fixture')
