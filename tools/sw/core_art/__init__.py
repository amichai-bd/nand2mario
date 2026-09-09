"""Reproduce the approved Springtrail core artwork with the shared pixel renderer."""
import argparse
import hashlib
import platform
import subprocess
import json
import re
from pathlib import Path
from tools.sw.preview import render, png, svg, GLYPHS, PALETTE, CHECKER
from tools.sw.assets import validate_shades, encode_shades

def reconstruct(bank, mapping):
    """Validate tile references and reconstruct an exact shade image."""
    validate_shades(bank)
    if bank['height'] != 8:
        raise ValueError('tile bank must be one tile high')
    w, h = (mapping['width'], mapping['height'])
    if type(w) is not int or type(h) is not int or w <= 0 or (h <= 0) or w % 8 or h % 8:
        raise ValueError('asset dimensions must be positive multiples of eight')
    pixels = [[0] * w for _ in range(h)]
    positions = set()
    for p in mapping['pieces']:
        x, y, tile = (p['x'], p['y'], p['tile'])
        if any((type(v) is not int for v in (x, y, tile))) or not 0 <= tile < bank['width'] // 8:
            raise ValueError('invalid tile reference')
        if x % 8 or y % 8 or (not (0 <= x <= w - 8 and 0 <= y <= h - 8)) or ((x, y) in positions):
            raise ValueError('invalid or overlapping tile placement')
        positions.add((x, y))
        xf, yf = (p.get('x_flip', False), p.get('y_flip', False))
        if type(xf) is not bool or type(yf) is not bool:
            raise ValueError('flip flags must be boolean')
        rows = [r[8 * tile:8 * tile + 8] for r in bank['pixels']]
        if yf:
            rows = rows[::-1]
        for dy, row in enumerate(rows):
            pixels[y + dy][x:x + 8] = row[::-1] if xf else row
    if len(positions) != w * h // 64:
        raise ValueError('asset map must cover every tile')
    data = dict(schema_version=1, width=w, height=h, pixels=pixels)
    validate_shades(data)
    return data

def load_assets(root):
    owner = root / 'src/sw/springtrail/assets'
    assets, banks, maps = ({}, {}, {})
    for group in ('core', 'terrain', 'enemies'):
        banks[group] = json.loads((owner / 'core' / f'{group}-tiles.json').read_text())
        maps[group] = json.loads((owner / 'core' / f'{group}-maps.json').read_text())
        assets[group] = {k: reconstruct(banks[group], v) for k, v in maps[group].items()}
    courier = json.loads((owner / 'courier/unique-tiles.json').read_text())
    poses = json.loads((owner / 'courier/poses.json').read_text())
    for form, height in [('small', 16), ('large', 24)]:
        for name, pieces in poses[form].items():
            assets['core'][form + '-' + name.lower()] = reconstruct(courier, dict(width=16, height=height, pieces=pieces))
    return (assets, banks, maps)

