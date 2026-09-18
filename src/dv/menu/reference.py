"""Independent menu frame reference: the layout rules of wiki/src/sw/menu/SPEC.md.

The frame is composed from the font's authoritative shade JSON and literal
layout rules, never from the assembled ROM, its tilemap or DUT output. A
catalogue is a list of entries shaped like `n2m.host.library.parse_catalogue`
rows: `valid` (int), `profile` (int), `length` (int), `title` (16 bytes) and
`tagline` (up to 18 bytes, empty for none); index i is slot i, and an entry 16
(the menu itself) is ignored. A row that carries only `valid` and `title` still
renders: the missing fields read as an unknown profile and a zero length.
The window's two rows are the information footer of
wiki/src/sw/menu/SPEC.md: the upper row describes one slot and the lower row
carries its tagline or the selection message. `check_pixels` compares a packed
`host snapshot` frame (5760 bytes, four 2-bit pixels per byte, first pixel
in the low bits) pixel for pixel and names the first mismatch.

The frame is the background map, the window over its bottom two rows and one
object on top: the cursor pointer. Object shade 0 is transparent, the rest map
through OBP0; the window draws through BGP like the background.

The background map is 32 rows: the boot splash above the list. A frame is
read from it at the slide's `scy` and drawn through the fade's `bgp`, so the
splash frames and the settled menu come from the same rules; `splash_state`
gives both from the displayed frame number alone.
"""
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[3]
FONT = ROOT / 'src/sw/menu/assets/font-tiles.json'
GREY_ART = ROOT / 'src/sw/menu/assets/design/v2-grey-tiles.json'
POINTER_ART = ROOT / 'src/sw/menu/assets/design/v2-cursor-tiles.json'
SPLASH_ART = ROOT / 'src/sw/menu/assets/design/v2-splash-tiles.json'
STAR_ART = ROOT / 'src/sw/menu/assets/design/v2-stars-tiles.json'
FOOTER_ART = ROOT / 'src/sw/menu/assets/design/v2-footer-tiles.json'
PULSE_ART = ROOT / 'src/sw/menu/assets/design/v2-pulse-tiles.json'
WIDTH, HEIGHT = 160, 144
COLUMNS, ROWS = 20, 18
SLOTS = 16
# A slot row's sixteen title cells, and the half a delayed frame draws when it
# also changes the nudge phase (wiki/src/sw/menu/SPEC.md).
TITLE_CELLS = 16
TITLE_HALF = TITLE_CELLS // 2
PACKED_BYTES = WIDTH * HEIGHT // 4
# Font atlas order: A-Z, 0-9, dash, blank, cursor arrow.
TILE_DIGIT, TILE_DASH, TILE_BLANK, TILE_ARROW = 26, 36, 37, 38
FONT_TILES = 39
# The bank: the 39 font tiles, the same 39 on a mid-grey page, the six authored
# grey cells and the two pointer phases. Adding TILE_GREY to a font tile moves
# it onto the grey page.
TILE_GREY = FONT_TILES
GREY_ART_TILES, POINTER_TILES = 6, 2
# The authored grey cells, in atlas order.
TILE_CAP_LEFT, TILE_CAP_RIGHT = 78, 79
TILE_FADE32, TILE_FADE21, TILE_FADE10, TILE_SHADOW = 80, 81, 82, 83
# The two pointer phases, the same arrow one pixel apart. They are object
# tiles; no map cell ever names them.
TILE_POINTER = 84
# The boot splash badge, four cells by two, the only cells above the list.
TILE_BADGE, BADGE_COLUMNS, BADGE_TILES = 86, 4, 8
# The star field's four cells.
TILE_STAR, STAR_TILES = 94, 4
# The footer's two cells, on the grey page like the font: the cartridge badge
# the upper footer row draws and the separator dot no cell names yet.
TILE_CART, TILE_DOT, FOOTER_ART_TILES = 98, 99, 2
# The press-A badge's two phases on the grey page: dim (shade 1 on the grey
# page) in nudge phase 0, ink in phase 1. The same frame-counter bit drives the
# pointer nudge, the star twinkle and this pulse.
TILE_PULSE, PULSE_TILES = 100, 2
BANK_TILES = 102
# The grey page shade: the font's shade 0 becomes 2, its ink stays 3.
GREY_PAGE = 2
# Cells between the two plate caps of the header and bottom plates.
PLATE_CELLS = COLUMNS - 2
# Frames the cursor holds each nudge phase. The same bit twinkles the stars.
PHASE_HOLD = 16
PHASES = 2
# The star field: the two columns the list always leaves blank, column 0 (the
# page the cursor object draws on) and column 3 (between the slot number and
# the title). The rule reads map coordinates, so the field wraps with the
# 32-row map and rides the list's own SCY; DMG has one background layer and
# the composite layout spends it on the list, so there is no second band and
# no SCX drift. A title cell is never a star: the star set must not depend on
# the catalogue, and the slot-row draw path stays off the star rule.
STAR_COLUMNS = (0, 3)
STAR_MASK = 3
# The window: the bottom plate alone, pinned to the last two screen rows.
WINDOW_X, WINDOW_Y = 7, 128
WINDOW_ROWS = 2
FOOTER_ROW, WINDOW_STATUS_ROW = 0, 1
# The information footer. The upper row is the cartridge badge in plate cell
# FOOTER_BADGE_COLUMN and then FOOTER_TEXT_CELLS cells of the entry's profile
# and size; the pad character keeps the plate's own gradient fill, as the
# status rows do. The lower row is the tagline, centred like the status text,
# unless a message is on it.
FOOTER_BADGE_COLUMN, FOOTER_TEXT_COLUMN, FOOTER_TEXT_CELLS = 1, 2, 16
# The press-A badge: the plate cell before the cartridge badge, drawn with the
# upper row and pulsing on the nudge phase. The footer's text never reaches it.
PULSE_COLUMN = 0
PLATE_PAD = '#'
# The profile ID of an entry to the word the footer draws (cfg/interfaces.json
# profile group); any other ID draws dashes.
PROFILE_WORDS = {1: 'DIRECT', 2: 'LOADER', 3: 'MBC1'}
PROFILE_CELLS = 6
# The size field: whole kibibytes in SIZE_DIGITS columns with leading blanks,
# then ' KB'. A length that is not a whole number of kibibytes, or one of a
# thousand and more, draws dashes instead of digits.
KIBIBYTE, SIZE_DIGITS = 1024, 3
EMPTY_LINE = 'EMPTY SLOT'
# One tagline record: the characters the menu reads, at TAGLINE_BYTES stride
# behind the entries in the same window bank (wiki/src/rtl/storage/MAS_sdram.md).
TAGLINE_CHARS = 18
# The boot splash (wiki/src/sw/menu/SPEC.md#boot-splash). The background map is
# 32 rows: the splash fills the 18 rows the screen shows at SCY 0, the list
# follows it, and the list's last four rows wrap into map rows 0..3 as the
# splash's own top rows scroll off. The settled view is SCY 144, at which the
# visible rows are exactly the list.
MAP_ROWS = 32
LIST_MAP_ROW = ROWS
SETTLED_SCY = 8 * LIST_MAP_ROW
WRAPPED_ROWS = LIST_MAP_ROW + ROWS - MAP_ROWS
# The fade: the page first, then the ink, then the mid shades, ending on the
# identity palette. Each step holds FADE_HOLD frames; the slide then raises
# SCY by SLIDE_STEP a frame. These two constants are the whole schedule, here
# and mirrored in the image; they are chosen as the longest splash whose
# frame-by-frame target still fits the simulation wall budget.
FADE = (0x00, 0x40, 0x90, 0xE4)
FADE_HOLD = 2
SLIDE_STEP = 16
FADE_FRAMES = len(FADE) * FADE_HOLD
SLIDE_FRAMES = SETTLED_SCY // SLIDE_STEP
# The first frame that carries the settled list: the last slide frame.
SETTLED_FRAME = FADE_FRAMES + SLIDE_FRAMES - 1
# A skip draws at most this many wrapped rows in one VBlank, which keeps the
# frame's work well inside the VBlank budget the testbench measures.
SKIP_ROWS = 2
# The scroll ramp (wiki/src/sw/menu/SPEC.md#the-scroll-ramp). The window hides
# the sixteenth slot row at the settled SCY, so a cursor on SCROLL_SLOT asks
# for the view one row up, SCROLLED_SCY, and the header scrolls off with the
# list; any other slot asks for the settled view. SCY moves SCROLL_STEP a
# frame toward the view the cursor names, so a move across that boundary is
# SCROLL_FRAMES frames long and the pointer rides its row throughout. The image
# holds the same constants.
SCROLL_SLOT = SLOTS - 1
SCROLLED_SCY = SETTLED_SCY + 8
SCROLL_STEP = 2
SCROLL_FRAMES = (SCROLLED_SCY - SETTLED_SCY) // SCROLL_STEP
# The splash art, from the approved sheet: the badge and its two lines.
BADGE_ROW, BADGE_COLUMN = 4, 8
SPLASH_TITLE, SPLASH_TITLE_ROW, SPLASH_TITLE_COLUMN = 'GAME LIBRARY', 8, 4
SPLASH_HINT, SPLASH_HINT_ROW, SPLASH_HINT_COLUMN = 'SELECT A GAME', 10, 3
# Header 0x143 values that mark a 15-byte title: the CGB flag and CGB-only flag.
CGB_FLAG, CGB_ONLY = 0x80, 0xC0
HEADER, HEADER_COLUMN = 'GAME LIBRARY', 4
SLOT_ROW, NUMBER_COLUMN, TITLE_COLUMN, STATUS_ROW = 1, 1, 4, 17
RESULT_NONE, RESULT_OK, RESULT_INVALID_SLOT, RESULT_CRC_MISMATCH, RESULT_NOT_READY = 0, 1, 2, 3, 4
WORDS = {RESULT_INVALID_SLOT: 'INVALID', RESULT_CRC_MISMATCH: 'BAD CRC', RESULT_NOT_READY: 'NOT READY'}
NO_INDEX = 255
# The identity palette, for the background and for the pointer.
IDENTITY_PALETTE = (0, 1, 2, 3)


