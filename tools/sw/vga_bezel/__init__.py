"""Render 640x480 VGA bezel design directions around the real scaled menu image.

The border outside the scaled image is black today. These are mockups of what a
bezel drawn by the FPGA would look like on the monitor, not RTL and not a change
to the image: `wiki/src/rtl/vga/BEZEL.md` states each direction's RTL approach
and cost. `directions.json` owns the colours and band widths; this module owns
the shapes. Geometry authority is `wiki/src/clocks-resets-cdc.md`: the 160x144
image is scaled three times and centred at x=80..559, y=24..455.
"""
import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.sw.preview import png, svg
from tools.sw.program_art import load_module

WIDTH, HEIGHT = 640, 480
LEFT, TOP, RIGHT, BOTTOM = 80, 24, 560, 456
SOURCE_WIDTH, SCALE = 160, 3
# The scanout's shade conversion: one 4-bit code repeated on all three channels.
SHADE_CODE = (0xF, 0xA, 0x5, 0x0)
# The sample library of the menu previews: our own images and empty slots.
SAMPLE = ['SPRINGTRAIL', 'EXIT DEMO', 'STACKDROP', '', 'TILE PARADE', 'BOUNCE LAB',
          'SCROLL TEST', 'PATTERN 01', '', 'KEY TEST', 'FRAME TIMER', '', 'DEMO REEL',
          '', 'SOUND STUB', '']
CURSOR = 2
SOURCE = Path(__file__).with_name('directions.json')


def code(channels):
    """One editable 4-bit triplet as the 8-bit colour a 4-bit DAC actually shows."""
    if len(channels) != 3 or any(type(v) is not int or not 0 <= v <= 15 for v in channels):
        raise ValueError('a bezel colour is three 4-bit VGA codes')
    return tuple(17 * v for v in channels)


def gray(level):
    return code((level, level, level))


def distance(x, y):
    """Outward Chebyshev distance in screen pixels from the scaled image; 0 inside it."""
    dx = max(LEFT - x, x - (RIGHT - 1), 0)
    dy = max(TOP - y, y - (BOTTOM - 1), 0)
    return max(dx, dy)


def along(x, y):
    """The coordinate that runs along the nearest border band, for repeating marks."""
    return y if LEFT <= x < RIGHT else x


def inside_round(x, y, radius):
    """False only in the four screen corners cut by a rounded outer rectangle."""
    cx = radius - 1 - x if x < radius else x - (WIDTH - radius) if x >= WIDTH - radius else None
    cy = radius - 1 - y if y < radius else y - (HEIGHT - radius) if y >= HEIGHT - radius else None
    if cx is None or cy is None:
        return True
    return (radius - 1 - cx) ** 2 + (radius - 1 - cy) ** 2 <= (radius - 1) ** 2


