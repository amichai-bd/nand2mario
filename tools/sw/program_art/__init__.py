"""Render Stackdrop and v0.5 program previews from built ROM bytes and executed writes."""
import argparse
import hashlib
import importlib.util
import json
import platform
import re
import subprocess
import sys
from pathlib import Path
# The assembler imports the generated `n2m` interface tables from the tools directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.sw.preview import render, png, svg, PALETTE
from tools.sw.assembler import assemble
from tools.sw.linker import link
from tools.sw.package import package
from tools.sw.assets import validate_shades, encode_shades

SCREEN_SCALE = 4
STACKDROP_TILE_NAMES = ['EMPTY', 'BORDER', 'LOCKED', 'ACTIVE', 'TITLE', 'PLAYING', 'GAME OVER',
                        'UNUSED', 'UNUSED', 'UNUSED'] + [f'DIGIT {d}' for d in range(10)]
PIECE_NAMES = 'IOTLJSZ'
# Button bits follow JOYP packing in both programs: Right, Left, Up, Down, A, B, Select, Start.
START, A, B, DOWN, RIGHT, LEFT = 128, 16, 32, 8, 1, 2
# Legal play from a fresh game, one sample per frame; zero samples release each edge.
# Comments name the piece each group of edges steers; the rules model decides the outcome.
PLAY_SCRIPT = ([START, 0]
               + [LEFT, 0, LEFT, 0, B, 0]                 # I: left twice, hard drop
               + [RIGHT, 0, RIGHT, 0, B, 0]               # O: right twice, hard drop
               + [A, 0, LEFT, 0, LEFT, 0, LEFT, 0, B, 0]  # T: rotate, left three times, hard drop
               + [RIGHT, 0, RIGHT, 0, RIGHT, 0, B, 0]     # L: right three times, hard drop
               + [A, 0, A, 0, A, 0, B, 0]                 # J: rotate three times, hard drop
               + [RIGHT, 0, RIGHT, 0, A, 0, B, 0]         # S: right twice, rotate, hard drop
               + [DOWN, 0, DOWN, 0, DOWN, 0])             # Z: soft drop three rows, still falling
V05_INPUT_DOT = 50000  # Inside the first CPU HALT, as in the bounded acceptance window.