def glyph_tile(byte):
    """Title byte to font tile: letters, digits and dash; zero and space blank; anything else the dash."""
    if byte in (0, 0x20):
        return TILE_BLANK
    if 0x30 <= byte <= 0x39:
        return TILE_DIGIT + byte - 0x30
    if 0x41 <= byte <= 0x5A:
        return byte - 0x41
    return TILE_DASH


def title_tiles(title):
    """The 16 title cells: header 0x143 is the CGB flag when the title is 15 bytes, so 0x80/0xC0 there is blank."""
    title = bytes(title)[:16].ljust(16, b'\0')
    last = TILE_BLANK if title[15] in (CGB_FLAG, CGB_ONLY) else glyph_tile(title[15])
    return [glyph_tile(byte) for byte in title[:15]] + [last]


def text_tiles(text):
    return [glyph_tile(ord(character)) for character in text]


def status_text(result=RESULT_NONE, index=NO_INDEX, sdram_ready=True):
    """The 20-character status row."""
    if not sdram_ready:
        return 'NOT READY'.ljust(COLUMNS)
    if result < RESULT_INVALID_SLOT:
        return ' ' * COLUMNS
    number = f'{index:02d}' if index < 17 else '--'
    return f'SLOT {number} {WORDS.get(result, "ERROR")}'.ljust(COLUMNS)