def disc(x, y, cx, cy, radius):
    return (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2


def shell(spec):
    """Handheld shell: a moulded body, a recessed screen well, an accent stripe and a power dot."""
    well, edge = spec['bands']['well'], spec['bands']['well_edge']
    radius = spec['corner_radius']
    stripes = [code(c) for c in spec['stripe']]

    def pixel(x, y, d):
        if not inside_round(x, y, radius):
            return code(spec['surround'])
        if d <= well:
            return code(spec['well'])
        if d <= edge:
            return code(spec['well_edge'])
        # Bevel the outer rim: light above and left, dark below and right.
        rim = min(x, y, WIDTH - 1 - x, HEIGHT - 1 - y)
        if rim < 3:
            lit = x < WIDTH // 2 if rim in (x, WIDTH - 1 - x) else y < HEIGHT // 2
            return code(spec['body_high'] if lit else spec['body_low'])
        if 12 <= x < 32 and 300 <= y < 452:
            bar = (x - 12) // 7
            if bar < 3 and (x - 12) % 7 < 6:
                return stripes[bar]
        if disc(x, y, 36, 60, 6):
            return code(spec['led'] if disc(x, y, 36, 60, 4) else spec['led_ring'])
        # Slanted speaker grille: one comparator on x+y inside a rectangle.
        if 592 <= x < 632 and 300 <= y < 452 and (x + y) % 12 < 3:
            return code(spec['grille'])
        return code(spec['body'])
    return pixel


def plate(spec, caps):
    """Plated frame: the menu's inverse plate rails and its two plate-cap tiles, scaled three times."""
    gap, hair, inner, rail = (spec['bands'][k] for k in ('gap', 'hairline', 'inner', 'rail'))
    pitch, mark = spec['notch_pitch'], spec['notch_width']
    corners = {(LEFT - 8 * SCALE, TOP - 8 * SCALE): (0, False), (RIGHT, TOP - 8 * SCALE): (1, False),
               (LEFT - 8 * SCALE, BOTTOM): (0, True), (RIGHT, BOTTOM): (1, True)}

    def pixel(x, y, d):
        for (ox, oy), (tile, flip) in corners.items():
            if ox <= x < ox + 8 * SCALE and oy <= y < oy + 8 * SCALE:
                row = (y - oy) // SCALE
                return gray(SHADE_CODE[caps[tile][7 - row if flip else row][(x - ox) // SCALE]])
        if d <= gap:
            return code(spec['field'])
        if d <= hair:
            return code(spec['hairline'])
        if d <= inner:
            return code(spec['field'])
        if d <= rail:
            return code(spec['notch'] if along(x, y) % pitch < mark else spec['rail'])
        return code(spec['field'])
    return pixel


def vignette(spec):
    """Minimal dark vignette: a hairline at the image edge stepping down to black at the rim."""
    steps = [(int(limit), int(level)) for limit, level in spec['steps']]

    def pixel(x, y, d):
        if min(x, y, WIDTH - 1 - x, HEIGHT - 1 - y) < spec['surround']:
            return gray(0)
        for limit, level in steps:
            if d <= limit:
                return gray(level)
        return gray(0)
    return pixel


DIRECTIONS = ('shell', 'plate', 'vignette')
TITLES = {'shell': 'Handheld shell', 'plate': 'Plated frame', 'vignette': 'Dark vignette'}


def menu_frame(root):
    """The current plated-list menu frame as 160x144 shades, from its independent reference."""
    reference = load_module('menu_reference', root / 'src/dv/menu/reference.py')
    entries = [{'valid': 1 if title else 0, 'title': title.encode('ascii').ljust(16, b'\0')}
               for title in SAMPLE]
    return reference.frame(entries, cursor=CURSOR)


def plate_caps(root):
    """The committed plate-cap tiles of menu direction A, as 8x8 shade rows."""
    atlas = json.loads((root / 'src/sw/menu/assets/design/direction-a-tiles.json')
                       .read_text(encoding='utf-8'))
    return [[atlas['pixels'][y][8 * t:8 * t + 8] for y in range(8)] for t in (1, 2)]


def builders(root, spec):
    return {'shell': lambda: shell(spec['shell']),
            'plate': lambda: plate(spec['plate'], plate_caps(root)),
            'vignette': lambda: vignette(spec['vignette'])}


def canvas(frame, pixel):
    """One whole active VGA frame: the untouched scaled image inside, the bezel outside."""
    rows = []
    for y in range(HEIGHT):
        row = []
        for x in range(WIDTH):
            d = distance(x, y)
            if d:
                row.append(pixel(x, y, d))
            else:
                shade = frame[(y - TOP) // SCALE * SOURCE_WIDTH + (x - LEFT) // SCALE]
                row.append(gray(SHADE_CODE[shade]))
        rows.append(row)
    return rows


def cell_keys(rows, cx, cy):
    """One 8x8 screen cell and its three mirrors, so a folded tile ROM can be counted."""
    cell = tuple(tuple(rows[8 * cy + dy][8 * cx + dx] for dx in range(8)) for dy in range(8))
    flip_x = tuple(tuple(reversed(row)) for row in cell)
    return cell, min(cell, flip_x, cell[::-1], flip_x[::-1])


def measure(rows):
    """The cost figures the design note quotes, counted from the rendered frame itself."""
    border = [rows[y][x] for y in range(HEIGHT) for x in range(WIDTH) if distance(x, y)]
    cells, folded = set(), set()
    for cy in range(HEIGHT // 8):
        for cx in range(WIDTH // 8):
            # A cell is a border cell only when all 64 of its pixels are outside the image.
            if distance(8 * cx, 8 * cy) and distance(8 * cx + 7, 8 * cy + 7):
                cell, key = cell_keys(rows, cx, cy)
                cells.add(cell)
                folded.add(key)
    colours = len(set(border))
    index_bits = max(1, (colours - 1).bit_length())
    return {'border_pixels': len(border), 'border_colours': colours,
            'gray_only': all(len(set(c)) == 1 for c in border),
            'lit_pixels': sum(1 for c in border if c != (0, 0, 0)),
            'border_cells': sum(1 for cy in range(HEIGHT // 8) for cx in range(WIDTH // 8)
                                if distance(8 * cx, 8 * cy) and distance(8 * cx + 7, 8 * cy + 7)),
            'unique_cells': len(cells), 'folded_cells': len(folded),
            'index_bits': index_bits, 'tile_rom_bits': 64 * index_bits * len(folded)}


def generate(root, out):
    """Write every direction's frame and return its summary with the rendered canvases."""
    spec = json.loads(SOURCE.read_text(encoding='utf-8'))
    frame = menu_frame(root)
    if len(frame) != SOURCE_WIDTH * 144:
        raise ValueError('the menu reference must supply one 160x144 frame')
    build = builders(root, spec)
    summary, canvases = {}, {}
    for name in DIRECTIONS:
        rows = canvas(frame, build[name]())
        folder = out / name
        folder.mkdir(parents=True)
        (folder / 'frame.svg').write_bytes(svg(rows, 1))
        (folder / 'frame.png').write_bytes(png(rows, 1))
        summary[name], canvases[name] = measure(rows), rows
    (out / 'menu-frame.json').write_text(
        json.dumps({'schema_version': 1, 'width': SOURCE_WIDTH, 'height': 144,
                    'pixels': [list(frame[y * SOURCE_WIDTH:(y + 1) * SOURCE_WIDTH])
                               for y in range(144)]}, separators=(',', ':')) + '\n',
        encoding='utf-8', newline='\n')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8', newline='\n')
    return summary, canvases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', args.tag):
        parser.error('invalid build tag')
    root = Path(__file__).resolve().parents[3]
    folder = root / 'workdir/builds' / args.tag
    if folder.resolve() != folder:
        parser.error('output path traverses a symlink')
    folder.mkdir(parents=True, exist_ok=False)
    out = folder / 'vga-bezel'
    out.mkdir()
    generate(root, out)
    sources = [SOURCE, Path(__file__), root / 'src/dv/menu/reference.py',
               root / 'src/sw/menu/assets/font-tiles.json',
               root / 'src/sw/menu/assets/design/direction-a-tiles.json',
               root / 'tools/sw/preview/__init__.py', root / 'tools/sw/program_art/__init__.py']
    digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(status='PASS', schema_version=1, python=platform.python_version(),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                                 text=True).strip(),
                  inputs={p.relative_to(root).as_posix(): digest(p) for p in sources},
                  outputs={p.relative_to(out).as_posix(): digest(p)
                           for p in sorted(out.rglob('*')) if p.is_file()})
    (out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n',
                                     encoding='utf-8', newline='\n')
    return 0
