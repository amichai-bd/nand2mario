"""Compare a board `host snapshot` menu frame with the independent reference, by frame class.

Usage: python src/dv/menu/board_compare.py <frame.2bpp> <catalogue.bin> <out-dir> <sample>
           [--phase 0|1|any] [--result R] [--index I]

`catalogue.bin` is the artifact `host library status` retains: the catalogue as
stored in SDRAM, entries and tagline table. `sample` is a reference frame name
(`menu`, `phase-N`, `cursor-N`, `footer-A-B`, `scroll-N`, `splash-N`, `back-N`)
or a family that names several candidates (`splash`, `phase`, `ramp`, `back`).
Every candidate is rendered in each requested nudge phase and compared pixel for
pixel; the record names the candidates that matched. `--result` and `--index`
are the loader status bytes the frame was read under, for frames after a
refused select. Writes frame.png, reference.png (the first matching candidate,
else the first candidate), diff.png and compare.json into <out-dir>; exits 0
only when at least one candidate matches.
"""
import argparse
import json
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src' / 'dv' / 'libbet'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import frame_png  # noqa: E402
import reference  # noqa: E402
from n2m.host import library  # noqa: E402

RAMP_OFF_SLOT = reference.SCROLL_SLOT - 1
FAMILIES = {
    'splash': [f'splash-{n}' for n in range(reference.SETTLED_FRAME + 1)],
    'phase': [f'phase-{n}' for n in range(reference.PHASES)],
    'ramp': [f'scroll-{n}' for n in range(1, reference.SCROLL_FRAMES + 1)],
    'back': [f'back-{n}' for n in range(1, reference.SCROLL_FRAMES)] + [f'cursor-{RAMP_OFF_SLOT}'],
}


def state_of(sample):
    """The `reference.frame` keyword state of one named frame, without the catalogue.

    The names are `reference.expected`'s, plus `back-N`: frame N (1..3) of the
    ramp off the last slot back to slot 14, whose first frame carries the
    staged footer and the rest the settled one.
    """
    if sample == 'menu':
        return {}
    kind, _, rest = sample.partition('-')
    if kind == 'phase':
        return dict(phase=int(rest))
    if kind == 'cursor':
        cursor = int(rest)
        return dict(cursor=cursor, scy=reference.scroll_target(cursor))
    if kind == 'footer':
        upper, lower = (int(part) for part in rest.split('-'))
        ramp = reference.scroll_ramp(reference.scroll_target(lower), upper)
        return dict(cursor=upper, footer=(upper, lower), scy=ramp[0] if ramp else reference.scroll_target(upper))
    if kind == 'scroll':
        step = int(rest)
        if not 1 <= step <= reference.SCROLL_FRAMES:
            raise ValueError(f'a scroll frame is 1..{reference.SCROLL_FRAMES}')
        return dict(cursor=reference.SCROLL_SLOT, scy=reference.SETTLED_SCY + reference.SCROLL_STEP * step)
    if kind == 'back':
        step = int(rest)
        if not 1 <= step < reference.SCROLL_FRAMES:
            raise ValueError(f'a ramp-off frame is 1..{reference.SCROLL_FRAMES - 1}')
        footer = (RAMP_OFF_SLOT, reference.SCROLL_SLOT) if step == 1 else None
        return dict(cursor=RAMP_OFF_SLOT, footer=footer,
                    scy=reference.SCROLLED_SCY - reference.SCROLL_STEP * step)
    if kind == 'splash':
        bgp, scy, wrapped = reference.splash_state(int(rest))
        return dict(bgp=bgp, scy=scy, wrapped=wrapped)
    raise ValueError(f'unknown menu sample {sample!r}')