def load_module(name, path):
    """Import a DV helper under a private name; both games ship a `reference` module."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(root, name):
    """Assemble, link and package one registered target in memory."""
    registry = json.loads((root / 'src/sw/targets.json').read_text(encoding='utf-8'))
    target = registry['targets'][name]
    tree = root / 'src/sw' / target['directory']
    objects = [assemble(tree / source, tree, root / 'src/sw/generated/interfaces.inc', {})
               for source in target['sources']]
    layout = json.loads((tree / target['layout']).read_text(encoding='utf-8'))
    linked = link(list(zip(target['sources'], objects)), layout, target['entry'], target['profile'])
    rom = package(linked, target['title'], target['version'], target['profile'])
    symbols = {s['symbol']: s['value'] for s in linked['symbols']['symbols']}
    lines = sorted(linked['listing']['lines'], key=lambda line: line['address'])
    return rom, symbols, lines


def port_write(lines, port):
    """Value stored by the last `LDH [$FF<port>],A`: the preceding LD A,n or XOR A, past other stores of A."""
    stores = [i for i, line in enumerate(lines) if line['bytes'] == [0xE0, port]]
    if not stores:
        raise ValueError(f'no write to FF{port:02X}')
    index = stores[-1] - 1
    while lines[index]['bytes'][:1] in ([0xE0], [0xEA]):
        index -= 1
    if lines[index]['bytes'][:1] == [0x3E]:
        return lines[index]['bytes'][1]
    if lines[index]['bytes'] == [0xAF]:
        return 0
    raise ValueError(f'unrecognised source of the FF{port:02X} write')


def decode_tiles(data):
    """2bpp bytes to a one-row strict shade bank."""
    if len(data) % 16:
        raise ValueError('tile data must be whole 8x8 tiles')
    count = len(data) // 16
    pixels = [[0] * (8 * count) for _ in range(8)]
    for tile in range(count):
        for y in range(8):
            low, high = data[tile * 16 + 2 * y], data[tile * 16 + 2 * y + 1]
            for x in range(8):
                pixels[y][tile * 8 + x] = ((low >> (7 - x)) & 1) | (((high >> (7 - x)) & 1) << 1)
    return validate_shades(dict(schema_version=1, width=8 * count, height=8, pixels=pixels))


def compose(bank, cells, columns, rows, bgp):
    """Background tile IDs to a shade image through the BGP palette register."""
    palette = [(bgp >> (2 * i)) & 3 for i in range(4)]
    pixels = [[0] * (8 * columns) for _ in range(8 * rows)]
    for y in range(rows):
        for x in range(columns):
            tile = cells[y][x]
            if not 0 <= tile < bank['width'] // 8:
                raise ValueError(f'map references missing tile {tile}')
            for dy in range(8):
                row = bank['pixels'][dy][8 * tile:8 * tile + 8]
                pixels[8 * y + dy][8 * x:8 * x + 8] = [palette[v] for v in row]
    return validate_shades(dict(schema_version=1, width=8 * columns, height=8 * rows, pixels=pixels))


def screen(bank, vram_map, lcdc, scx, scy, bgp):
    """The 160x144 image of a static background: no window, objects or mid-frame writes."""
    if lcdc & 0x91 != 0x91 or lcdc & 0x08 or lcdc & 0x22:
        raise ValueError('preview supports LCD on, BG on, $8000 tiles, $9800 map, no window/objects')
    if scx % 8 or scy % 8:
        raise ValueError('preview supports tile-aligned scroll only')
    cells = [[vram_map[((scy // 8 + y) % 32) * 32 + (scx // 8 + x) % 32] for x in range(20)]
             for y in range(18)]
    return compose(bank, cells, 20, 18, bgp)


def card(data, label, transparent):
    canvas = render(data, width=data['width'], height=data['height'], labels=[label])
    if not transparent:
        for y, row in enumerate(data['pixels']):
            for x, v in enumerate(row):
                if v == 0:
                    canvas[2 + y][2 + x] = PALETTE[0]
    return canvas


def grid(cards, cols):
    cw = max(len(c[0]) for c in cards) + 3
    ch = max(len(c) for c in cards) + 3
    canvas = [[(250, 250, 250)] * (cw * cols) for _ in range(ch * ((len(cards) + cols - 1) // cols))]
    for i, c in enumerate(cards):
        for y, row in enumerate(c):
            canvas[i // cols * ch + y][i % cols * cw:i % cols * cw + len(row)] = row
    return canvas


def bank_sheet(bank, names, cols):
    tiles = [validate_shades(dict(schema_version=1, width=8, height=8,
                                  pixels=[row[8 * i:8 * i + 8] for row in bank['pixels']]))
             for i in range(bank['width'] // 8)]
    return grid([card(t, f'{i:02} {n}', True) for i, (t, n) in enumerate(zip(tiles, names))], cols)


def stackdrop_prepare(shapes, game):
    """Mirror Prepare: the 118 tile IDs the game writes each VBlank, from the ROM shape table."""
    image = [2 * v for v in game.board] + [0] * 16
    if game.status == 1:
        for cell in shapes[game.piece * 16 + game.rotation * 4:][:4]:
            image[(game.y + (cell >> 4)) * 8 + game.x + (cell & 15)] = 3
    following = (game.piece + 1) % 7
    for cell in shapes[following * 16:following * 16 + 4]:
        image[96 + (cell >> 4) * 4 + (cell & 15)] = 3
    return image + [10 + int(d) for d in f'{game.score:04d}'] + [4 + game.status, 10 + game.rotation]


def stackdrop_map(rom, symbols, image):
    """Mirror Render: the initial map with the prepared image copied to its VRAM windows."""
    vram_map = list(rom[symbols['Map']:symbols['Map'] + 1024])
    for i in range(96):
        vram_map[0x66 + (i // 8) * 32 + i % 8] = image[i]
    for i in range(16):
        vram_map[0x8F + (i // 4) * 32 + i % 4] = image[96 + i]
    for i in range(4):
        vram_map[0x208 + i] = image[112 + i]
    vram_map[0x44], vram_map[0x64] = image[116], image[117]
    return vram_map


def stackdrop(root, out):
    rom, symbols, lines = build(root, 'stackdrop')
    bank = decode_tiles(rom[symbols['Tiles']:symbols['Tiles'] + 320])
    shapes = rom[symbols['Shapes']:symbols['Shapes'] + 112]
    registers = {port: port_write(lines, port) for port in (0x40, 0x42, 0x43, 0x47)}
    reference = load_module('n2m_stackdrop_reference', root / 'src/dv/stackdrop/reference.py')
    title = reference.Game()
    play = reference.Game()
    for buttons in PLAY_SCRIPT:
        play.update(buttons)
    if play.status != 1:
        raise ValueError('play script must end during play')
    pieces = []
    for rotation in range(4):
        for piece in range(7):
            cells = [[0] * 4 for _ in range(4)]
            for cell in shapes[piece * 16 + rotation * 4:][:4]:
                cells[cell >> 4][cell & 15] = 3
            pieces.append(card(compose(bank, cells, 4, 4, registers[0x47]),
                               f'{PIECE_NAMES[piece]} R{rotation}', False))
    views = {'tile-bank': (bank_sheet(bank, STACKDROP_TILE_NAMES, 5), 8),
             'pieces': (grid(pieces, 7), 4)}
    frames = {}
    for name, game in (('title', title), ('play', play)):
        image = stackdrop_prepare(shapes, game)
        frames[name] = screen(bank, stackdrop_map(rom, symbols, image), registers[0x40],
                              registers[0x43], registers[0x42], registers[0x47])
        views[name] = ([[PALETTE[v] for v in row] for row in frames[name]['pixels']], SCREEN_SCALE)
    save(out, 'stackdrop', bank, views, frames)


def v05_writes(root, rom, mask):
    """Run the literal instruction recipe and return every program write."""
    reference = load_module('n2m_v05_reference', root / 'src/dv/v05/reference.py')
    for pc, instruction in reference.Reference().instructions.items():
        if rom[pc:pc + len(bytes.fromhex(instruction['bytes']))] != bytes.fromhex(instruction['bytes']):
            raise ValueError(f'v0.5 recipe differs from the built ROM at {pc:04X}')
    model = reference.Reference([(V05_INPUT_DOT, mask)] if mask else [])
    for _ in model.records(reference.BOUNDED_END):
        pass
    return model.writes


def v05(root, out):
    rom, _, _ = build(root, 'v05')
    views, frames, bank = {}, {}, None
    for name, mask in (('idle', 0), ('right-a', 0x11), ('all-buttons', 0xFF)):
        tiles, vram_map, registers = {}, [None] * 1024, {}
        for _, address, value in v05_writes(root, rom, mask):
            if 0x8000 <= address < 0x9800:
                tiles[address - 0x8000] = value
            elif 0x9800 <= address < 0x9C00:
                vram_map[address - 0x9800] = value
            elif 0xFF40 <= address <= 0xFF47:
                registers[address & 0xFF] = value
        count = max(tiles) // 16 + 1
        if set(tiles) != set(range(16 * count)) or None in vram_map:
            raise ValueError('program must write every previewed tile byte and map cell')
        bank = decode_tiles(bytes(tiles[i] for i in range(16 * count)))
        frames[name] = screen(bank, vram_map, registers[0x40], registers[0x43], registers[0x42], registers[0x47])
        views[name] = ([[PALETTE[v] for v in row] for row in frames[name]['pixels']], SCREEN_SCALE)
    views['tile-bank'] = (bank_sheet(bank, ['CLEAR', 'MARKED'], 2), 8)
    save(out, 'v05', bank, views, frames)


def save(out, name, bank, views, frames):
    folder = out / name
    folder.mkdir()
    (folder / 'tile-bank.json').write_text(json.dumps(bank, separators=(',', ':')) + '\n', encoding='utf-8')
    (folder / 'tile-bank.2bpp').write_bytes(encode_shades(bank))
    for view, data in frames.items():
        (folder / f'{view}.json').write_text(json.dumps(data, separators=(',', ':')) + '\n', encoding='utf-8')
    for view, (canvas, scale) in views.items():
        (folder / f'{view}.png').write_bytes(png(canvas, scale))
        (folder / f'{view}.svg').write_bytes(svg(canvas, scale))


def generate(root, out):
    stackdrop(root, out)
    v05(root, out)


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
    out = folder / 'program-art'
    out.mkdir()
    generate(root, out)
    sources = [root / 'src/sw/targets.json', root / 'src/dv/stackdrop/reference.py',
               root / 'src/dv/v05/reference.py', root / 'src/dv/v05/program.json',
               Path(__file__), root / 'tools/sw/preview/__init__.py', root / 'tools/sw/assets.py']
    sources += sorted(p for game in ('stackdrop', 'v05') for p in (root / 'src/sw' / game).glob('*')
                      if p.suffix in ('.asm', '.json'))
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    report = dict(status='PASS', python=platform.python_version(),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
                  inputs={p.relative_to(root).as_posix(): digest(p) for p in sources},
                  outputs={p.relative_to(out).as_posix(): digest(p) for p in sorted(out.rglob('*')) if p.is_file()})
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
