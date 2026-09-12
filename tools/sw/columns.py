"""Generate and check the Springtrail display column table from the literal world.

`world.asm` is the single source; `columns.asm` is its committed generated
output. Run `python tools/sw/columns.py` to regenerate, `--check` to verify.
Every `sw build springtrail` runs the same check before assembly. This is a
data-generation step only; the assembler contract gains no macros.
"""
import argparse
from pathlib import Path
import sys

try:
    from .expressions import AssemblyError
except ImportError:  # invoked as a script, not as the sw package
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from sw.expressions import AssemblyError

TREE = Path('src/sw/springtrail')
WORLD = TREE / 'world.asm'
COLUMNS = TREE / 'columns.asm'
WIDTH, HEIGHT, ROWS, FIRST_ROW, TILES = 256, 18, 16, 2, 94
# Stage base column and width; the three stages fill one 256-column page.
STAGES = ((0, 96), (96, 80), (176, 80))
HEADER = '; Original count/tile display columns for all three stages; collision data stays in world.asm.'


def decode(data, tiles=TILES):
    """Expand one count/tile run list into sixteen tiles; reject anything else."""
    def bad():
        raise AssemblyError('COLUMN_ENCODING', 'exact bounded sixteen-row column required')
    if not isinstance(data, list) or not 1 <= len(data) <= 33: bad()
    if any(type(n) is not int or not 0 <= n <= 255 for n in data): bad()
    out = []; index = 0
    while index < len(data):
        count = data[index]; index += 1
        if count == 0:
            if index != len(data) or len(out) != ROWS: bad()
            return out
        if count > ROWS or index == len(data) or len(out) + count > ROWS: bad()
        tile = data[index]; index += 1
        if tile >= tiles: bad()
        out.extend([tile] * count)
    bad()


def encode(column):
    """Greedy count/tile runs ending in 0; the inverse of decode."""
    runs = []
    for tile in column:
        if runs and runs[-2] == tile and runs[-1] < ROWS:
            runs[-1] += 1
        else:
            runs += [tile, 1]
    data = [value for tile, count in zip(runs[::2], runs[1::2]) for value in (count, tile)] + [0]
    if decode(data) != list(column):
        raise AssemblyError('COLUMN_ENCODING', 'column does not round-trip through its encoding')
    return data


def load_world(text):
    """The literal 18x256 three-stage tile rows of world.asm, or COLUMN_WORLD."""
    rows = []
    for line in text.splitlines():
        body = line.split(';')[0].strip()
        if body.startswith('DB '):
            parts = body[3:].split(',')
            if not all(part.isdigit() for part in parts):
                raise AssemblyError('COLUMN_WORLD', 'literal18x256 three-stage collision world required')
            rows.append([int(part) for part in parts])
    if len(rows) != HEIGHT or any(len(row) != WIDTH for row in rows) or any(not 0 <= n < TILES for row in rows for n in row):
        raise AssemblyError('COLUMN_WORLD', 'literal18x256 three-stage collision world required')
    return rows


def render(world):
    """The exact text of columns.asm for one world: pointers, then run data."""
    lines = [HEADER, 'SECTION "columns",ROM', 'ColumnPointers:']
    lines += ['DW DisplayColumn' + str(x) for x in range(WIDTH)]
    for x in range(WIDTH):
        column = [world[y + FIRST_ROW][x] for y in range(ROWS)]
        lines += ['DisplayColumn' + str(x) + ':', 'DB ' + ','.join(map(str, encode(column)))]
    return '\n'.join(lines) + '\n'


def inputs(root):
    """Generator inputs a springtrail build must fingerprint."""
    return [Path(root) / name for name in (WORLD, COLUMNS, 'tools/sw/columns.py')]


def validate(root):
    """Fail unless the committed columns.asm equals generation from world.asm."""
    root = Path(root)
    world = load_world((root / WORLD).read_text(encoding='utf-8'))
    expected = render(world)
    path = root / COLUMNS
    actual = path.read_text(encoding='utf-8') if path.is_file() else ''
    if actual != expected:
        have, want = actual.splitlines(), expected.splitlines()
        line = next((i for i, pair in enumerate(zip(have, want), 1) if pair[0] != pair[1]), min(len(have), len(want)) + 1)
        raise AssemblyError('COLUMN_STALE', COLUMNS.as_posix() + ' differs from generation from '
                            + WORLD.as_posix() + ' at line ' + str(line) + '; run python tools/sw/columns.py',
                            span={'file': COLUMNS.relative_to(TREE.parent).as_posix(), 'line': line, 'column': 1})
    return [[world[y + FIRST_ROW][x] for y in range(ROWS)] for x in range(WIDTH)]


def generate(root, check=False):
    root = Path(root)
    if check:
        validate(root)
        return
    path = root / COLUMNS
    text = render(load_world((root / WORLD).read_text(encoding='utf-8')))
    # Keep the checkout's line ending so regeneration does not churn the file.
    newline = '\r\n' if path.is_file() and b'\r\n' in path.read_bytes() else '\n'
    path.write_text(text, encoding='utf-8', newline=newline)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='verify the committed table without writing')
    parser.add_argument('--root', default=Path(__file__).resolve().parents[2], help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        generate(args.root, check=args.check)
    except (AssemblyError, OSError) as error:
        code = error.diagnostic['code'] if isinstance(error, AssemblyError) else 'OSERROR'
        parser.exit(1, f'FAIL {code}: {error}\n')
    print('PASS ' + COLUMNS.as_posix() + (' matches ' if args.check else ' generated from ') + WORLD.as_posix())


if __name__ == '__main__':
    main()