def plate(fill, text=''):
    """A plate row: the two grey caps around 18 `fill` cells, with `text` centred on the grey page.

    The leftover space is biased left, so a 15-character message starts at
    column 2 of the screen exactly as the contract states.
    """
    cells = [fill] * PLATE_CELLS
    if text:
        start = (PLATE_CELLS - len(text)) // 2
        cells[start:start + len(text)] = [TILE_GREY + tile for tile in text_tiles(text)]
    return [TILE_CAP_LEFT] + cells + [TILE_CAP_RIGHT]


def entry_of(entries, slot):
    """The catalogue row of a slot, or None when the catalogue has no such row."""
    if slot is None or not 0 <= slot < SLOTS or slot >= len(entries):
        return None
    return entries[slot]


def size_text(length):
    """The size field: whole kibibytes with leading blanks, or dashes for anything the field cannot hold."""
    kibibytes = length // KIBIBYTE
    if length % KIBIBYTE or kibibytes >= 10 ** SIZE_DIGITS:
        return f'{"-" * SIZE_DIGITS} KB'
    return f'{kibibytes:{SIZE_DIGITS}d} KB'


def footer_line(entry):
    """The footer's upper text: the profile word and the size of a valid entry, or the empty-slot line.

    Exactly FOOTER_TEXT_CELLS characters, padded with PLATE_PAD, which keeps
    the plate's own gradient fill where the line does not reach.
    """
    if not entry or entry.get('valid') != 1:
        return EMPTY_LINE.ljust(FOOTER_TEXT_CELLS, PLATE_PAD)
    word = PROFILE_WORDS.get(entry.get('profile', 0), '-' * PROFILE_CELLS)
    line = f'{word:<{PROFILE_CELLS}}  {size_text(entry.get("length", 0))}'
    return line.ljust(FOOTER_TEXT_CELLS, PLATE_PAD)