def candidates(sample, phases=(0, 1), result=reference.RESULT_NONE, index=reference.NO_INDEX):
    """[(name, state)] for a sample or family: every named frame in every requested phase.

    A splash frame has no pointer, window or twinkle phase, so it is one
    candidate; `phase-N` names its own phase. `result` and `index` reach every
    candidate, because a message on the plate stays until the next select.
    """
    names = FAMILIES.get(sample, [sample])
    out = []
    for name in names:
        state = state_of(name)
        if name.startswith('splash-'):
            out.append((name, dict(state, result=result, index=index)))
            continue
        if 'phase' in state:
            out.append((name, dict(state, result=result, index=index)))
            continue
        for phase in phases:
            out.append((f'{name}/phase-{phase}', dict(state, phase=phase, result=result, index=index)))
    return out


def crc32(pixels):
    return f'{zlib.crc32(bytes(pixels)):08x}'


def compare(packed, entries, candidate_list):
    """The comparison record of one packed frame against every candidate; `matches` names the exact ones."""
    pixels = reference.unpack(packed)
    rows = []
    for name, state in candidate_list:
        expected = reference.frame(entries, **state)
        mismatches = sum(1 for a, b in zip(pixels, expected) if a != b)
        first = next(((i % reference.WIDTH, i // reference.WIDTH) for i, (a, b) in enumerate(zip(pixels, expected))
                      if a != b), None)
        rows.append(dict(name=name, mismatches=mismatches, reference_crc32=crc32(expected),
                         first_mismatch=None if first is None else dict(x=first[0], y=first[1]),
                         state={k: (list(v) if isinstance(v, tuple) else v) for k, v in state.items()}))
    matches = [row['name'] for row in rows if row['mismatches'] == 0]
    return dict(size=len(packed), pixels=len(pixels), frame_crc32=crc32(pixels), candidates=rows,
                matches=matches, match=bool(matches))


def render(packed, entries, record, out, scale=2):
    """frame.png, reference.png and diff.png of a comparison record under `out`."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    pixels = reference.unpack(packed)
    chosen = next((row for row in record['candidates'] if row['mismatches'] == 0), record['candidates'][0])
    state = {k: (tuple(v) if isinstance(v, list) else v) for k, v in chosen['state'].items()}
    expected = reference.frame(entries, **state)
    frame_png.write_frame(pixels, out / 'frame.png', scale=scale)
    frame_png.write_frame(expected, out / 'reference.png', scale=scale)
    frame_png.write_diff(expected, pixels, out / 'diff.png', scale=scale)
    return chosen['name']


def run(frame, catalogue, out, sample, phases=(0, 1), result=reference.RESULT_NONE, index=reference.NO_INDEX):
    packed = Path(frame).read_bytes()
    entries = library.parse_catalogue(Path(catalogue).read_bytes())
    record = compare(packed, entries, candidates(sample, phases, result, index))
    record.update(frame=str(frame), catalogue=str(catalogue), sample=sample,
                  rendered=render(packed, entries, record, out),
                  entries=[dict(index=i, valid=e['valid'], title=library.title_text(e['title']),
                                tagline=library.title_text(e['tagline'])) for i, e in enumerate(entries)])
    (Path(out) / 'compare.json').write_text(json.dumps(record, indent=2, sort_keys=True), encoding='utf-8')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('frame')
    parser.add_argument('catalogue')
    parser.add_argument('out')
    parser.add_argument('sample')
    parser.add_argument('--phase', default='any', choices=('0', '1', 'any'))
    parser.add_argument('--result', type=int, default=reference.RESULT_NONE)
    parser.add_argument('--index', type=int, default=reference.NO_INDEX)
    args = parser.parse_args(argv)
    phases = (0, 1) if args.phase == 'any' else (int(args.phase),)
    record = run(args.frame, args.catalogue, args.out, args.sample, phases, args.result, args.index)
    brief = {k: record[k] for k in ('sample', 'size', 'frame_crc32', 'matches', 'match', 'rendered')}
    brief['candidates'] = {row['name']: row['mismatches'] for row in record['candidates']}
    print(json.dumps(brief, sort_keys=True))
    return 0 if record['match'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
