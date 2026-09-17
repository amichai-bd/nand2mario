"""Render the menu design directions of wiki/src/sw/menu/DESIGN.md as 160x144 screens.

The committed shade JSON under `src/sw/menu/assets/design/` owns the new pixels and
`src/sw/menu/assets/font-tiles.json` the shared glyphs; this helper owns the review
layouts, the sample catalogue and the animation phases. Nothing here is built, run or
loaded by the menu image: these are design proposals for the owner to choose from.
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
from tools.sw.preview import PALETTE, png, svg
from tools.sw.program_art import bank_sheet, card, compose, grid, load_module

SCREEN_SCALE = 3
BANK_COLUMNS = 8
FONT_TILES = 39
IDENTITY_BGP, INVERTED_BGP = 0xE4, 0x1B
# Sample library for the review screens: our own images, empty slots and a listed
# entry whose selection is refused, so every row state appears in one screen.
SAMPLE = ['SPRINGTRAIL', 'EXIT DEMO', 'STACKDROP', '', 'TILE PARADE', 'BOUNCE LAB',
          'SCROLL TEST', 'PATTERN 01', '', 'KEY TEST', 'FRAME TIMER', '', 'DEMO REEL',
          '', 'SOUND STUB', '']
# Each direction is reviewed in the same three states: the fresh list, the next
# animation phase, and a refused selection deep in the list.
STATES = (('list', dict(cursor=2, phase=0)),
          ('phase', dict(cursor=2, phase=1)),
          ('refused', dict(cursor=13, phase=0, result=2, index=13)))


def entries():
    return [{'valid': 1 if title else 0, 'title': title.encode('ascii').ljust(16, b'\0')}
            for title in SAMPLE]


def load_bank(root, name):
    data = json.loads((root / 'src/sw/menu/assets' / name).read_text(encoding='utf-8'))
    return validate_shades(data)


def tiles_of(bank):
    return [[row[8 * i:8 * i + 8] for row in bank['pixels']] for i in range(bank['width'] // 8)]


def bank_from(tiles):
    return validate_shades(dict(schema_version=1, width=8 * len(tiles), height=8,
                                pixels=[[v for tile in tiles for v in tile[y]] for y in range(8)]))


def inverted(tile):
    return [[3 - v for v in row] for row in tile]


def blank_cells(tile):
    return [[tile] * 20 for _ in range(18)]


def place(row, column, cells):
    row[column:column + len(cells)] = cells


def direction_a(root, reference):
    """Plated list: inverted header and footer plates, a full-row inverse highlight bar."""
    font = tiles_of(load_bank(root, 'font-tiles.json'))
    extra = tiles_of(load_bank(root, 'design/direction-a-tiles.json'))
    nudge, plate_l, plate_r = extra
    tiles = font + [inverted(t) for t in font] + [nudge, plate_l, plate_r, inverted(nudge)]
    names = ['ARROW NUDGE', 'PLATE LEFT', 'PLATE RIGHT']
    INVERSE, PLATE_L, PLATE_R, NUDGE_INV = 39, 79, 80, 81

    def cells(cursor=0, phase=0, result=0, index=255):
        rows = blank_cells(reference.TILE_BLANK)
        rows[0] = [PLATE_L] + [INVERSE + reference.TILE_BLANK] * 18 + [PLATE_R]
        place(rows[0], 4, [INVERSE + t for t in reference.text_tiles('GAME LIBRARY')])
        catalogue = entries()
        for slot, entry in enumerate(catalogue):
            row = rows[1 + slot]
            place(row, 1, reference.text_tiles(f'{slot:02d}'))
            if entry['valid']:
                place(row, 4, reference.title_tiles(entry['title']))
            if slot == cursor:
                rows[1 + slot] = [INVERSE + tile for tile in row]
                rows[1 + slot][0] = NUDGE_INV if phase else INVERSE + reference.TILE_ARROW
        text = reference.status_text(result, index).strip().center(18)
        rows[17] = ([PLATE_L] + [INVERSE + t for t in reference.text_tiles(text)] + [PLATE_R])
        return rows
    return bank_from(tiles), names, cells, IDENTITY_BGP


def direction_b(root, reference):
    """Cartridge shelf: a two-row emblem header, a framed twelve-row window and a hint bar."""
    font = tiles_of(load_bank(root, 'font-tiles.json'))
    extra = tiles_of(load_bank(root, 'design/direction-b-tiles.json'))
    tiles = font + extra
    names = ['LOGO TL', 'LOGO T', 'LOGO TR', 'LOGO BL', 'LOGO B', 'LOGO BR',
             'BOX TL', 'BOX T', 'BOX TR', 'BOX L', 'BOX R', 'BOX BL', 'BOX B', 'BOX BR',
             'CART FULL', 'CART EMPTY', 'MORE UP', 'MORE DOWN', 'PICK LEFT']
    LOGO = FONT_TILES
    BOX_TL, BOX_T, BOX_TR, BOX_L, BOX_R, BOX_BL, BOX_B, BOX_BR = range(LOGO + 6, LOGO + 14)
    CART_FULL, CART_EMPTY, MORE_UP, MORE_DOWN, PICK_L = range(LOGO + 14, LOGO + 19)
    WINDOW = 12

    def cells(cursor=0, phase=0, result=0, index=255):
        rows = blank_cells(reference.TILE_BLANK)
        # The emblem repeats its middle tile across both of its four-cell rows.
        place(rows[0], 1, [LOGO, LOGO + 1, LOGO + 1, LOGO + 2])
        place(rows[1], 1, [LOGO + 3, LOGO + 4, LOGO + 4, LOGO + 5])
        place(rows[1], 6, reference.text_tiles('GAME LIBRARY'))
        top = min(max(cursor - WINDOW // 2, 0), 16 - WINDOW)
        rows[2] = [BOX_TL] + [BOX_T] * 18 + [BOX_TR]
        rows[15] = [BOX_BL] + [BOX_B] * 18 + [BOX_BR]
        if top:
            rows[2][18] = MORE_UP
        if top + WINDOW < 16:
            rows[15][18] = MORE_DOWN
        catalogue = entries()
        for line in range(WINDOW):
            slot = top + line
            row = rows[3 + line]
            row[0], row[19] = BOX_L, BOX_R
            row[1] = CART_FULL if catalogue[slot]['valid'] else CART_EMPTY
            if slot == cursor and not phase:
                row[2] = PICK_L
            if catalogue[slot]['valid']:
                place(row, 3, reference.title_tiles(catalogue[slot]['title']))
        place(rows[16], 2, reference.text_tiles(f'SLOT {cursor:02d}  A START'))
        rows[17] = reference.text_tiles(reference.status_text(result, index))
        return rows
    return bank_from(tiles), names, cells, IDENTITY_BGP


def direction_c(root, reference):
    """Night deck: the inverted palette, a pulsing power dot and a four-phase caret."""
    font = tiles_of(load_bank(root, 'font-tiles.json'))
    extra = tiles_of(load_bank(root, 'design/direction-c-tiles.json'))
    tiles = font + extra
    names = ['CARET 0', 'CARET 1', 'CARET 2', 'CARET 3', 'TAG LEFT', 'TAG RIGHT',
             'LED 0', 'LED 1', 'LED 2', 'RULE']
    CARET = FONT_TILES
    TAG_L, TAG_R, LED, RULE = CARET + 4, CARET + 5, CARET + 6, CARET + 9

    def cells(cursor=0, phase=0, result=0, index=255):
        rows = blank_cells(reference.TILE_BLANK)
        rows[0][0] = LED + phase % 3
        place(rows[0], 4, reference.text_tiles('GAME LIBRARY'))
        catalogue = entries()
        for slot, entry in enumerate(catalogue):
            row = rows[1 + slot]
            place(row, 1, reference.text_tiles(f'{slot:02d}'))
            if entry['valid']:
                place(row, 4, reference.title_tiles(entry['title']))
            if slot == cursor:
                row[0] = CARET + phase % 4
                row[3] = TAG_L
                row[19] = TAG_R if row[19] == reference.TILE_BLANK else row[19]
        text = reference.status_text(result, index)
        rows[17] = [RULE] * 20 if not text.strip() else reference.text_tiles(text)
        return rows
    return bank_from(tiles), names, cells, INVERTED_BGP


DIRECTIONS = {'a-plated-list': (direction_a, 'direction-a-tiles.json'),
              'b-cartridge-shelf': (direction_b, 'direction-b-tiles.json'),
              'c-night-deck': (direction_c, 'direction-c-tiles.json')}


def generate(root, out):
    reference = load_module('menu_reference', root / 'src/dv/menu/reference.py')
    summary = {}
    for name, (build, source) in DIRECTIONS.items():
        bank, names, cells, bgp = build(root, reference)
        authored = load_bank(root, f'design/{source}')
        folder = out / name
        folder.mkdir(parents=True)
        screens, cards = {}, []
        for state, options in STATES:
            screens[state] = compose(bank, cells(**options), 20, 18, bgp)
            cards.append(card(screens[state], state.upper(), False))
        views = {'screens': (grid(cards, len(cards)), SCREEN_SCALE),
                 'new-art': (bank_sheet(authored, names, BANK_COLUMNS), 6)}
        (folder / 'tile-bank.json').write_text(json.dumps(bank, separators=(',', ':')) + '\n',
                                               encoding='utf-8', newline='\n')
        (folder / 'tile-bank.2bpp').write_bytes(encode_shades(bank))
        for state, data in screens.items():
            (folder / f'{state}.json').write_text(json.dumps(data, separators=(',', ':')) + '\n',
                                                  encoding='utf-8', newline='\n')
        for view, (canvas, scale) in views.items():
            (folder / f'{view}.png').write_bytes(png(canvas, scale))
            (folder / f'{view}.svg').write_bytes(svg(canvas, scale))
        added = bank['width'] // 8 - FONT_TILES
        summary[name] = {'tiles': bank['width'] // 8, 'authored_tiles': authored['width'] // 8,
                         'added_tiles': added, 'added_bytes': 16 * added, 'bgp': bgp}
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
    out = folder / 'menu-art'
    out.mkdir()
    generate(root, out)
    sources = [root / 'src/sw/menu/assets/font-tiles.json', root / 'src/dv/menu/reference.py',
               Path(__file__), root / 'tools/sw/preview/__init__.py',
               root / 'tools/sw/program_art/__init__.py', root / 'tools/sw/assets.py']
    sources += sorted((root / 'src/sw/menu/assets/design').glob('*.json'))
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