def tagline_line(entry):
    """The tagline characters of an entry, up to the record's first zero; an all-zero record is no tagline."""
    if not entry:
        return ''
    raw = bytes(entry.get('tagline') or b'')[:TAGLINE_CHARS]
    return raw.partition(b'\0')[0].decode('latin-1')


def plate_cell(character):
    """One plate cell of a text line: the pad keeps the gradient fill, everything else draws on the grey page."""
    if character == PLATE_PAD:
        return TILE_FADE21
    return TILE_GREY + glyph_tile(ord(character))


def footer_row(entry, phase=0):
    """The footer's upper row: the press-A badge in nudge phase `phase`, the cartridge badge, then the entry's profile and size."""
    cells = [TILE_FADE21] * PLATE_CELLS
    cells[PULSE_COLUMN] = TILE_PULSE + phase
    cells[FOOTER_BADGE_COLUMN] = TILE_CART
    for offset, character in enumerate(footer_line(entry)):
        cells[FOOTER_TEXT_COLUMN + offset] = plate_cell(character)
    return [TILE_CAP_LEFT] + cells + [TILE_CAP_RIGHT]


def star_here(column, map_row):
    """Whether the star field puts a star in this map cell.

    An incremental rule: walking a row adds 3, walking a column adds 5, so the
    image carries the sum rather than multiplying, and the exclusive-or of the
    row's own high bits breaks the lattice the plain sum would draw.
    """
    return ((3 * column + 5 * map_row) ^ (map_row >> 2)) & STAR_MASK == 0


def star_tile(column, map_row, phase=0):
    """The star cell of this map cell in nudge phase `phase`.

    The four star cells cycle with the same frame-counter bit that nudges the
    cursor, so the field twinkles once every PHASE_HOLD frames and follows
    from the frame number alone.
    """
    return TILE_STAR + (column + map_row + phase) % STAR_TILES


def header_row():
    """The header plate: the title on the grey page over the 3-to-2 gradient fill."""
    cells = [TILE_FADE32] * PLATE_CELLS
    cells[HEADER_COLUMN - 1:HEADER_COLUMN - 1 + len(HEADER)] = [TILE_GREY + tile
                                                                for tile in text_tiles(HEADER)]
    return [TILE_CAP_LEFT] + cells + [TILE_CAP_RIGHT]