def generate(root, out):
    packs, banks, all_maps = load_assets(root)
    assets = packs['core']
    OUT = out
    for group, frames in packs.items():
        folder = out / group
        folder.mkdir()
        for name, data in frames.items():
            (folder / (name + '.json')).write_text(json.dumps(data, separators=(',', ':')) + '\n')
            (folder / (name + '.2bpp')).write_bytes(encode_shades(data))

    def sheet(name, entries, cols=4, scale=5, tiled=False):
        cards = []
        for key, label in entries:
            d = assets[key]
            if tiled:
                a = d['pixels']
                w = d['width']
                h = d['height']
                c = render(d, width=w, height=h, labels=[label])
                for yy in range(h):
                    for xx in range(w):
                        if xx and xx % 8 == 0 or (yy and yy % 8 == 0):
                            c[2 + yy][2 + xx] = (110, 145, 175)
            else:
                c = render(d, width=d['width'], height=d['height'], labels=[label])
            if key.startswith('screen-') or key == 'hud-strip':
                for yy, row in enumerate(d['pixels']):
                    for xx, v in enumerate(row):
                        if v == 0:
                            c[2 + yy][2 + xx] = PALETTE[0]
            cards.append(c)
        cw = max((len(c[0]) for c in cards)) + 3
        ch = max((len(c) for c in cards)) + 3
        canvas = [[(250, 250, 250)] * (cw * cols) for _ in range(ch * ((len(cards) + cols - 1) // cols))]
        for i, c in enumerate(cards):
            for y, row in enumerate(c):
                canvas[i // cols * ch + y][i % cols * cw:i % cols * cw + len(row)] = row
        (OUT / f'{name}.png').write_bytes(png(canvas, scale))
        (OUT / f'{name}.svg').write_bytes(svg(canvas, scale))
    poses = [(form + '-' + pose, form[0].upper() + ' ' + pose.upper()) for form in ['small', 'large'] for pose in ['skid', 'throw', 'hurt', 'crouch']]
    sheet('player-actions', poses, 4, 6)
    names = ['spark-a', 'spark-b', 'dust-a', 'dust-b', 'heart', 'life', 'clock', 'shot-a', 'shot-b']
    sheet('effects-icons', [(n, n.upper()) for n in names], 5, 6)
    sheet('font-tiles', [('glyph-' + ('dash' if c == '-' else c), c) for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'], 10, 5)
    names = ['title', 'level-entry', 'pause', 'time-up', 'game-over', 'clear']
    sheet('progression-screens', [('screen-' + n, n.upper()) for n in names], 3, 2)

    def load(group, key):
        return packs[group][key]['pixels']
    a = [[0] * 160 for _ in range(144)]

    def put(tile, x, y, transparent=True):
        for yy, row in enumerate(tile):
            for xx, v in enumerate(row):
                if (v or not transparent) and 0 <= x + xx < 160 and (0 <= y + yy < 144):
                    a[y + yy][x + xx] = v
    put(load('core', 'hud-strip'), 0, 0, False)
    put(load('terrain', 'cloud'), 12, 28)
    put(load('terrain', 'cloud'), 88, 24)
    put(load('terrain', 'bush'), 4, 112)
    put(load('terrain', 'bush'), 100, 112)
    put(load('terrain', 'arch'), 128, 96)
    for x in range(0, 160, 8):
        put(load('terrain', 'sod'), x, 128, False)
        put(load('terrain', 'soil'), x, 136, False)
    put(load('terrain', 'sealed'), 48, 64)
    put(load('terrain', 'used'), 64, 64)
    put(load('terrain', 'coin1'), 56, 40)
    put(load('terrain', 'leaf'), 90, 70)
    put(load('enemies', 'PLATFORM SOLID'), 88, 88)
    put(load('enemies', 'POD FLAP1'), 122, 56)
    put(load('core', 'large-walk1'), 28, 104)
    put(load('enemies', 'BEETLE WALK1'), 96, 112)
    d = {'schema_version': 1, 'width': 160, 'height': 144, 'pixels': a}
    validate_shades(d)
    encode_shades(d)
    (OUT / 'scene-preview.json').write_text(json.dumps(d), encoding='utf-8')
    c = [[PALETTE[v] for v in row] for row in a]
    (OUT / 'scene-preview.png').write_bytes(png(c, 5))
    (OUT / 'scene-preview.svg').write_bytes(svg(c, 5))
    names = ['sod', 'soil', 'brick', 'stone', 'ledge', 'post', 'ridge', 'hill', 'water', 'spike', 'sealed', 'used', 'crack', 'reveal', 'shards', 'coin1', 'coin2', 'leaf', 'gem', 'spark']
    cards = []
    for key in names:
        b = packs['terrain'][key]
        cards.append(render(b, width=b['width'], height=b['height'], labels=[key.upper()]))
    cw = 30
    ch = 28
    cols = 5
    canvas = [[(250, 250, 250)] * (cw * cols) for _ in range(ch * 4)]
    for i, c in enumerate(cards):
        for yy, row in enumerate(c):
            canvas[i // cols * ch + yy][i % cols * cw:i % cols * cw + len(row)] = row
    (OUT / 'terrain-items-review.png').write_bytes(png(canvas, 6))
    (OUT / 'terrain-items-review.svg').write_bytes(svg(canvas, 6))
    assets = packs['enemies']
    maps = all_maps['enemies']
    bank = banks['enemies']
    tiles = [[r[x:x + 8] for r in bank['pixels']] for x in range(0, bank['width'], 8)]

    def text(c, s, x, y):
        for i, ch in enumerate(s):
            for j, b in enumerate(GLYPHS[ch]):
                if b == '1':
                    c[y + j // 3][x + i * 4 + j % 3] = PALETTE[3]

    def save(name, c, scale=6):
        (OUT / (name + '.png')).write_bytes(png(c, scale))
        (OUT / (name + '.svg')).write_bytes(svg(c, scale))
    groups = [['BEETLE WALK1', 'BEETLE WALK2', 'BEETLE STOMP1', 'BEETLE STOMP2'], ['POD FLAP1', 'POD FLAP2', 'CURL DORMANT', 'CURL ACTIVE'], ['PLATFORM SOLID', 'PLATFORM CRACK1', 'PLATFORM CRACK2'], ['PUFF1', 'PUFF2']]
    c = [[(250, 250, 250)] * 270 for _ in range(202)]
    text(c, 'ORIGINAL ENEMIES AND PLATFORMS - DRAFT', 3, 3)
    for row, names in enumerate(groups):
        top = 14 + row * 46
        for col, name in enumerate(names):
            d = assets[name]
            left = 3 + col * 66
            text(c, name, left, top)
            assembled = render(d, d['width'], d['height'], scale=1)
            for y, line in enumerate(assembled):
                c[top + 8 + y][left:left + len(line)] = line
            for p in maps[name]['pieces']:
                dx = left + 30 + p['x'] + p['x'] // 8
                dy = top + 10 + p['y'] + p['y'] // 8
                for y, tr in enumerate([line[p['x']:p['x']+8] for line in d['pixels'][p['y']:p['y']+8]]):
                    for x, s in enumerate(tr):
                        c[dy + y][dx + x] = PALETTE[s] if s else CHECKER[(x // 2 + y // 2) % 2]
            for ty in range(d['height'] // 8):
                ids = [p['tile'] for p in maps[name]['pieces'] if p['y'] == ty * 8]
                text(c, ' '.join((f'{i:02}' for i in ids)), left + 30, top + 30 + ty * 6)
    text(c, 'LEFT ASSEMBLED - RIGHT 8X8 TILES AND IDS', 3, 199 - 5)
    save('enemies-platforms-review', c)

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
    out = folder / 'core-art'
    out.mkdir()
    generate(root, out)
    sources = list((root/'src/sw/springtrail/assets/core').glob('*.json'))
    sources += list((root/'src/sw/springtrail/assets/courier').glob('*.json'))
    sources += [Path(__file__), root/'tools/sw/preview/__init__.py', root/'tools/sw/assets.py']
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(status='PASS', python=platform.python_version(),
                  commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
                  inputs={p.relative_to(root).as_posix():digest(p) for p in sources},
                  outputs={p.relative_to(out).as_posix():digest(p) for p in out.rglob('*') if p.is_file()})
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out)
if __name__ == '__main__':
    main()
