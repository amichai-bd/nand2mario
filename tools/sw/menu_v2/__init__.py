"""Render the menu v2 ideas of wiki/src/sw/menu/DESIGN_V2.md as 160x144 screens.

The committed shade JSON under `src/sw/menu/assets/design/v2-*.json` owns the new
pixels and this helper owns the review layouts, the sample catalogue and the
animation phases. Nothing is assembled, built or run.

Every sheet is drawn over the 82-tile plated list the menu loaded when the ideas
were published, which this module pins below. The shipped bank has moved on since:
`src/dv/menu/reference.py` owns what the image draws now, and these sheets stay as
the proposals the composite decision was made from, so they must keep reproducing
byte for byte. Only the glyph mapping and the status text come from the reference,
and those rules are unchanged.

Unlike the background-only composer of the first design pass, the frame here is drawn
layer by layer, because the ideas need them: a 32x32 background map at any pixel
scroll, an opaque window from (WX-7, WY) to the bottom right corner, and objects whose
shade 0 is transparent. Background-to-object priority is not modelled; every object
here sits on the page.
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
from tools.sw.assets import encode_shades, validate_shades
from tools.sw.menu_art import IDENTITY_BGP, SAMPLE, bank_from, entries, load_bank, tiles_of
from tools.sw.preview import png, svg
from tools.sw.program_art import bank_sheet, card, grid, load_module

SCREEN_SCALE = 3
BANK_COLUMNS = 8
WIDTH, HEIGHT, COLUMNS, ROWS = 160, 144, 20, 18
MAP_CELLS = 32
# The bank the menu ships today; every idea below adds to it.
SHIPPED_TILES = 82
# Fade steps of the boot splash: page only, then the ink, then the mid shades.
FADE = (0x00, 0x40, 0x90, IDENTITY_BGP)
# The object palette that keeps a dark pointer readable on the inverse bar.
INVERTED_BGP = 0x1B


# The plated list the ideas were drawn over: the 39 font tiles, their inverses,
# the nudged arrow, the two plate caps and the inverse nudged arrow.
PLATED_INVERSE = 39
PLATED_NUDGE, PLATED_CAP_LEFT, PLATED_CAP_RIGHT, PLATED_NUDGE_INVERSE = 78, 79, 80, 81
PLATED_SLOTS = 16
PLATED_HEADER, PLATED_HEADER_COLUMN = 'GAME LIBRARY', 4
PLATED_CELLS = COLUMNS - 2


def invert(tile):
    """The inverse of a tile: every shade becomes 3 - shade."""
    return [[3 - shade for shade in row] for row in tile]


def plated_bank(root, reference):
    """The 82 tiles the menu loaded when these ideas were published."""
    font = reference.font_tiles()
    nudge, left, right = authored(root, 'direction-a-tiles.json')
    bank = font + [invert(tile) for tile in font] + [nudge, left, right, invert(nudge)]
    if len(bank) != SHIPPED_TILES:
        raise ValueError('the plated-list bank is 82 tiles')
    return bank


def plated_plate(reference, cells):
    """A header or status plate: the 18 inverse cells of `cells` between the two caps."""
    return [PLATED_CAP_LEFT] + [PLATED_INVERSE + tile for tile in cells] + [PLATED_CAP_RIGHT]


def plated_tilemap(reference, entries, cursor=0, phase=0, result=0, index=None):
    """The visible 20x18 plated-list cells: header plate, slot rows, inverse bar, status plate."""
    index = reference.NO_INDEX if index is None else index
    rows = [[reference.TILE_BLANK] * COLUMNS for _ in range(ROWS)]
    header = [reference.TILE_BLANK] * PLATED_CELLS
    header[PLATED_HEADER_COLUMN - 1:PLATED_HEADER_COLUMN - 1 + len(PLATED_HEADER)] = \
        reference.text_tiles(PLATED_HEADER)
    rows[0] = plated_plate(reference, header)
    for slot in range(PLATED_SLOTS):
        row = rows[1 + slot]
        row[1:3] = reference.text_tiles(f'{slot:02d}')
        if slot < len(entries) and entries[slot]['valid'] == 1:
            row[4:20] = reference.title_tiles(entries[slot]['title'])
    bar = [PLATED_INVERSE + tile for tile in rows[1 + cursor]]
    bar[0] = PLATED_NUDGE_INVERSE if phase else PLATED_INVERSE + reference.TILE_ARROW
    rows[1 + cursor] = bar
    text = reference.status_text(result, index).strip().center(PLATED_CELLS)
    rows[17] = plated_plate(reference, reference.text_tiles(text))
    return rows


def render(bank, bgmap, bgp, scx=0, scy=0, window=None, wx=7, wy=0, objects=(), obp=IDENTITY_BGP):
    """The 160x144 shade image of one frame: background, then window, then objects."""
    tiles = tiles_of(bank)
    palette = [(bgp >> (2 * i)) & 3 for i in range(4)]
    object_palette = [(obp >> (2 * i)) & 3 for i in range(4)]
    pixels = [[0] * WIDTH for _ in range(HEIGHT)]
    for y in range(HEIGHT):
        for x in range(WIDTH):
            source, sy, sx = bgmap, (y + scy) % (8 * MAP_CELLS), (x + scx) % (8 * MAP_CELLS)
            if window is not None and y >= wy and x >= wx - 7:
                source, sy, sx = window, y - wy, x - (wx - 7)
            pixels[y][x] = palette[tiles[source[sy // 8][sx // 8]][sy % 8][sx % 8]]
    for top, left, tile, flip in objects:
        for y in range(8):
            for x in range(8):
                shade = tiles[tile][y][7 - x if flip else x]
                if shade and 0 <= top + y < HEIGHT and 0 <= left + x < WIDTH:
                    pixels[top + y][left + x] = object_palette[shade]
    return validate_shades(dict(schema_version=1, width=WIDTH, height=HEIGHT, pixels=pixels))


def blank_map(blank, rows=()):
    """A 32x32 background map of `blank`, with `rows` placed at its top left."""
    cells = [[blank] * MAP_CELLS for _ in range(MAP_CELLS)]
    for y, row in enumerate(rows):
        cells[y][:len(row)] = list(row)
    return cells


def place(row, column, cells):
    row[column:column + len(cells)] = cells


def authored(root, name):
    return tiles_of(load_bank(root, f'design/{name}'))


def plate(reference, text):
    """A header or status plate: the 18 inverse cells of `text` between the two caps."""
    return plated_plate(reference, reference.text_tiles(text.center(COLUMNS - 2)))


def splash(root, reference):
    """Boot splash: a badge that fades in through BGP, then the list slides up from below."""
    tiles = plated_bank(root, reference) + authored(root, 'v2-splash-tiles.json')
    names = ['BADGE 0', 'BADGE 1', 'BADGE 2', 'BADGE 3', 'BADGE 4', 'BADGE 5', 'BADGE 6', 'BADGE 7']
    bank, badge = bank_from(tiles), SHIPPED_TILES
    listing = plated_tilemap(reference, entries(), cursor=0)
    screen = [[reference.TILE_BLANK] * COLUMNS for _ in range(ROWS)]
    place(screen[4], 8, [badge + i for i in range(4)])
    place(screen[5], 8, [badge + 4 + i for i in range(4)])
    place(screen[8], 4, reference.text_tiles('GAME LIBRARY'))
    place(screen[10], 3, reference.text_tiles('SELECT A GAME'))
    # The splash sits above the list in one 32-row map, so the slide is an SCY ramp.
    both = blank_map(reference.TILE_BLANK, screen + listing[:14])
    states = [(f'FADE {step}', render(bank, both, bgp)) for step, bgp in enumerate(FADE)]
    states.append(('SLIDE 64PX', render(bank, both, IDENTITY_BGP, scy=64)))
    states.append(('LIST', render(bank, blank_map(reference.TILE_BLANK, listing), IDENTITY_BGP)))
    return bank, names, states


def cursor(root, reference):
    """Sprite cursor: an object pointer in two phases, with and without the inverse bar."""
    tiles = plated_bank(root, reference) + authored(root, 'v2-cursor-tiles.json')
    names = ['POINT 0', 'POINT 1']
    bank, pointer, slot = bank_from(tiles), SHIPPED_TILES, 2
    states = []
    for kept in (True, False):
        for phase in range(2):
            rows = [list(row) for row in plated_tilemap(reference, entries(), cursor=slot)]
            if not kept:
                plain = [tile - PLATED_INVERSE for tile in rows[1 + slot]]
                plain[0] = reference.TILE_BLANK
                rows[1 + slot] = plain
            objects = [(8 * (1 + slot), phase, pointer + phase, False)]
            label = f'{"BAR" if kept else "SPRITE"} PHASE {phase}'
            # Over the inverse bar the pointer needs the inverted object palette to be seen.
            states.append((label, render(bank, blank_map(reference.TILE_BLANK, rows), IDENTITY_BGP,
                                         objects=objects,
                                         obp=INVERTED_BGP if kept else IDENTITY_BGP)))
    return bank, names, states


def footer_rows(reference, badge, text, tagline):
    """The two-row information plate: a cartridge badge with the profile line, then the tagline."""
    top = plated_plate(reference, reference.text_tiles(f'  {text}'.ljust(COLUMNS - 2)))
    top[2] = badge + 2
    return [top, plated_plate(reference, reference.text_tiles(tagline.center(COLUMNS - 2)))]


def footer(root, reference):
    """Info footer: profile, size and a one-line tagline under a fifteen-slot list."""
    art = authored(root, 'v2-footer-tiles.json')
    tiles = plated_bank(root, reference) + art + [invert(tile) for tile in art]
    names = ['CART', 'DOT']
    bank, badge = bank_from(tiles), SHIPPED_TILES
    lines = {2: ('DIRECT   32 KB', 'BRISK PLATFORM HOP'), 3: ('EMPTY SLOT', 'NOTHING LOADED HERE'),
             13: ('EMPTY SLOT', 'NOTHING LOADED HERE')}
    states = []
    for slot, label, refused in ((2, 'INFO FOOTER', 0), (3, 'EMPTY SLOT', 0), (13, 'REFUSED', 2)):
        rows = [list(row) for row in plated_tilemap(reference, entries(), cursor=slot)]
        text, tagline = lines[slot]
        if refused:
            tagline = reference.status_text(refused, slot).strip()
        rows[16:18] = footer_rows(reference, badge, text, tagline)
        states.append((label, render(bank, blank_map(reference.TILE_BLANK, rows), IDENTITY_BGP)))
    return bank, names, states


def stars(root, reference):
    """Moving background: a star band scrolled by SCX/SCY, with everything else on the window."""
    tiles = plated_bank(root, reference) + authored(root, 'v2-stars-tiles.json')
    names = ['STAR A', 'STAR B', 'STAR C', 'SPARK']
    bank, star = bank_from(tiles), SHIPPED_TILES
    # A sparse 32x32 star map: a fixed scatter, so the band never repeats on a short scroll.
    field = blank_map(reference.TILE_BLANK)
    for y in range(MAP_CELLS):
        for x in range(MAP_CELLS):
            if (7 * x + 13 * y + x * y) % 11 == 0:
                field[y][x] = star + (x + y) % 4
    listing = plated_tilemap(reference, entries(), cursor=2)
    # The window is opaque from its top edge down, so the band costs the last two slot rows.
    window = [listing[0]] + listing[1:15] + [listing[17]]
    states = [(f'SCROLL {offset}PX', render(bank, field, IDENTITY_BGP, scx=offset, scy=offset // 2,
                                            window=window, wy=16))
              for offset in (0, 24, 48)]
    return bank, names, states


def grey(root, reference):
    """Mid-grey plates and dithered gradients: a third shade on the header, bar and status row."""
    art = authored(root, 'v2-grey-tiles.json')
    font = reference.font_tiles()
    # The grey bank is the font on a mid-grey page: shade 0 becomes 2, the ink stays 3.
    shaded = [[[2 if shade == 0 else shade for shade in row] for row in tile] for tile in font]
    tiles = plated_bank(root, reference) + shaded + art
    names = ['CAP L GREY', 'CAP R GREY', 'FADE 32', 'FADE 21', 'FADE 10', 'SHADOW']
    bank, shade_bank = bank_from(tiles), SHIPPED_TILES
    cap_l, cap_r, fade32, fade21 = (shade_bank + 39 + i for i in range(4))
    states = []
    for slot, label, refused in ((2, 'GREY PLATES', 0), (5, 'CURSOR ON SLOT 5', 0), (3, 'REFUSED', 2)):
        rows = [list(row) for row in plated_tilemap(reference, entries(), cursor=slot, result=refused,
                                                    index=slot if refused else reference.NO_INDEX)]
        header = [fade32] * (COLUMNS - 2)
        place(header, 3, [shade_bank + tile for tile in reference.text_tiles('GAME LIBRARY')])
        rows[0] = [cap_l] + header + [cap_r]
        rows[1 + slot] = [shade_bank + tile if tile < reference.FONT_TILES else tile
                          for tile in [t - PLATED_INVERSE for t in rows[1 + slot]]]
        rows[1 + slot][0] = shade_bank + reference.TILE_ARROW
        status = reference.status_text(refused, slot if refused else reference.NO_INDEX).strip()
        cells = [fade21] * (COLUMNS - 2)
        if status:
            place(cells, (COLUMNS - 2 - len(status)) // 2,
                  [shade_bank + tile for tile in reference.text_tiles(status)])
        rows[17] = [cap_l] + cells + [cap_r]
        states.append((label, render(bank, blank_map(reference.TILE_BLANK, rows), IDENTITY_BGP)))
    return bank, names, states


def hint(reference, badge, phase):
    """The fixed two-row hint on the window: the slot line and the pulsing press-A line."""
    rows = [plate(reference, 'SLOT 15  DIRECT'), plate(reference, 'PRESS   TO START')]
    rows[1][8] = badge + phase
    return rows


def pulse(root, reference):
    """Smooth scroll and a press-A pulse: the list rides SCY while the hint stays on the window."""
    art = authored(root, 'v2-pulse-tiles.json')
    # The hint sits on an inverse plate, so the badge is stored inverted like the plate text.
    tiles = plated_bank(root, reference) + art + [invert(tile) for tile in art]
    names = ['A DIM', 'A BRIGHT']
    bank, badge = bank_from(tiles), SHIPPED_TILES + 2
    listing = plated_tilemap(reference, entries(), cursor=15)
    field = blank_map(reference.TILE_BLANK, listing[:17])
    states = [(f'SCROLL {offset}PX', render(bank, field, IDENTITY_BGP, scy=offset,
                                            window=hint(reference, badge, 0), wy=8 * 16))
              for offset in (0, 2, 4, 6)]
    states += [(f'PULSE {phase}', render(bank, field, IDENTITY_BGP, scy=8,
                                         window=hint(reference, badge, phase), wy=8 * 16))
               for phase in range(2)]
    return bank, names, states


IDEAS = {'1-boot-splash': (splash, ('v2-splash-tiles.json',)),
         '2-sprite-cursor': (cursor, ('v2-cursor-tiles.json',)),
         '3-info-footer': (footer, ('v2-footer-tiles.json',)),
         '4-moving-background': (stars, ('v2-stars-tiles.json',)),
         '5-grey-plates': (grey, ('v2-grey-tiles.json',)),
         '6-scroll-and-pulse': (pulse, ('v2-pulse-tiles.json',))}


def generate(root, out):
    reference = load_module('menu_reference', root / 'src/dv/menu/reference.py')
    summary = {}
    for name, (build, sources) in IDEAS.items():
        bank, names, states = build(root, reference)
        art = bank_from([tile for source in sources for tile in authored(root, source)])
        folder = out / name
        folder.mkdir(parents=True)
        views = {'screens': (grid([card(image, label, False) for label, image in states],
                                  min(len(states), 3)), SCREEN_SCALE),
                 'new-art': (bank_sheet(art, names, BANK_COLUMNS), 6)}
        (folder / 'tile-bank.json').write_text(json.dumps(bank, separators=(',', ':')) + '\n',
                                               encoding='utf-8', newline='\n')
        (folder / 'tile-bank.2bpp').write_bytes(encode_shades(bank))
        for label, image in states:
            state = label.lower().replace(' ', '-')
            (folder / f'{state}.json').write_text(json.dumps(image, separators=(',', ':')) + '\n',
                                                  encoding='utf-8', newline='\n')
        for view, (canvas, scale) in views.items():
            (folder / f'{view}.png').write_bytes(png(canvas, scale))
            (folder / f'{view}.svg').write_bytes(svg(canvas, scale))
        added = bank['width'] // 8 - SHIPPED_TILES
        summary[name] = {'tiles': bank['width'] // 8, 'authored_tiles': art['width'] // 8,
                         'added_tiles': added, 'added_bytes': 16 * added, 'frames': len(states)}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n',
                                      encoding='utf-8', newline='\n')
    return summary


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
    out = folder / 'menu-v2'
    out.mkdir()
    generate(root, out)
    sources = [root / 'src/sw/menu/assets/font-tiles.json', root / 'src/dv/menu/reference.py',
               Path(__file__), root / 'tools/sw/menu_art/__init__.py',
               root / 'tools/sw/preview/__init__.py', root / 'tools/sw/program_art/__init__.py',
               root / 'tools/sw/assets.py']
    sources += sorted((root / 'src/sw/menu/assets/design').glob('v2-*.json'))
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