def list_rows(entries, cursor=0, phase=0, result=RESULT_NONE, index=NO_INDEX, sdram_ready=True,
              drawn_slots=SLOTS, partial_cells=0):
    """The list's own 18 rows; `drawn_slots` counts the title rows already drawn on the delayed path.

    `partial_cells` is the first cells of the row after them, the half a
    delayed frame draws when it also changes the nudge phase.

    The selection is the pointer object, not a map cell, so `cursor` does not
    change the background at all; `frame` uses it. `phase` does: it is the
    twinkle of the star field in the two gutter columns.

    Row 17 is the page. The bottom plate left the background for the window,
    and the row it used to fill is behind the window whenever the list is
    settled.
    """
    if not 0 <= cursor < SLOTS:
        raise ValueError('cursor must select a slot 0..15')
    if phase not in range(PHASES):
        raise ValueError('phase must be 0 or 1')
    if not 0 <= partial_cells < TITLE_CELLS:
        raise ValueError(f'a partial row draws 0..{TITLE_CELLS - 1} cells')
    rows = [[TILE_BLANK] * COLUMNS for _ in range(ROWS)]
    rows[0] = header_row()
    for slot in range(SLOTS):
        row = rows[SLOT_ROW + slot]
        row[NUMBER_COLUMN:NUMBER_COLUMN + 2] = text_tiles(f'{slot:02d}')
        cells = TITLE_CELLS if slot < drawn_slots else partial_cells if slot == drawn_slots else 0
        if cells and slot < len(entries) and entries[slot]['valid'] == 1:
            row[TITLE_COLUMN:TITLE_COLUMN + cells] = title_tiles(entries[slot]['title'])[:cells]
        map_row = (LIST_MAP_ROW + SLOT_ROW + slot) % MAP_ROWS
        for column in STAR_COLUMNS:
            if star_here(column, map_row):
                row[column] = star_tile(column, map_row, phase)
    return rows


def window_rows(entries=(), footer=(0, 0), phase=0, result=RESULT_NONE, index=NO_INDEX, sdram_ready=True):
    """The window's two rows: the information footer of the slots `footer` names.

    The window is opaque from its top left corner to the bottom right of the
    screen, so it cannot be a band: it is pinned to the last two screen rows
    and carries the plate alone. Its upper row describes the slot `footer[0]`
    and its lower row carries the tagline of `footer[1]`, which lags the
    cursor by a frame because no VBlank writes two plate rows. A status
    message owns the lower row while it is shown, and a row the image has not
    drawn is None: the plate's own fill, with no badge and no pulse either.
    `phase` is the nudge phase the press-A badge pulses on.
    """
    upper, lower = footer
    rows = [footer_row(entry_of(entries, upper), phase) if upper is not None else plate(TILE_FADE21)]
    message = status_text(result, index, sdram_ready).strip()
    if message:
        return rows + [plate(TILE_FADE21, message)]
    tagline = tagline_line(entry_of(entries, lower)) if lower is not None else ''
    return rows + [plate(TILE_FADE21, tagline)]


def window_on(scy=SETTLED_SCY):
    """Whether the window is on: the image enables it on the settled frame, with the cursor, and the scroll ramp keeps it on."""
    return SETTLED_SCY <= scy <= SCROLLED_SCY


def scroll_target(cursor=0):
    """The SCY the list settles at for this cursor: one row up on the last slot, which the window otherwise hides."""
    if not 0 <= cursor < SLOTS:
        raise ValueError('cursor must select a slot 0..15')
    return SCROLLED_SCY if cursor == SCROLL_SLOT else SETTLED_SCY


def scroll_ramp(scy, cursor):
    """The SCY of each frame after a move to `cursor` from a list at `scy`, until it settles.

    A frame steps SCROLL_STEP toward the view the cursor names, and the move's
    own frame carries the first step, so a move across the boundary shows
    SCROLL_FRAMES frames and a move that stays on one side shows none.
    """
    if not SETTLED_SCY <= scy <= SCROLLED_SCY or scy % SCROLL_STEP:
        raise ValueError('a settled list scrolls between SETTLED_SCY and SCROLLED_SCY in whole steps')
    target = scroll_target(cursor)
    step = SCROLL_STEP if target > scy else -SCROLL_STEP
    return list(range(scy + step, target + step, step)) if target != scy else []


def splash_rows():
    """The splash's own 18 map rows: the badge over its two lines of text."""
    rows = [[TILE_BLANK] * COLUMNS for _ in range(ROWS)]
    for cell in range(BADGE_COLUMNS):
        rows[BADGE_ROW][BADGE_COLUMN + cell] = TILE_BADGE + cell
        rows[BADGE_ROW + 1][BADGE_COLUMN + cell] = TILE_BADGE + BADGE_COLUMNS + cell
    for row, column, text in ((SPLASH_TITLE_ROW, SPLASH_TITLE_COLUMN, SPLASH_TITLE),
                              (SPLASH_HINT_ROW, SPLASH_HINT_COLUMN, SPLASH_HINT)):
        rows[row][column:column + len(text)] = text_tiles(text)
    return rows


