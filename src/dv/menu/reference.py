"""Independent menu frame reference: the layout rules of wiki/src/sw/menu/SPEC.md.

The frame is composed from the font's authoritative shade JSON and literal
layout rules, never from the assembled ROM, its tilemap or DUT output. A
catalogue is a list of entries shaped like `n2m.host.library.unpack_entry`
rows: `valid` (int) and `title` (16 bytes); index i is slot i, and an
entry 16 (the menu itself) is ignored. `check_pixels` compares a packed
`host snapshot` frame (5760 bytes, four 2-bit pixels per byte, first pixel
in the low bits) pixel for pixel and names the first mismatch.
"""
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parents[3]
FONT = ROOT / 'src/sw/menu/assets/font-tiles.json'
WIDTH, HEIGHT = 160, 144
COLUMNS, ROWS = 20, 18
SLOTS = 16
PACKED_BYTES = WIDTH * HEIGHT // 4
# Font atlas order: A-Z, 0-9, dash, blank, cursor arrow.
TILE_DIGIT, TILE_DASH, TILE_BLANK, TILE_ARROW = 26, 36, 37, 38
# Header 0x143 values that mark a 15-byte title: the CGB flag and CGB-only flag.
CGB_FLAG, CGB_ONLY = 0x80, 0xC0
HEADER, HEADER_COLUMN = 'GAME LIBRARY', 4
SLOT_ROW, NUMBER_COLUMN, TITLE_COLUMN, STATUS_ROW = 1, 1, 4, 17
RESULT_NONE, RESULT_OK, RESULT_INVALID_SLOT, RESULT_CRC_MISMATCH, RESULT_NOT_READY = 0, 1, 2, 3, 4
WORDS = {RESULT_INVALID_SLOT: 'INVALID', RESULT_CRC_MISMATCH: 'BAD CRC', RESULT_NOT_READY: 'NOT READY'}
NO_INDEX = 255


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


def tilemap(entries, cursor=0, result=RESULT_NONE, index=NO_INDEX, sdram_ready=True, drawn_slots=SLOTS):
    """Visible 20x18 tile indices; `drawn_slots` counts the title rows already drawn on the delayed path."""
    if not 0 <= cursor < SLOTS:
        raise ValueError('cursor must select a slot 0..15')
    rows = [[TILE_BLANK] * COLUMNS for _ in range(ROWS)]
    rows[0][HEADER_COLUMN:HEADER_COLUMN + len(HEADER)] = text_tiles(HEADER)
    for slot in range(SLOTS):
        row = rows[SLOT_ROW + slot]
        row[NUMBER_COLUMN:NUMBER_COLUMN + 2] = text_tiles(f'{slot:02d}')
        if slot < drawn_slots and slot < len(entries) and entries[slot]['valid'] == 1:
            row[TITLE_COLUMN:TITLE_COLUMN + 16] = title_tiles(entries[slot]['title'])
    rows[SLOT_ROW + cursor][0] = TILE_ARROW
    rows[STATUS_ROW] = text_tiles(status_text(result, index, sdram_ready))
    return rows


def font_tiles():
    """The 39 font tiles as rows of shades, from the asset's authoritative shade JSON."""
    atlas = json.loads(FONT.read_text(encoding='utf-8'))
    if atlas['schema_version'] != 1 or atlas['height'] != 8 or atlas['width'] != 39 * 8:
        raise ValueError('menu font atlas must be one row of 39 tiles')
    return [[atlas['pixels'][y][tile * 8:tile * 8 + 8] for y in range(8)] for tile in range(39)]


def frame(entries, **state):
    """Row-major shade bytes of the whole 160x144 frame, identity BGP, no scroll."""
    tiles = font_tiles()
    rows = tilemap(entries, **state)
    return bytes(tiles[rows[y // 8][x // 8]][y % 8][x % 8] for y in range(HEIGHT) for x in range(WIDTH))


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
    """Named frames for board checks: 'menu' is the fresh menu; 'cursor-N' the cursor on slot N."""
    if sample == 'menu':
        return frame(entries)
    if sample.startswith('cursor-'):
        return frame(entries, cursor=int(sample.removeprefix('cursor-')))
    raise ValueError(f'unknown menu sample {sample!r}')


def crc32(pixels):
    return f'{zlib.crc32(pixels):08x}'
