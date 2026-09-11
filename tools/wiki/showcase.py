#!/usr/bin/env python3
"""Generate the README showcase SVGs: real terminal transcripts and exact game frames.

Writes wiki/showcase/build-and-tests.svg, board-session.svg and game-start.svg.
Every terminal line is captured or recorded text (see wiki/showcase/README.md);
every game pixel comes from the independent Springtrail frame references under
src/dv/springtrail. The SVGs are self-contained: CSS keyframes only, no script,
no external resource. The authored state is the finished still, so a reduced
motion reader sees the complete final picture.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'wiki/showcase'
sys.path.insert(0, str(ROOT / 'src/dv/springtrail'))

MONO = 'ui-monospace,Consolas,"Liberation Mono",Menlo,monospace'
PANEL, BORDER, TEXT, MUTED, ACCENT, WARM = '#171c24', '#303a48', '#e4eaf2', '#a9b6c7', '#93e7bd', '#f5cc83'
SHADES = ('#ffffff', '#d0d0d0', '#686868', '#181818')
WIDTH, LINE, PAD, BAR = 800, 18, 16, 30

# --- Loop 1: build and tests. Captured at 5ce0aa0 on 2026-09-11; long JSON lines
# are shortened with an ellipsis, every kept field is verbatim.
BUILD = [
    (0.0, 'cmd', 'python tools/build.py sw build springtrail --tag readme --json'),
    (1.6, 'out', '{"artifacts": {…}, "attempt": "f5c2e3ef0619", "cache": "MISS", "commit": "5ce0aa0d…", …'),
    (1.6, 'out', ' "rom": "workdir/builds/readme/sw/build/springtrail/runs/f5c2e3ef0619/image.gb", "status": "PASS", …}'),
    (3.6, 'cmd', 'python -m unittest tools.n2m.tests.test_core_art tools.n2m.tests.test_sprite_preview'),
    (4.4, 'out', '.........'),
    (4.6, 'out', '----------------------------------------------------------------------'),
    (4.6, 'out', 'Ran 9 tests in 0.600s'),
    (4.6, 'out', ''),
    (4.6, 'out', 'OK'),
    (6.4, 'cmd', 'python tools/build.py check --tag readme'),
    (8.6, 'out', 'PASS: check tag=readme'),
    (10.2, 'cmd', 'workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-joypad --tag readme'),
    (13.6, 'out', 'BUILT: sim tag=readme'),
    (14.6, 'cmd', 'grep -o "TESTS=.*" workdir/builds/readme/sim/test/python-joypad/sim.log'),
    (15.2, 'out', 'TESTS=1 PASS=1 FAIL=0 SKIP=0              21442.00           3.58       5985.43  **'),
]
BUILD_LOOP = 19.0

# --- Loop 2: board session. Command lines and response shapes follow
# wiki/tools/n2m/host/SPEC.md and the generated interface records; the dot
# values follow the documented 70224-dot frame, the source LCD commit at dot
# 76964 and row-143 frame completion. Not a live capture: the build ID, the
# retirement counters and sequence tokens are elided.
PACKAGE = 'workdir/builds/readme/sw/build/springtrail/runs/f5c2e3ef0619/result.json'
BOARD = [
    (0.0, 'cmd', f'python tools/build.py host load --package {PACKAGE} --tag board --json'),
    (3.4, 'out', '{"action": "load", …, "endpoint": {"abi": 1, "build_id": "…"}, …, "result": {"image": {"bytes": 32768,'),
    (3.4, 'out', ' "sha256": "adbef6b04b5ca7c3…"}, "verified_bytes": 32768}, "status": "PASS", "tag": "board", "wire_abi": 1}'),
    (5.2, 'cmd', 'python tools/build.py host status --tag board --json'),
    (5.8, 'out', '{"action": "status", …, "result": {"IMAGE_VALID": 1, "INPUT": 0, "PROFILE": 1, "STATE": 0}, "status": "PASS", …}'),
    (7.2, 'cmd', 'python tools/build.py host input --mask 128 --tag board --json'),
    (7.8, 'out', '{"action": "input", …, "result": {"dot": 0}, "status": "PASS", …}'),
    (9.0, 'cmd', 'python tools/build.py host run-dots --dots 70224 --tag board --json'),
    (9.6, 'out', '{"action": "run-dots", …, "result": {"dot": 70224, "executed": 70224, "reason": 0}, "status": "PASS", …}'),
    (10.6, 'cmd', 'python tools/build.py host run-dots --dots 70224 --tag board --json'),
    (11.2, 'out', '{"action": "run-dots", …, "result": {"dot": 140448, "executed": 70224, "reason": 0}, "status": "PASS", …}'),
    (12.2, 'cmd', 'python tools/build.py host run-dots --dots 70224 --tag board --json'),
    (12.8, 'out', '{"action": "run-dots", …, "result": {"dot": 210672, "executed": 70224, "reason": 0}, "status": "PASS", …}'),
    (14.0, 'cmd', 'python tools/build.py host snapshot --tag board --json'),
    (15.4, 'out', '{"action": "snapshot", …, "result": {"pixels": {"bytes": 5760, "sha256": "…"},'),
    (15.4, 'out', ' "snapshot": {"dot": 142627, "epoch": 2, "seq": 0, "size": 5760}}, "status": "PASS", …}'),
    (17.0, 'cmd', 'python tools/build.py host input --mask 0 --tag board --json'),
    (17.6, 'out', '{"action": "input", …, "result": {"dot": 210672}, "status": "PASS", …}'),
    (18.8, 'cmd', 'python tools/build.py host crc-proof --expected-build-id <reviewed-wire-id> --tag board --json'),
    (21.6, 'out', '{"action": "crc-proof", …, "result": {"after": {"DOT_HI": 0, "DOT_LO": 210672, "INPUT": 0, "INPUT_EFFECTIVE": 0,'),
    (21.6, 'out', ' "INPUT_SOURCE": 0, "STATE": 0, …}, "before": {…}, "silence_seconds": 2.0, …}, "status": "PASS", …}'),
]
BOARD_LOOP = 25.0

HIGHLIGHT = re.compile(r'"status": "PASS"|\bPASS\b|\bOK\b|\bBUILT\b|\bMISS\b|"dot": \d+|"verified_bytes": 32768|"silence_seconds": 2\.0')


def esc(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def pct(seconds, loop):
    return f'{seconds / loop * 100:.2f}'.rstrip('0').rstrip('.')


def spans(kind, text):
    if kind == 'cmd':
        return f'<tspan fill="{ACCENT}">$ </tspan>{esc(text)}'
    if kind == 'cmd+':
        return esc(text)
    parts, last = [], 0
    for match in HIGHLIGHT.finditer(text):
        parts.append(esc(text[last:match.start()]))
        parts.append(f'<tspan fill="{ACCENT}">{esc(match.group())}</tspan>')
        last = match.end()
    parts.append(esc(text[last:]))
    return f'<tspan fill="{MUTED}">{"".join(parts)}</tspan>'


def reveal_css(prefix, times, loop):
    """One keyframes per distinct appearance time; hidden before it, shown after."""
    css = []
    for index, seconds in enumerate(sorted(set(times))):
        if seconds == 0:
            continue
        css.append(f'@keyframes {prefix}{index}{{0%,{pct(seconds - 0.01, loop)}%{{opacity:0}}{pct(seconds, loop)}%,100%{{opacity:1}}}}')
    return css


def wrap(lines, columns=112):
    """Continue a long command on the next row, as a terminal would."""
    out = []
    for seconds, kind, text in lines:
        while len(text) > columns:
            cut = text.rfind(' ', 0, columns) if kind == 'cmd' else columns
            out.append((seconds, kind, text[:cut]))
            text, kind = ('    ' if kind == 'cmd' else ' ') + text[cut:].lstrip(), kind + '+'
        out.append((seconds, kind, text))
    return out


def terminal(title, footer, lines, loop):
    lines = wrap(lines)
    times = sorted(set(seconds for seconds, _, _ in lines))
    index = {seconds: times.index(seconds) for seconds in times}
    height = BAR + PAD + LINE * (len(lines) + 1) + PAD + 22
    body, rules = [], []
    for row, (seconds, kind, text) in enumerate(lines):
        y = BAR + PAD + LINE * (row + 1) - 4
        cls = f' class="t{index[seconds]}"' if seconds else ''
        body.append(f'<text{cls} x="{PAD}" y="{y}" xml:space="preserve">{spans(kind, text)}</text>')
    # The cursor waits below the last shown line while the loop plays.
    cursor_y = BAR + PAD + LINE * (len(lines) + 1) - 16
    steps = []
    for seconds in times:
        rows = sum(1 for s, _, _ in lines if s <= seconds)
        steps.append((seconds, BAR + PAD + LINE * (rows + 1) - 16 - cursor_y))
    frames = [f'0%{{transform:translateY({steps[0][1]}px)}}']
    for seconds, offset in steps[1:]:
        frames.append(f'{pct(seconds, loop)}%{{transform:translateY({offset}px)}}')
    frames.append('100%{transform:translateY(0)}')
    rules.append('@keyframes cur{' + ''.join(frames) + '}')
    rules.append('@keyframes blink{50%{opacity:0}}')
    rules += reveal_css('t', times, loop)
    motion = [f'.t{i}{{animation:t{i} {loop}s linear infinite}}' for i in range(1, len(times))]
    motion.append(f'.cur{{animation:cur {loop}s step-end infinite,blink 1s step-end infinite}}')
    style = (f'text{{font:12px {MONO};fill:{TEXT}}}.h{{font-size:11px;fill:{MUTED}}}'
             + ''.join(rules) + '@media (prefers-reduced-motion:no-preference){' + ''.join(motion) + '}')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{esc(title)}">',
           f'<title>{esc(title)}</title><style>{style}</style>',
           f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
           f'<path d="M0 {BAR}.5H{WIDTH}" stroke="{BORDER}"/>',
           f'<circle cx="18" cy="15" r="5" fill="#ff5f57"/><circle cx="36" cy="15" r="5" fill="#febc2e"/><circle cx="54" cy="15" r="5" fill="#28c840"/>',
           f'<text class="h" x="{WIDTH / 2}" y="19" text-anchor="middle">{esc(title)}</text>',
           *body,
           f'<text x="{PAD}" y="{cursor_y + 12}" xml:space="preserve"><tspan fill="{ACCENT}">$ </tspan></text>',
           f'<rect class="cur" x="{PAD + 15}" y="{cursor_y}" width="7" height="14" fill="{ACCENT}"/>',
           f'<text class="h" x="{PAD}" y="{height - 12}">{esc(footer)}</text>',
           '</svg>']
    return '\n'.join(svg) + '\n'


# --- Loop 3: game start from the independent Springtrail frame references.

def frames():
    from hud_reference import image
    from interactions_reference import Game, update
    title = Game()
    started = update(title, 128)                       # Start edge on the title screen
    walk = [started]
    for _ in range(24):                                 # Right+B held: 2 px per update
        walk.append(update(walk[-1], 33))
    released = update(walk[-1], 0)
    assert (started.mode, released.player.x // 16, released.player.camera) == (1, 72, 0)
    hidden = replace(started, player=replace(started.player, fell=True))
    def grid(game):
        pixels = image(game)
        return [pixels[y * 160:(y + 1) * 160] for y in range(144)]
    return grid(title), grid(hidden), grid(started), [grid(g) for g in walk[1:]], grid(released)


def diff(frame, base):
    return {(x, y): frame[y][x] for y in range(144) for x in range(160) if frame[y][x] != base[y][x]}


def normalise(pixels):
    left = min(x for x, _ in pixels)
    return left, {(x - left, y): shade for (x, y), shade in pixels.items()}


def paths(pixels):
    """Dominant-shade underlay under horizontal runs; exact for 2bpp pixel art."""
    dominant = Counter(pixels.values()).most_common(1)[0][0]
    rows = {}
    for (x, y), shade in pixels.items():
        rows.setdefault(y, []).append((x, shade))
    runs = {shade: [] for shade in range(4)}
    for y, cells in rows.items():
        cells.sort()
        for pass_shade, wanted in ((dominant, None), *((s, s) for s in range(4) if s != dominant)):
            start = previous = None
            for x, shade in cells:
                if wanted is not None and shade != wanted:
                    if start is not None:
                        runs[pass_shade].append((start, y, previous - start + 1)); start = None
                    continue
                if start is None or x != previous + 1:
                    if start is not None:
                        runs[pass_shade].append((start, y, previous - start + 1))
                    start = x
                previous = x
            if start is not None:
                runs[pass_shade].append((start, y, previous - start + 1))
    out = []
    for shade in (dominant, *(s for s in range(4) if s != dominant)):
        if runs[shade]:
            d = ''.join(f'M{x} {y}h{w}v1h-{w}z' for x, y, w in runs[shade])
            out.append(f'<path fill="{SHADES[shade]}" d="{d}"/>')
    return ''.join(out)


def game():
    title, base, started, walk, released = frames()
    stand_left, stand = normalise(diff(started, base))
    walk_left, first = normalise(diff(walk[0], base))
    for index, frame in enumerate(walk):
        left, pose = normalise(diff(frame, base))
        assert pose == first and left == walk_left + 2 * index, 'walk pose changed or moved unevenly'
    end_left, end = normalise(diff(released, base))
    assert end == stand and end_left == stand_left + 48
    stand_pixels = diff(started, base)
    title_only = {k: v for k, v in diff(title, base).items() if stand_pixels.get(k) != v}
    loop = 10.0
    scale, sx, sy = 3, PAD, BAR + PAD
    px, py = sx + 160 * scale + 40, sy + 8
    buttons = ['Right', 'Left', 'Up', 'Down', 'A', 'B', 'Select', 'Start']
    pills = []
    for index, label in enumerate(buttons):
        column, row = divmod(index, 4)
        x, y = px + column * 120, py + 30 + row * 34
        cls = {'Start': ' class="k-start"', 'Right': ' class="k-run"', 'B': ' class="k-run"'}.get(label, '')
        pills.append(f'<g{cls}><rect x="{x}" y="{y}" width="108" height="26" rx="13" fill="{PANEL}" stroke="{BORDER}"/>'
                     f'<text x="{x + 54}" y="{y + 17}" text-anchor="middle">{label}</text></g>')
    my = py + 30 + 4 * 34 + 14
    masks = ''.join(f'<text class="{cls}" x="{px}" y="{my}"{hide} xml:space="preserve"><tspan fill="{MUTED}">host input --mask </tspan>{value}</text>'
                    for cls, value, hide in (('m128', '128', ' opacity="0"'), ('m33', '33', ' opacity="0"'), ('m0', '0', '')))
    steps = [('s1', 'TITLE screen: PRESS START'), ('s2', 'Start (mask 128) → PLAY'), ('s3', 'Right+B (mask 33): run 48 px')]
    ly = my + 40
    legend = ''.join(f'<text class="{cls}" x="{px}" y="{ly + i * 24}">{i + 1}  {esc(text)}</text>' for i, (cls, text) in enumerate(steps))
    height = sy + 144 * scale + PAD + 22
    css = [
        f'text{{font:13px {MONO};fill:{TEXT}}}.h{{font-size:11px;fill:{MUTED}}}',
        f'.k-start rect,.k-run rect{{fill:{PANEL}}}',
        '@keyframes title{0%,28%{opacity:1}28.1%,100%{opacity:0}}',
        '@keyframes stand{0%,36%{opacity:1;transform:translateX(0)}36.1%,75.9%{opacity:0;transform:translateX(48px)}76%,100%{opacity:1;transform:translateX(48px)}}',
        '@keyframes walk{0%,36%{opacity:0;transform:translateX(0)}36.1%{opacity:1;transform:translateX(0)}76%{opacity:1;transform:translateX(48px)}76.1%,100%{opacity:0;transform:translateX(48px)}}',
        f'@keyframes lit{{0%,23.9%{{fill:{PANEL}}}24%,30%{{fill:{ACCENT}}}30.1%,100%{{fill:{PANEL}}}}}',
        f'@keyframes run{{0%,35.9%{{fill:{PANEL}}}36%,76%{{fill:{ACCENT}}}76.1%,100%{{fill:{PANEL}}}}}',
        f'@keyframes lit-text{{0%,23.9%{{fill:{TEXT}}}24%,30%{{fill:{PANEL}}}30.1%,100%{{fill:{TEXT}}}}}',
        f'@keyframes run-text{{0%,35.9%{{fill:{TEXT}}}36%,76%{{fill:{PANEL}}}76.1%,100%{{fill:{TEXT}}}}}',
        '@keyframes m128{0%,23.9%{opacity:0}24%,35.9%{opacity:1}36%,100%{opacity:0}}',
        '@keyframes m33{0%,35.9%{opacity:0}36%,76%{opacity:1}76.1%,100%{opacity:0}}',
        '@keyframes m0{0%,23.9%{opacity:1}24%,76%{opacity:0}76.1%,100%{opacity:1}}',
        f'@keyframes s1{{0%,24%{{fill:{ACCENT}}}24.1%,100%{{fill:{MUTED}}}}}',
        f'@keyframes s2{{0%,23.9%{{fill:{MUTED}}}24%,36%{{fill:{ACCENT}}}36.1%,100%{{fill:{MUTED}}}}}',
        f'@keyframes s3{{0%,35.9%{{fill:{MUTED}}}36%,100%{{fill:{ACCENT}}}}}',
        '@media (prefers-reduced-motion:no-preference){'
        + ''.join(f'.{cls}{{animation:{cls} {loop}s {timing} infinite}}' for cls, timing in (
            ('title', 'step-end'), ('stand', 'step-end'), ('walk', 'steps(24,end)'), ('m128', 'step-end'),
            ('m33', 'step-end'), ('m0', 'step-end'), ('s1', 'step-end'), ('s2', 'step-end'), ('s3', 'step-end')))
        + f'.k-start rect{{animation:lit {loop}s step-end infinite}}.k-run rect{{animation:run {loop}s step-end infinite}}'
        + f'.k-start text{{animation:lit-text {loop}s step-end infinite}}.k-run text{{animation:run-text {loop}s step-end infinite}}}}',
    ]
    label = 'Springtrail start: title screen, Start press, then running right; frames from the independent game reference'
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{label}">',
           f'<title>{label}</title><style>{"".join(css)}</style>',
           f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
           f'<path d="M0 {BAR}.5H{WIDTH}" stroke="{BORDER}"/>',
           f'<circle cx="18" cy="15" r="5" fill="#ff5f57"/><circle cx="36" cy="15" r="5" fill="#febc2e"/><circle cx="54" cy="15" r="5" fill="#28c840"/>',
           f'<text class="h" x="{WIDTH / 2}" y="19" text-anchor="middle">Springtrail on the Game Boy screen · 160 × 144 · played at one tenth speed</text>',
           f'<g transform="translate({sx} {sy}) scale({scale})" shape-rendering="crispEdges">',
           '<rect width="160" height="144" fill="#ffffff"/>',
           paths({(x, y): base[y][x] for y in range(144) for x in range(160) if base[y][x]}),
           f'<g class="title" opacity="0">{paths(title_only)}</g>',
           f'<g class="stand" transform="translate(48 0)">{paths(diff(started, base))}</g>',
           f'<g class="walk" opacity="0">{paths(diff(walk[0], base))}</g>',
           '</g>',
           f'<rect x="{sx - .5}" y="{sy - .5}" width="{160 * scale + 1}" height="{144 * scale + 1}" fill="none" stroke="{BORDER}"/>',
           f'<text class="h" x="{px}" y="{py + 12}">JOYP buttons (UART INPUT mask)</text>',
           *pills, masks, legend,
           f'<text class="h" x="{PAD}" y="{height - 12}">Exact frames from src/dv/springtrail references; Start on the title screen begins PLAY, then Right+B runs 2 px per update.</text>',
           '</svg>']
    return '\n'.join(svg) + '\n'


def documents():
    return {
        'build-and-tests': terminal('Build and tests · nand2mario at 5ce0aa0 · 2026-09-11',
                                    'Real command output captured in one session. Long JSON lines are shortened with …; every shown field is verbatim.',
                                    BUILD, BUILD_LOOP),
        'board-session': terminal('Board session over UART · recorded shapes, not a live capture',
                                  'Commands and replies follow wiki/tools/n2m/host/SPEC.md; dots follow the 70224-dot frame. Build ID and counters elided.',
                                  BOARD, BOARD_LOOP),
        'game-start': game(),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in documents().items():
        path = OUT / f'{name}.svg'
        path.write_text(text, encoding='utf-8', newline='\n')
        print(f'{path.relative_to(ROOT).as_posix()}: {path.stat().st_size} bytes')


if __name__ == '__main__':
    main()
