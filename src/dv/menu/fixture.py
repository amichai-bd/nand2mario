"""Fixture library and scripted frames for the menu Verilator targets.

`build` is the registered `menu` preload builder: it builds the menu image
and the `exit-demo` game through the software pipeline, lays out a
sixteen-slot SDRAM library around them (seven 32 KiB stub games, the built
`exit-demo` image in slot 1, one 64 KiB MBC1 stub game in two slots, one
empty slot, one entry that is valid but has a foreign length, the rest
empty) and writes the bytes the testbench reads with `$readmemh`, plus the
reference frames of the scripted scenario, the `exit-demo` game frame, the
boot splash schedule and the delayed catalogue path. The catalogue entry layout is
the `catalogue_entry_t` record of cfg/interfaces.json: valid, profile,
length (bits 15:0), crc32, title, length_high (bits 23:16), 7 reserved bytes.
The tagline table follows the entries in the same region, 24 bytes per slot;
five slots declare one, so the footer's lower row is exercised beside slots
that declare none.
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
# The tagline table follows the entries inside the same 1 KiB catalogue region:
# 18 characters then 6 zero bytes per slot. The fixture declares no tagline, so
# every record is zero and the library bytes are what they were before the
# table existed; a scenario that wants one sets the row's `tagline`.
TAGLINE_ADDRESS, TAGLINE_BYTES, TAGLINE_CHARS = 0x88220, 24, 18
TAGLINE = struct.Struct('<18s6x')
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
# Taglines for five of the slots, so the footer's lower row is proved at the
# full plate width, at both centrings and against slots that declare none.
# Every character is one the menu font draws (n2m.profiles.TAGLINE_TEXT).
TAGLINES = {0: b'BRISK PLATFORM HOP', EXIT_SLOT: b'WALK OUT THE DOOR',
            2: b'TEST EVERY BUTTON', SHORT_SLOT: b'HALF AN IMAGE',
            MBC1_SLOT: b'TWO BANKS OF FUN'}
# Scripted frames in `menu-frames.hex` order. A cursor move settles the footer
# over two frames: the frame that shows the move carries the new slot on the
# upper row and the old one on the lower, and the frame after it is settled.
# `footer` names that pair wherever it is not the cursor's own slot twice.
SCENARIO = [dict(cursor=0),                                     # 0 the boot frame, settled
            dict(cursor=1, footer=(1, 0)),                      # 1 the first Down, staged
            dict(cursor=1),                                     # 2 settled on slot 1
            dict(cursor=2, footer=(2, 1)),                      # 3 the second Down, staged
            dict(cursor=2),                                     # 4 settled on slot 2
            dict(cursor=EMPTY_SLOT, footer=(EMPTY_SLOT, 2)),    # 5 staged onto the empty slot
            dict(cursor=EMPTY_SLOT, result=reference.RESULT_INVALID_SLOT, index=EMPTY_SLOT),
            dict(cursor=2, result=reference.RESULT_INVALID_SLOT, index=EMPTY_SLOT),
            dict(cursor=0, footer=(0, 1)),                      # 8 Up to the top, staged
            dict(cursor=EMPTY_SLOT),                            # 9 settled on the empty slot
            dict(cursor=SHORT_SLOT, footer=(SHORT_SLOT, EMPTY_SLOT)),
            dict(cursor=SHORT_SLOT),                            # 11 the foreign length, settled
            dict(cursor=MBC1_SLOT, footer=(MBC1_SLOT, SHORT_SLOT)),
            dict(cursor=MBC1_SLOT)]                             # 13 the 64 KiB entry, settled
# The scroll ramp frames, from SCROLL_FRAME on. The window hides the last slot
# row at rest, so a move onto slot 15 scrolls the list one row up over
# reference.SCROLL_FRAMES frames and a move off it scrolls back; the move's own
# frame carries the first step and the staged footer. The joypad reaches slot
# 14 only through fourteen Downs at two frames each, which no target can afford
# under the 120-second target, so the scroll fixtures deposit 14 into the
# menu's `Cursor` byte at a frame's first pixel; the menu treats it as a move
# and the frames that follow are checked staged and settled, as a navigated
# move is. Both crossings of the scroll boundary are joypad edges.
# `menu-marks.hex` carries the byte's address.
LAST_SLOT = reference.SCROLL_SLOT
RAMP_UP = reference.scroll_ramp(reference.SETTLED_SCY, LAST_SLOT)
RAMP_DOWN = reference.scroll_ramp(reference.SCROLLED_SCY, LAST_SLOT - 1)
SCROLL_FRAME = len(SCENARIO)
SCENARIO += [dict(cursor=LAST_SLOT - 1, footer=(LAST_SLOT - 1, 0)),          # 14 deposited onto 14, staged
             dict(cursor=LAST_SLOT - 1),                                    # 15 settled on 14
             dict(cursor=LAST_SLOT, footer=(LAST_SLOT, LAST_SLOT - 1), scy=RAMP_UP[0]),   # 16 Down: step 1
             dict(cursor=LAST_SLOT, scy=RAMP_UP[1]),                        # 17 step 2, footer settled
             dict(cursor=LAST_SLOT, scy=RAMP_UP[2]),                        # 18 step 3
             dict(cursor=LAST_SLOT, scy=RAMP_UP[3]),                        # 19 scrolled: slot 15 in view
             dict(cursor=LAST_SLOT - 1, footer=(LAST_SLOT - 1, LAST_SLOT), scy=RAMP_DOWN[0]),   # 20 Up: back
             dict(cursor=LAST_SLOT - 1, scy=RAMP_DOWN[1]),                  # 21
             dict(cursor=LAST_SLOT - 1, scy=RAMP_DOWN[2])]                  # 22; the next is frame 15 again
# The exit-demo game frame and the nudge phase frame follow the scenario
# frames in `menu-frames.hex`.
GAME_FRAME = len(SCENARIO)
PHASE_FRAME = GAME_FRAME + 1
# The boot splash frames go in their own file, `menu-splash.hex`, which only
# the splash fixture reads: every displayed frame of the schedule from the
# blank page to the settled list, which is the boot frame again.
SPLASH_FRAME = PHASE_FRAME + 1
SPLASH_FRAMES = reference.SETTLED_FRAME + 1
# The delayed catalogue frames go in `menu-delayed.hex` and
# `menu-delayed-worst.hex`, each read by one fixture. The menu boots with
# `sdram_ready` clear, so it starts settled with slot numbers alone and
# `NOT READY` on the plate; the testbench releases the ready bit after
# displayed frame `hold` and the frame after it commits the bank. Each frame
# after that draws one row, except the frame that also changes the nudge
# phase, which draws half a row and leaves the rest to the next one: so the 16
# rows take 17 frames and the path is `hold` + 19 frames long. The half falls
# on the row the hold chooses, at frame PHASE_HOLD: DELAYED_HOLD is the
# shortest run, where that row is an empty slot, and DELAYED_WORST_HOLD puts
# it on WORST_SLOT, whose sixteen title cells are all letters, which is the
# most expensive row the path can draw. `menu-delayed-marks.hex` carries these
# numbers to `tb_menu_system`, which fails if its own constants differ.
WORST_SLOT = 7
DELAYED_HOLD = 0
DELAYED_WORST_HOLD = reference.PHASE_HOLD - WORST_SLOT - 2
DELAYED_ROWS_FRAMES = 3 + reference.SLOTS


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
        row = {'valid': 0, 'profile': 0, 'length': 0, 'crc32': 0, 'title': bytes(16),
               'tagline': TAGLINES.get(index, b'')}
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


def pack_tagline(row):
    """The 24 tagline bytes of one row; a row with no tagline packs all zero."""
    tagline = bytes(row.get('tagline', b''))
    if len(tagline) > TAGLINE_CHARS:
        raise ValueError(f'a fixture tagline is at most {TAGLINE_CHARS} characters')
    return TAGLINE.pack(tagline)


def library_bytes(menu_image, exit_image=None):
    if len(menu_image) != SLOT_BYTES:
        raise ValueError('menu image must be one 32 KiB slot')
    if exit_image is not None and (len(exit_image) != SLOT_BYTES or exit_image[0x134:0x144] != EXIT_TITLE.ljust(16, b'\0')):
        raise ValueError('exit-demo image must be one 32 KiB slot titled EXIT DEMO')
    rows = entries(menu_image, exit_image)
    table = b''.join(pack_entry(row) for row in rows)
    table += bytes(TAGLINE_ADDRESS - CATALOGUE_ADDRESS - len(table))
    table += b''.join(pack_tagline(row) for row in rows)
    library = b''.join(image_bytes(index, menu_image, exit_image) for index in range(IMAGES)) + table
    return library.ljust(LIBRARY_BYTES, b'\0')


def scenario_frames(menu_image):
    """The scripted menu frames, the exit-demo game frame at GAME_FRAME, then the boot frame in nudge phase 1."""
    rows = entries(menu_image)
    return ([reference.frame(rows, **state) for state in SCENARIO]
            + [exit_frame(), reference.frame(rows, phase=1)])


def splash_frames(menu_image):
    """Every displayed frame of the boot splash, in schedule order."""
    rows = entries(menu_image)
    return [reference.expected(f'splash-{number}', rows) for number in range(SPLASH_FRAMES)]


def delayed_marks():
    """The shape of both delayed alignments: hold and frame count, in fixture order.

    The testbench reads these four bytes and fails when its own constants
    differ, so the hold cannot drift between the frames written here and the
    frames compared there.
    """
    return bytes([DELAYED_HOLD, DELAYED_HOLD + DELAYED_ROWS_FRAMES,
                  DELAYED_WORST_HOLD, DELAYED_WORST_HOLD + DELAYED_ROWS_FRAMES])


def delayed_frames(menu_image, hold=DELAYED_HOLD):
    """Every displayed frame of the delayed catalogue path, in order.

    Displayed frame `number` shows loop iteration `number`'s writes, so it
    carries the nudge phase of that frame number and, once the ready bit is
    released after frame `hold`, the rows the iterations before it drew. The
    frame after the release commits the bank and draws nothing; each frame
    after that draws one row, except the frame that also changes the nudge
    phase, which draws the first half of its row and leaves the rest to the
    next one. So one frame shows a half-drawn row and the path takes 17 frames
    to draw its 16 rows.
    """
    rows = entries(menu_image)
    frames, drawn, partial, shown_phase = [], 0, 0, 0
    for number in range(hold + DELAYED_ROWS_FRAMES):
        ready = number > hold
        phase = reference.phase_of_frame(number)
        if ready and number > hold + 1 and drawn < reference.SLOTS:
            if partial:
                drawn, partial = drawn + 1, 0
            elif phase != shown_phase:
                partial = reference.TITLE_HALF
            else:
                drawn += 1
        shown_phase = phase
        # No frame here carries a footer: the image draws its upper row from
        # the branch the catalogue path takes once the list is whole, which is
        # the iteration after the one that draws the last row, and this path
        # ends on that row.
        frames.append(reference.frame(rows, sdram_ready=ready, drawn_slots=drawn,
                                      partial_cells=partial, phase=phase, footer=(None, None)))
    return frames


def frame_marks(run):
    """The `Frame` address, the address after its `CALL WaitVBlank` and the `Cursor` byte's address.

    The testbench measures the menu's VBlank work between the first two
    points and deposits a slot into the third for the scroll fixtures, so the
    marks come from the build's own symbol and listing records rather than
    from constants that could drift with the image.
    """
    run = Path(run)
    symbols = json.loads((run / 'symbols.json').read_text(encoding='utf-8'))['symbols']
    frame = next(row['value'] for row in symbols if row['symbol'] == 'Frame')
    cursor = next(row['value'] for row in symbols if row['symbol'] == 'Cursor')
    lines = json.loads((run / 'listing.json').read_text(encoding='utf-8'))['lines']
    call = next(row for row in lines if row['address'] == frame and row['instruction'])
    return frame, frame + call['size'], cursor


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
        hex_lines(b''.join(bytes([mark & 255, mark >> 8]) for mark in marks)), encoding='ascii')
    (destination / 'menu-frames.hex').write_text(''.join(hex_lines(frame) for frame in scenario_frames(image)), encoding='ascii')
    (destination / 'menu-splash.hex').write_text(''.join(hex_lines(frame) for frame in splash_frames(image)), encoding='ascii')
    (destination / 'menu-delayed.hex').write_text(''.join(hex_lines(frame) for frame in delayed_frames(image)), encoding='ascii')
    (destination / 'menu-delayed-worst.hex').write_text(
        ''.join(hex_lines(frame) for frame in delayed_frames(image, DELAYED_WORST_HOLD)), encoding='ascii')
    (destination / 'menu-delayed-marks.hex').write_text(hex_lines(delayed_marks()), encoding='ascii')
    (destination / 'program.gb').write_bytes(image)
    return image


if __name__ == '__main__':
    build(Path(__file__).resolve().parents[3], Path(__file__).resolve().parents[3] / 'workdir/builds/menu-fixture')
