"""Independent menu frame reference: the layout rules of wiki/src/sw/menu/SPEC.md.

The frame is composed from the font's authoritative shade JSON and literal
layout rules, never from the assembled ROM, its tilemap or DUT output. A
catalogue is a list of entries shaped like `n2m.host.library.unpack_entry`
rows: `valid` (int) and `title` (16 bytes); index i is slot i, and an
entry 16 (the menu itself) is ignored. `check_pixels` compares a packed
`host snapshot` frame (5760 bytes, four 2-bit pixels per byte, first pixel
in the low bits) pixel for pixel and names the first mismatch.

The frame is the background map with one object on top: the cursor pointer.
Object shade 0 is transparent, the rest map through OBP0.
"""
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[3]
FONT = ROOT / 'src/sw/menu/assets/font-tiles.json'
GREY_ART = ROOT / 'src/sw/menu/assets/design/v2-grey-tiles.json'
POINTER_ART = ROOT / 'src/sw/menu/assets/design/v2-cursor-tiles.json'
WIDTH, HEIGHT = 160, 144
COLUMNS, ROWS = 20, 18
SLOTS = 16
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
BANK_TILES = 86
# The grey page shade: the font's shade 0 becomes 2, its ink stays 3.
GREY_PAGE = 2
# Cells between the two plate caps of the header and bottom plates.
PLATE_CELLS = COLUMNS - 2
# Frames the cursor holds each nudge phase.
PHASE_HOLD = 16
PHASES = 2
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


def header_row():
    """The header plate: the title on the grey page over the 3-to-2 gradient fill."""
    cells = [TILE_FADE32] * PLATE_CELLS
    cells[HEADER_COLUMN - 1:HEADER_COLUMN - 1 + len(HEADER)] = [TILE_GREY + tile
                                                                for tile in text_tiles(HEADER)]
    return [TILE_CAP_LEFT] + cells + [TILE_CAP_RIGHT]


def tilemap(entries, cursor=0, phase=0, result=RESULT_NONE, index=NO_INDEX, sdram_ready=True, drawn_slots=SLOTS):
    """Visible 20x18 tile indices; `drawn_slots` counts the title rows already drawn on the delayed path.

    The selection is the pointer object, not a map cell, so `cursor` and
    `phase` do not change the background at all; `frame` uses them.
    """
    if not 0 <= cursor < SLOTS:
        raise ValueError('cursor must select a slot 0..15')
    if phase not in range(PHASES):
        raise ValueError('phase must be 0 or 1')
    rows = [[TILE_BLANK] * COLUMNS for _ in range(ROWS)]
    rows[0] = header_row()
    for slot in range(SLOTS):
        row = rows[SLOT_ROW + slot]
        row[NUMBER_COLUMN:NUMBER_COLUMN + 2] = text_tiles(f'{slot:02d}')
        if slot < drawn_slots and slot < len(entries) and entries[slot]['valid'] == 1:
            row[TITLE_COLUMN:TITLE_COLUMN + 16] = title_tiles(entries[slot]['title'])
    rows[STATUS_ROW] = plate(TILE_FADE21, status_text(result, index, sdram_ready).strip())
    return rows


def objects(cursor=0, phase=0, **ignored):
    """The object list: the cursor pointer alone, at screen (0, 8 * (1 + cursor)).

    One object never reaches the ten-per-line limit, and its priority flag is
    clear, so it draws in front of the background wherever its shade is not 0.
    """
    if not 0 <= cursor < SLOTS:
        raise ValueError('cursor must select a slot 0..15')
    if phase not in range(PHASES):
        raise ValueError('phase must be 0 or 1')
    return [(0, 8 * (SLOT_ROW + cursor), TILE_POINTER + phase)]


def phase_of_frame(number):
    """The nudge phase of displayed frame `number`, counted from the menu's first frame."""
    if number < 0:
        raise ValueError('a frame number counts from the menu\'s first frame')
    return number // PHASE_HOLD % PHASES


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
    """The 86-tile bank: font, the font on the grey page, the six grey cells, the two pointer phases."""
    font = font_tiles()
    bank = (font + [greyed(tile) for tile in font]
            + atlas_tiles(GREY_ART, GREY_ART_TILES) + atlas_tiles(POINTER_ART, POINTER_TILES))
    if len(bank) != BANK_TILES:
        raise ValueError('the menu bank is 86 tiles')
    return bank


def frame(entries, **state):
    """Row-major shade bytes of the whole 160x144 frame: the background, then the pointer."""
    tiles = bank_tiles()
    rows = tilemap(entries, **state)
    pixels = [tiles[rows[y // 8][x // 8]][y % 8][x % 8] for y in range(HEIGHT) for x in range(WIDTH)]
    for left, top, tile in objects(**{key: state[key] for key in ('cursor', 'phase') if key in state}):
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
    """Named frames for board checks: 'menu' is the fresh menu, 'cursor-N' the pointer on slot N, 'phase-N' the fresh menu in nudge phase N."""
    if sample == 'menu':
        return frame(entries)
    if sample.startswith('cursor-'):
        return frame(entries, cursor=int(sample.removeprefix('cursor-')))
    if sample.startswith('phase-'):
        return frame(entries, phase=int(sample.removeprefix('phase-')))
    raise ValueError(f'unknown menu sample {sample!r}')


def crc32(pixels):
    return f'{zlib.crc32(pixels):08x}'