def background_map(entries, wrapped=WRAPPED_ROWS, **state):
    """The 32 map rows: the splash, then the list, whose last rows wrap into rows 0..3.

    `wrapped` counts the list's last rows already drawn over the splash's own
    top rows; the image draws one of them per slide frame, after that splash
    row has left the top of the screen and before the list row reaches the
    bottom.
    """
    if not 0 <= wrapped <= WRAPPED_ROWS:
        raise ValueError(f'wrapped must be 0..{WRAPPED_ROWS}')
    listing = list_rows(entries, **state)
    rows = splash_rows() + listing[:MAP_ROWS - LIST_MAP_ROW]
    for row in range(wrapped):
        rows[row] = listing[MAP_ROWS - LIST_MAP_ROW + row]
    return rows


def tilemap(entries, scy=SETTLED_SCY, wrapped=WRAPPED_ROWS, **state):
    """The visible 20x18 tile indices: the 32-row map read from `scy`, which wraps.

    The settled view is SCY 144, at which the visible rows are the list alone.
    """
    if scy % 8 or not 0 <= scy < 8 * MAP_ROWS:
        raise ValueError('scy is a whole cell row of the 32-row map')
    rows = background_map(entries, wrapped=wrapped, **state)
    return [rows[(scy // 8 + row) % MAP_ROWS] for row in range(ROWS)]


def objects(cursor=0, phase=0, scy=SETTLED_SCY, **ignored):
    """The object list: the cursor pointer alone, on its slot's row wherever the scroll ramp has put it.

    One object never reaches the ten-per-line limit, and its priority flag is
    clear, so it draws in front of the background, and of the window, wherever
    its shade is not 0. The list rides SCY while the splash slides away and the
    object does not, so the menu shows the cursor only once the slide has
    settled; from then on the pointer rides the list, lifted by however far
    the ramp has scrolled past the settled view.
    """
    if not 0 <= cursor < SLOTS:
        raise ValueError('cursor must select a slot 0..15')
    if phase not in range(PHASES):
        raise ValueError('phase must be 0 or 1')
    if not window_on(scy):
        return []
    return [(0, 8 * (SLOT_ROW + cursor) - (scy - SETTLED_SCY), TILE_POINTER + phase)]


def phase_of_frame(number):
    """The nudge phase of displayed frame `number`, counted from the menu's first frame."""
    if number < 0:
        raise ValueError('a frame number counts from the menu\'s first frame')
    return number // PHASE_HOLD % PHASES


def splash_state(number):
    """The boot splash state of displayed frame `number`: (bgp, scy, wrapped rows drawn).

    The frame counter alone decides it, as it does the nudge phase. Loop
    iteration `number` writes one register and, while the slide runs, draws
    one wrapped list row, and its writes appear in the frame it numbers.
    """
    if number < 0:
        raise ValueError('a frame number counts from the menu\'s first frame')
    if number < FADE_FRAMES:
        return FADE[number // FADE_HOLD], 0, 0
    step = min(number - FADE_FRAMES + 1, SLIDE_FRAMES)
    return FADE[-1], SLIDE_STEP * step, min(step, WRAPPED_ROWS)


def splash_at_boot(index=NO_INDEX, sdram_ready=True):
    """Whether the boot splash runs, from the two bytes the image reads at boot.

    It needs the catalogue listed at boot, and it needs to be the first boot
    since reset. The loader's last selected index is NO_INDEX only until the
    first selection, so a menu that has been here before - a return from a
    game, or a reboot after any select, refused or not - starts settled.
    """
    return sdram_ready and index == NO_INDEX


def skip_schedule(number):
    """The frames the splash shows after a skip, counted from displayed frame `number`.

    `number` is the last frame whose draw has completed when the press is
    sampled, which is the frame before the one that samples it: the image
    reads the wrapped-row count its previous iteration left. During the fade,
    where no row has been drawn yet, both readings give the same frames.

    A skip draws at most SKIP_ROWS wrapped rows a frame, so no VBlank carries
    more than half the map and the map finishes in two frames. Each of those
    frames is the schedule's own frame for the rows drawn so far, and the last
    is the settled frame, so a skip shows nothing the schedule does not.
    """
    rows = splash_state(number)[2]
    shown = []
    while rows < WRAPPED_ROWS:
        rows = min(rows + SKIP_ROWS, WRAPPED_ROWS)
        shown.append(SETTLED_FRAME if rows == WRAPPED_ROWS else FADE_FRAMES + rows - 1)
    return shown or [SETTLED_FRAME]


def atlas_tiles(path, count):
    """One row of `count` 8x8 tiles from an authoritative shade JSON."""
    atlas = json.loads(path.read_text(encoding='utf-8'))
    if atlas['schema_version'] != 1 or atlas['height'] != 8 or atlas['width'] != count * 8:
        raise ValueError(f'{path.name} must be one row of {count} tiles')
    return [[atlas['pixels'][y][tile * 8:tile * 8 + 8] for y in range(8)] for tile in range(count)]


def font_tiles():
    """The 39 font tiles as rows of shades, from the asset's authoritative shade JSON."""
    return atlas_tiles(FONT, FONT_TILES)


def greyed(tile):
    """The grey-page copy of a font tile: shade 0 becomes 2, the ink stays 3."""
    return [[GREY_PAGE if shade == 0 else shade for shade in row] for row in tile]


def bank_tiles():
    """The 102-tile bank: font, the font on the grey page, the grey cells, the pointer phases, the badge, the stars, the footer cells, the press-A phases."""
    font = font_tiles()
    bank = (font + [greyed(tile) for tile in font]
            + atlas_tiles(GREY_ART, GREY_ART_TILES) + atlas_tiles(POINTER_ART, POINTER_TILES)
            + atlas_tiles(SPLASH_ART, BADGE_TILES) + atlas_tiles(STAR_ART, STAR_TILES)
            + [greyed(tile) for tile in atlas_tiles(FOOTER_ART, FOOTER_ART_TILES)]
            + [greyed(tile) for tile in atlas_tiles(PULSE_ART, PULSE_TILES)])
    if len(bank) != BANK_TILES:
        raise ValueError(f'the menu bank is {BANK_TILES} tiles')
    return bank


def footer_slots(cursor=0, footer=None, drawn_slots=SLOTS, sdram_ready=True):
    """The slots the footer's two rows describe, or None for a row the image has not drawn yet.

    There is no footer until the list is whole, so a frame drawn before that
    has neither row. After it both rows are the cursor's own slot, unless a
    move has not settled yet, which `footer` names.
    """
    if footer is None:
        if not sdram_ready or drawn_slots < SLOTS:
            return None, None
        return cursor, cursor
    upper, lower = footer
    for slot in (upper, lower):
        if slot is not None and not 0 <= slot < SLOTS:
            raise ValueError('a footer row describes a slot 0..15 or nothing')
    return upper, lower


def frame(entries, bgp=FADE[-1], footer=None, **state):
    """Row-major shade bytes of the whole 160x144 frame: the background through BGP, then the window, then the pointer.

    `bgp` is the background palette the fade steps through and `scy` the
    slide's scroll; both default to the settled menu, so a frame asked for
    without them is the menu the list shows. The window carries the
    information footer and comes on with the cursor, on the settled frame.
    `footer` names the slots its two rows describe when they have not settled
    on the cursor's own slot yet.
    """
    tiles = bank_tiles()
    # The background is read at a pixel scroll: the splash slides in whole
    # rows, the scroll ramp in SCROLL_STEP pixels, and both wrap the 32-row map.
    scy = state.pop('scy', SETTLED_SCY)
    if not 0 <= scy < 8 * MAP_ROWS:
        raise ValueError('scy is a pixel row of the 32-row map')
    rows = background_map(entries, **state)
    palette = [(bgp >> (2 * shade)) & 3 for shade in range(4)]
    pixels = [palette[tiles[rows[((scy + y) // 8) % MAP_ROWS][x // 8]][(scy + y) % 8][x % 8]]
              for y in range(HEIGHT) for x in range(WIDTH)]
    if window_on(scy):
        cells = window_rows(entries, footer=footer_slots(
                                state.get('cursor', 0), footer,
                                **{key: state[key] for key in ('drawn_slots', 'sdram_ready') if key in state}),
                            **{key: state[key] for key in ('phase', 'result', 'index', 'sdram_ready') if key in state})
        for y in range(WINDOW_Y, HEIGHT):
            for x in range(max(WINDOW_X - 7, 0), WIDTH):
                row, column = y - WINDOW_Y, x - (WINDOW_X - 7)
                shade = tiles[cells[row // 8][column // 8]][row % 8][column % 8]
                pixels[y * WIDTH + x] = palette[shade]
    for left, top, tile in objects(scy=scy, **{key: state[key] for key in ('cursor', 'phase') if key in state}):
        for y in range(8):
            for x in range(8):
                shade = tiles[tile][y][x]
                if shade and 0 <= top + y < HEIGHT and 0 <= left + x < WIDTH:
                    pixels[(top + y) * WIDTH + left + x] = IDENTITY_PALETTE[shade]
    return bytes(pixels)


def unpack(packed):
    if len(packed) != PACKED_BYTES:
        raise ValueError(f'a packed frame has {PACKED_BYTES} bytes')
    return bytes((byte >> shift) & 3 for byte in packed for shift in (0, 2, 4, 6))


def check_pixels(packed, entries, **state):
    """Compare a `host snapshot` frame with the reference; returns the pixel count or raises MENU_PIXEL."""
    actual = unpack(packed)
    expected = frame(entries, **state)
    for position, (want, have) in enumerate(zip(expected, actual)):
        if want != have:
            y, x = divmod(position, WIDTH)
            raise AssertionError(f'MENU_PIXEL x={x} y={y} expected={want} actual={have}')
    return len(actual)


def expected(sample, entries):
    """Named frames for board checks.

    'menu' is the fresh menu; 'cursor-N' the pointer on slot N with its footer
    settled and the list scrolled as that slot asks; 'footer-A-B' the frame
    after a move to slot A whose lower footer row still describes slot B;
    'phase-N' the fresh menu in nudge phase N, which is also the press-A
    badge's pulse phase N; 'footer-15-14' and 'footer-14-15' therefore carry
    the first step of the scroll ramp; 'scroll-N' frame N (1..SCROLL_FRAMES) of the ramp
    toward the last slot with the footer settled on it, so 'scroll-4' is
    'cursor-15'; 'splash-N' the boot splash at displayed frame N.
    """
    if sample == 'menu':
        return frame(entries)
    if sample.startswith('footer-'):
        # The frame after a move from B to A carries the ramp's first step
        # when the move crosses the scroll boundary, and the settled view of A
        # otherwise.
        upper, lower = (int(part) for part in sample.removeprefix('footer-').split('-'))
        ramp = scroll_ramp(scroll_target(lower), upper)
        return frame(entries, cursor=upper, footer=(upper, lower), scy=ramp[0] if ramp else scroll_target(upper))
    if sample.startswith('cursor-'):
        cursor = int(sample.removeprefix('cursor-'))
        return frame(entries, cursor=cursor, scy=scroll_target(cursor))
    if sample.startswith('phase-'):
        return frame(entries, phase=int(sample.removeprefix('phase-')))
    if sample.startswith('scroll-'):
        step = int(sample.removeprefix('scroll-'))
        if not 1 <= step <= SCROLL_FRAMES:
            raise ValueError(f'a scroll frame is 1..{SCROLL_FRAMES}')
        return frame(entries, cursor=SCROLL_SLOT, scy=SETTLED_SCY + SCROLL_STEP * step)
    if sample.startswith('splash-'):
        bgp, scy, wrapped = splash_state(int(sample.removeprefix('splash-')))
        return frame(entries, bgp=bgp, scy=scy, wrapped=wrapped)
    raise ValueError(f'unknown menu sample {sample!r}')


def crc32(pixels):
    return f'{zlib.crc32(pixels):08x}'
