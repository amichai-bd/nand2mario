#!/usr/bin/env python3
"""Generate the showcase SVGs: real terminal transcripts and exact game frames.

Writes the README loops wiki/showcase/build-and-tests.svg, board-session.svg
and game-start.svg, and the lesson-deck terminal sessions
reproducible-builds.svg, uart-debugging.svg and verification.svg, and the
board loops libbet-board.svg and springtrail-board.svg the showcase page embeds.
Every terminal line is captured or recorded text (see wiki/showcase/README.md);
every game-start.svg pixel comes from the independent Springtrail frame
references under src/dv/springtrail, and every board-loop pixel is a frame the
DE10-Lite returned over UART. The SVGs are self-contained: CSS keyframes only, no script,
no external resource. The authored state is the finished still, so a reduced
motion reader sees the complete final picture.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'wiki/showcase'
sys.path.insert(0, str(ROOT / 'src/dv/springtrail'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

MONO = 'ui-monospace,Consolas,"Liberation Mono",Menlo,monospace'
PANEL, BORDER, TEXT, MUTED, ACCENT, WARM = '#171c24', '#303a48', '#e4eaf2', '#a9b6c7', '#93e7bd', '#f5cc83'
SHADES = ('#ffffff', '#d0d0d0', '#686868', '#181818')
WIDTH, LINE, PAD, BAR = 800, 18, 16, 30
# A typed command lays out its own characters at a fixed monospace advance
# (0.6em at the 12px terminal font) instead of relying on the browser's own
# font metrics, so the keystroke reveal tracks a stable column regardless of
# which system font ui-monospace resolves to.
CHAR_W, TYPE_RATE, MIN_TYPE = 7.2, 0.028, 0.35
# The page that embeds each loop; the quality tests check the reference and
# that the committed SVG equals this generator's output.
EMBEDS = {'build-and-tests': 'README.md', 'board-session': 'README.md', 'game-start': 'README.md',
          'reproducible-builds': 'wiki/presentations/reproducible-builds.html',
          'uart-debugging': 'wiki/presentations/uart-debugging.html',
          'verification': 'wiki/presentations/verification.html',
          'springtrail-state-board': 'wiki/showcase/README.md',
          'libbet-board': 'wiki/showcase/README.md', 'springtrail-board': 'wiki/showcase/README.md'}

# --- Loop 1: build and tests. Captured at 5ce0aa0 on 2026-09-11; long JSON lines
# are shortened with an ellipsis, every kept field is verbatim; wrap() breaks
# them into rows.
BUILD = [
    (0.0, 'cmd', 'python tools/build.py sw build springtrail --tag readme --json'),
    (1.6, 'out', '{"artifacts": {…}, "attempt": "f5c2e3ef0619", "cache": "MISS", "commit": "5ce0aa0d…", …, "rom": "workdir/builds/readme/sw/build/springtrail/runs/f5c2e3ef0619/image.gb", "status": "PASS", …}'),
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
    (3.4, 'out', '{"action": "load", …, "endpoint": {"abi": 1, "build_id": "…"}, …, "result": {"image": {"bytes": 32768, "sha256": "adbef6b04b5ca7c3…"}, "verified_bytes": 32768}, "status": "PASS", "tag": "board", "wire_abi": 1}'),
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
    (15.4, 'out', '{"action": "snapshot", …, "result": {"pixels": {"bytes": 5760, "sha256": "…"}, "snapshot": {"dot": 142627, "epoch": 2, "seq": 0, "size": 5760}}, "status": "PASS", …}'),
    (17.0, 'cmd', 'python tools/build.py host input --mask 0 --tag board --json'),
    (17.6, 'out', '{"action": "input", …, "result": {"dot": 210672}, "status": "PASS", …}'),
    (18.8, 'cmd', 'python tools/build.py host crc-proof --expected-build-id <reviewed-wire-id> --tag board --json'),
    (21.6, 'out', '{"action": "crc-proof", …, "result": {"after": {"DOT_HI": 0, "DOT_LO": 210672, "INPUT": 0, "INPUT_EFFECTIVE": 0, "INPUT_SOURCE": 0, "STATE": 0, …}, "before": {…}, "silence_seconds": 2.0, …}, "status": "PASS", …}'),
]
BOARD_LOOP = 24.0

# --- Lesson loops. Each teaches one deck's subject with the commands it is
# about; wiki/showcase/README.md records where every shown line comes from.

# Reproducible builds: captured at 396b0b4 on 2026-09-11 in one shell. Two
# clean tags build the same fingerprint and image hash; the same tag again is
# a cache HIT; one appended comment line in world.asm changes the source hash,
# so the fingerprint misses and a fresh attempt builds byte-identical bytes.
LESSON_A = 'workdir/builds/lesson-a/sw/build/springtrail/runs/8f9e24a33197/image.gb'
LESSON_B = 'workdir/builds/lesson-b/sw/build/springtrail/runs/9ad388c6093e/image.gb'
LESSON_C = 'workdir/builds/lesson-a/sw/build/springtrail/runs/76c8b79b8fe7/image.gb'
IMAGE_SHA = '616de11b49e0807539837358824a570776459b9bf13a4b9424dbf42adfe5c983'
BUILDS = [
    (0.0, 'cmd', 'python tools/build.py sw build springtrail --tag lesson-a --json'),
    (1.2, 'out', '{"artifacts": {…}, "attempt": "8f9e24a33197", "cache": "MISS", "commit": "396b0b4c…", …, "fingerprint": "e3a381f906d5ee45…", …, "status": "PASS", …}'),
    (3.0, 'cmd', 'python tools/build.py sw build springtrail --tag lesson-b --json'),
    (4.2, 'out', '{"artifacts": {…}, "attempt": "9ad388c6093e", "cache": "MISS", "commit": "396b0b4c…", …, "fingerprint": "e3a381f906d5ee45…", …, "status": "PASS", …}'),
    (6.4, 'cmd', f'sha256sum {LESSON_A} {LESSON_B}'),
    (6.8, 'out', f'{IMAGE_SHA} *{LESSON_A}'),
    (6.8, 'out', f'{IMAGE_SHA} *{LESSON_B}'),
    (8.8, 'cmd', 'python tools/build.py sw build springtrail --tag lesson-a --json'),
    (9.6, 'out', '{"artifacts": {…}, "attempt": "8f9e24a33197", "cache": "HIT", "commit": "396b0b4c…", …, "fingerprint": "e3a381f906d5ee45…", …, "reused_from": "396b0b4c…", "status": "PASS", …}'),
    (11.6, 'cmd', "printf '; lesson: one comment line changes the source hash\\r\\n' >> src/sw/springtrail/world.asm"),
    (13.2, 'cmd', 'python tools/build.py sw build springtrail --tag lesson-a --json'),
    (14.4, 'out', '{"artifacts": {…}, "attempt": "76c8b79b8fe7", "cache": "MISS", "commit": "396b0b4c…", …, "fingerprint": "dbb46f91643c8b0d…", …, "status": "PASS", …}'),
    (16.4, 'cmd', f'sha256sum {LESSON_C}'),
    (16.8, 'out', f'{IMAGE_SHA} *{LESSON_C}'),
    (18.4, 'cmd', 'git checkout -- src/sw/springtrail/world.asm'),
]
BUILDS_LOOP = 21.0

# UART debugging: the recorded Libbet play session from src/dv/libbet/README.md
# ("Start at 8 s: title, play, one roll"), not a live capture and nothing sent
# to a board for this page. Command lines and reply shapes follow
# wiki/tools/n2m/host/SPEC.md; the wire build ID, image hash and size are the
# recorded pin; every dot, seq and the three-frame Start hold are the record's
# values. The snapshot epoch and pixel hashes are elided.
LIBBET_SHA = '3607412031c8287c…'
SESSION = [
    (0.0, 'cmd', 'python tools/build.py host status --tag lesson --json'),
    (0.8, 'out', '{"action": "status", …, "endpoint": {"abi": 1, "build_id": "bb02588d127b72ce6458a07ff1145c57"}, …, "result": {"IMAGE_VALID": 1, "INPUT": 0, "PROFILE": 1, "STATE": 0}, "status": "PASS", …}'),
    (2.6, 'cmd', 'python tools/build.py host load --external libbet --tag lesson --json'),
    (6.0, 'out', f'{{"action": "load", …, "external": {{"license": "Zlib", "pin": "libbet", "sha256": "{LIBBET_SHA}", "size": 32768, …}}, …, "result": {{"image": {{"bytes": 32768, "sha256": "{LIBBET_SHA}"}}, "verified_bytes": 32768}}, "status": "PASS", …}}'),
    (8.0, 'cmd', 'python tools/build.py host run --tag lesson --json'),
    (8.6, 'out', '{"action": "run", …, "result": null, "status": "PASS", …}'),
    (10.4, 'cmd', 'python tools/build.py host halt --tag lesson --json'),
    (11.0, 'out', '{"action": "halt", …, "result": {"dot": 33631192}, "status": "PASS", …}'),
    (12.4, 'cmd', 'python tools/build.py host snapshot --tag lesson --json'),
    (13.8, 'out', '{"action": "snapshot", …, "result": {"pixels": {"bytes": 5760, "sha256": "…"}, "snapshot": {"dot": 33605475, "epoch": …, "seq": 456, "size": 5760}}, "status": "PASS", …}'),
    (15.6, 'cmd', 'python tools/build.py host input --mask 128 --tag lesson --json'),
    (16.2, 'out', '{"action": "input", …, "result": {"dot": 33631192}, "status": "PASS", …}'),
    (17.4, 'cmd', 'python tools/build.py host run-dots --dots 70224 --tag lesson --json'),
    (18.0, 'out', '{"action": "run-dots", …, "result": {"dot": 33701416, "executed": 70224, "reason": 0}, "status": "PASS", …}'),
    (19.0, 'cmd', 'python tools/build.py host run-dots --dots 70224 --tag lesson --json'),
    (19.6, 'out', '{"action": "run-dots", …, "result": {"dot": 33771640, "executed": 70224, "reason": 0}, "status": "PASS", …}'),
    (20.6, 'cmd', 'python tools/build.py host run-dots --dots 70224 --tag lesson --json'),
    (21.2, 'out', '{"action": "run-dots", …, "result": {"dot": 33841864, "executed": 70224, "reason": 0}, "status": "PASS", …}'),
    (22.4, 'cmd', 'python tools/build.py host input --mask 0 --tag lesson --json'),
    (23.0, 'out', '{"action": "input", …, "result": {"dot": 33841864}, "status": "PASS", …}'),
    (24.2, 'cmd', 'python tools/build.py host snapshot --tag lesson --json'),
    (25.6, 'out', '{"action": "snapshot", …, "result": {"pixels": {"bytes": 5760, "sha256": "…"}, "snapshot": {"dot": 33675699, "epoch": …, "seq": 457, "size": 5760}}, "status": "PASS", …}'),
]
SESSION_LOOP = 28.6

# Accent words: results a reader scans for. FAIL and the expected fault line
# take the warm colour so a deliberate failure reads as one.
HIGHLIGHT = re.compile(r'"status": "PASS"|\bPASS\b|\bOK\b|\bBUILT\b|\bMISS\b|\bHIT\b|"dot": \d+|"verified_bytes": 32768|"silence_seconds": 2\.0')
WARN = re.compile(r'"status": "FAIL"|Fatal: [^"]*')

# Verification: from retained Questa receipts under workdir/builds of the
# primary checkout, not a fresh capture (the single Questa seat was held).
# The passing Python joypad target ran at f6fff8f (isolated Python 3.12.14
# DV environment); the deliberate-failure builder target ran at c89b47d.
# Each JSON line shortens the retained result.json (the --json report) with …,
# keeping cache, python_results, error and status verbatim except the error's
# elided receipt path; each grep line is the real grep result on the retained
# sim.log.
DV = 'workdir/builds/python-dv-env/.venv/Scripts/python.exe'
TESTS = [
    (0.0, 'cmd', f'{DV} tools/build.py sim test python-joypad --tag standalone-verify2 --json'),
    (3.6, 'out', '{"artifacts": {…}, "cache": "BUILT", …, "python_results": {"sim_time_ns": 21442.0, "status": "PASS", "test": "joypad_contract"}, …, "status": "PASS", …}'),
    (5.4, 'cmd', 'grep -o "TESTS=.*" workdir/builds/standalone-verify2/sim/test/python-joypad/sim.log'),
    (6.0, 'out', 'TESTS=1 PASS=1 FAIL=0 SKIP=0              21442.00           3.88       5527.10  **'),
    (7.8, 'cmd', 'python tools/build.py sim test builder-smoke-fail --tag deliberate-failure --json'),
    (10.6, 'out', '{"artifacts": {…}, "cache": "BUILT", …, "error": "unexpected exit 1; see workdir\\builds\\deliberate-failure\\…", …, "status": "FAIL", …}'),
    (12.4, 'cmd', 'grep -o "Fatal: .*" workdir/builds/deliberate-failure/sim/test/builder-smoke-fail/sim.log'),
    (13.0, 'out', 'Fatal: count cycle=3 expected=7 actual=3 seed=1'),
]
TESTS_LOOP = 16.6


def esc(text):
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def pct(seconds, loop):
    return f'{seconds / loop * 100:.2f}'.rstrip('0').rstrip('.')


def spans(kind, text):
    if kind == 'cmd+':
        return esc(text)
    parts, last = [], 0
    matches = sorted([(m.start(), m.end(), ACCENT) for m in HIGHLIGHT.finditer(text)]
                     + [(m.start(), m.end(), WARM) for m in WARN.finditer(text)])
    for start, end, fill in matches:
        if start < last:
            continue  # the earlier match already covers this span
        parts.append(esc(text[last:start]))
        parts.append(f'<tspan fill="{fill}">{esc(text[start:end])}</tspan>')
        last = end
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


def typed_rows(rows, prompt_at, start, end, loop, y_of):
    """Command rows typed one character at a time by the shared cursor.

    `rows` is a cmd row and its cmd+ continuation rows, typed as one command
    from `start` to `end`. Each character sits at a fixed x (CHAR_W apart)
    instead of the browser's own text flow, so the reveal tracks a stable
    column on every platform's monospace font. The "$ " prompt appears at
    `prompt_at`, when the previous output has printed, so the cursor waits
    at a real prompt before typing; a not-yet-typed command stays hidden.
    Returns the text elements, keyframes, motion bindings and the cursor
    steps (time, x after the typed character, row top).
    """
    css, motion, texts, steps = [], [], [], []
    typed = sum(len(text.lstrip()) if kind == 'cmd+' else len(text) for _, kind, text in rows)
    dur, k = max(end - start, 0.01), 0
    for row, kind, text in rows:
        y, x0 = y_of(row), PAD + (2 * CHAR_W if kind == 'cmd' else 0)
        prompt, tspans = '', []
        if kind == 'cmd':
            prompt = f'<tspan fill="{ACCENT}">$ </tspan>'
            if prompt_at > 0:
                css.append(f'@keyframes k{row}p{{0%,{pct(prompt_at - 0.01, loop)}%{{opacity:0}}{pct(prompt_at, loop)}%,100%{{opacity:1}}}}')
                motion.append(f'.k{row}p{{animation:k{row}p {loop}s step-end infinite}}')
                prompt = f'<tspan class="k{row}p" fill="{ACCENT}">$ </tspan>'
            steps.append((min(prompt_at, start), x0, y - 12))
        # A continuation row's indent is layout, not keystrokes: it lands
        # with the row's first typed character.
        indent = len(text) - len(text.lstrip()) if kind == 'cmd+' else 0
        for i, ch in enumerate(text):
            cls, x = f'k{row}c{i}', x0 + i * CHAR_W
            t = start + (k / typed) * dur
            if i >= indent:
                k += 1
                steps.append((t, x + CHAR_W, y - 12))
            tspans.append(f'<tspan class="{cls}" x="{x:.1f}">{esc(ch)}</tspan>')
            if t <= 0:
                continue  # already typed when the loop starts
            css.append(f'@keyframes {cls}{{0%,{pct(max(t - 0.01, 0), loop)}%{{opacity:0}}{pct(t, loop)}%,100%{{opacity:1}}}}')
            motion.append(f'.{cls}{{animation:{cls} {loop}s step-end infinite}}')
        texts.append(f'<text x="{PAD}" y="{y}" xml:space="preserve">{prompt}{"".join(tspans)}</text>')
    return texts, css, motion, steps


def split_rows(text, limit, rows, separator):
    """Break text into `rows` rows of at most `limit` characters, each ending
    at the last `separator` before an even share; None when that cannot fit."""
    out = []
    for left in range(rows, 1, -1):
        target = min(limit, -(-len(text) // left) + 8)
        cut = text.rfind(separator, 0, target)
        if cut <= 0:
            cut = text.rfind(separator, 0, limit)  # no even share; take the longest row
        if cut <= 0:
            cut = text.rfind(' ', 0, target)
        if cut <= 0:
            return None
        if text[cut:cut + len(separator)] == separator:
            cut += len(separator) - 1  # keep the "," on this row
        out.append(text[:cut])
        text = ' ' + text[cut:].lstrip()
    return out + [text] if len(text) <= limit else None


def wrap(lines, columns=101):
    """Continue a long line on the next rows, as a terminal would.

    Rows are balanced so no continuation is a stub: each break lands at the
    last space (commands) or ", " JSON separator (output) before an even
    share of the text, so no field or value is cut in two.
    """
    out = []
    for seconds, kind, text in lines:
        # A typed cmd row also carries the "$ " prompt and the cursor; keep it
        # a few columns narrower so that overhead still fits the 800px viewBox
        # at a 0.6em font.
        limit = columns - 4 if kind == 'cmd' else columns
        rows = [text]
        for count in range(2, 6):
            if len(text) <= limit:
                break
            rows = split_rows(text, limit, count, ' ' if kind == 'cmd' else ', ')
            if rows:
                break
        assert rows and all(len(row) <= limit for row in rows), text
        out.append((seconds, kind, rows[0]))
        # A continuation command row is indented under its prompt.
        out += [(seconds, kind + '+', ('   ' if kind == 'cmd' else '') + row) for row in rows[1:]]
    return out


def terminal(title, footer, lines, loop):
    lines = wrap(lines)
    # Lead in by LEAD seconds so the very first command has room to type
    # before its own reveal time, instead of popping in fully typed; every
    # line (and the loop length) shifts by the same fixed amount, so real
    # gaps between commands and their output are unchanged.
    LEAD = 0.8
    lines = [(seconds + LEAD, kind, text) for seconds, kind, text in lines]
    loop += LEAD
    times = sorted(set(seconds for seconds, _, _ in lines))
    index = {seconds: times.index(seconds) for seconds in times}
    height = BAR + PAD + LINE * (len(lines) + 1) + PAD + 22

    def y_of(row):
        return BAR + PAD + LINE * (row + 1) - 4

    body, rules, motion, steps = [], [], [], []
    row = 0
    while row < len(lines):
        seconds, kind, text = lines[row]
        if kind != 'cmd':
            cls = f' class="t{index[seconds]}"' if seconds else ''
            body.append(f'<text{cls} x="{PAD}" y="{y_of(row)}" xml:space="preserve">{spans(kind, text)}</text>')
            row += 1
            continue
        group = [(row, kind, text)]
        while row + len(group) < len(lines) and lines[row + len(group)][1] == 'cmd+':
            group.append((row + len(group),) + lines[row + len(group)][1:])
        # Type the command in before it "runs": start early enough to finish
        # exactly when the line's own reveal time arrives, so the output
        # below still only appears once typing is done.
        earlier = [s for s in times if s < seconds]
        prev = earlier[-1] if earlier else 0.0
        typed = sum(len(t.lstrip()) if k == 'cmd+' else len(t) for _, k, t in group)
        dur = min(max(typed * TYPE_RATE, MIN_TYPE), max(seconds - prev - 0.05, MIN_TYPE))
        texts, css, mo, st = typed_rows(group, prev, max(seconds - dur, 0.0), seconds, loop, y_of)
        body += texts
        rules += css
        motion += mo
        steps += st
        row += len(group)
    # One cursor: it walks along each command as it is typed, then waits on
    # the row below the last shown line: at column 0 while output is still
    # to come, after the "$ " prompt once it has printed. Its authored place
    # (no transform) is the final prompt row, the still.
    cursor_x, cursor_y = PAD + 2 * CHAR_W, BAR + PAD + LINE * (len(lines) + 1) - 16
    for seconds in times:
        rows = sum(1 for s, _, _ in lines if s <= seconds)
        at_prompt = rows == len(lines) or lines[rows][1] == 'cmd'
        steps.append((seconds, cursor_x if at_prompt else PAD, BAR + PAD + LINE * (rows + 1) - 16))
    steps.sort(key=lambda step: step[0])
    if steps[0][0] > 0:
        steps.insert(0, (0.0, PAD, BAR + PAD + LINE - 16))  # no line shown yet
    frames = [f'{pct(t, loop) if t else 0}%{{transform:translate({x - cursor_x:.1f}px,{y - cursor_y}px)}}' for t, x, y in steps]
    frames.append('100%{transform:translate(0,0)}')
    rules.append('@keyframes cur{' + ''.join(frames) + '}')
    rules.append('@keyframes blink{50%{opacity:0}}')
    # Soften the loop seam: a short fade in and out of the whole session.
    rules.append(f'@keyframes reel{{0%{{opacity:0}}{pct(0.3, loop)}%,{pct(loop - 0.5, loop)}%{{opacity:1}}100%{{opacity:0}}}}')
    rules += reveal_css('t', times, loop)
    # Every distinct reveal time now sits after LEAD > 0 (the type-in lead),
    # so every t{i} class needs its own animation binding.
    motion += [f'.t{i}{{animation:t{i} {loop}s linear infinite}}' for i in range(len(times))]
    motion.append(f'.cur{{animation:cur {loop}s step-end infinite}}.bl{{animation:blink 1s step-end infinite}}')
    motion.append(f'.reel{{animation:reel {loop}s linear infinite}}')
    style = (f'text{{font:12px {MONO};fill:{TEXT}}}.h{{font-size:11px;fill:{MUTED}}}'
             + ''.join(rules) + '@media (prefers-reduced-motion:no-preference){' + ''.join(motion) + '}')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{esc(title)}">',
           f'<title>{esc(title)}</title><style>{style}</style>',
           f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
           f'<path d="M0 {BAR}.5H{WIDTH}" stroke="{BORDER}"/>',
           f'<circle cx="18" cy="15" r="5" fill="#ff5f57"/><circle cx="36" cy="15" r="5" fill="#febc2e"/><circle cx="54" cy="15" r="5" fill="#28c840"/>',
           f'<text class="h" x="{WIDTH / 2}" y="19" text-anchor="middle">{esc(title)}</text>',
           '<g class="reel">',
           *body,
           f'<text class="t{len(times) - 1}" x="{PAD}" y="{cursor_y + 12}" xml:space="preserve"><tspan fill="{ACCENT}">$ </tspan></text>',
           f'<g class="cur"><rect class="bl" x="{cursor_x:.1f}" y="{cursor_y}" width="7" height="14" fill="{ACCENT}"/></g>',
           '</g>',
           f'<text class="h" x="{PAD}" y="{height - 12}">{esc(footer)}</text>',
           '</svg>']
    return '\n'.join(svg) + '\n'


# --- Loop 3: game start from the independent Springtrail frame references.

def story():
    """A full Springtrail play: title, Start, a run, a jump over a gap, a
    pause and resume, more running, then a patrol collision ends in RETRY.

    Every tick calls the independent interactions_reference.update() the same
    way the reference model's own tests do; the asserts below pin the exact
    button masks and outcomes so a change to the reference rules fails this
    generator instead of silently drawing a different game.
    """
    from interactions_reference import Game, update, PLAYING, PAUSED, RETRY
    states = {0: Game()}
    g = update(states[0], 128); states[1] = g                     # Start edge on the title screen
    for tick in range(2, 32):
        g = update(g, 33); states[tick] = g                       # Right+B: run toward the first gap
    assert (states[31].mode, states[31].player.x // 16, states[31].player.grounded) == (PLAYING, 84, True)
    g = update(g, 128); states[32] = g                             # Start edge: pause
    assert g.mode == PAUSED
    g = update(g, 0); states[33] = g                               # release, so the next Start is an edge
    g = update(g, 128); states[34] = g                             # Start edge: resume
    assert (states[34].mode, states[34].player.x // 16) == (PLAYING, 84)
    for tick in range(35, 75):
        g = update(g, 33); states[tick] = g                       # run up to the gap
    assert (states[74].player.x // 16, states[74].player.grounded) == (164, True)
    g = update(g, 49); states[75] = g                              # Right+B+A edge: jump
    assert not g.player.grounded
    for tick in range(76, 117):
        g = update(g, 33); states[tick] = g                       # airborne arc, clears the gap
    assert (states[116].player.x // 16, states[116].player.grounded, states[116].mode) == (248, True, PLAYING)
    for tick in range(117, 127):
        g = update(g, 33); states[tick] = g                       # runs on, into the patrol
    assert (states[126].mode, states[126].player.x // 16) == (RETRY, 268)
    return states


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


# Each sample is one real tick of story(), held on screen for its own
# duration: (id, tick or None for the title screen, hold seconds, the INPUT
# mask update() consumed to produce that tick (None hides the readout), and a
# short legend line. The jump is sampled along its arc so it reads as motion.
SAMPLES = (
    ('title', None, 2.0, None, 'TITLE screen: PRESS START'),
    ('stand', 1, 1.0, 128, 'Start (128) → PLAY'),
    ('run1', 20, 1.6, 33, 'Right+B (33): runs'),
    ('paused', 32, 2.2, 128, 'Start (128) → PAUSED'),
    ('resume', 34, 1.0, 128, 'Start (128): resumes'),
    ('run2', 58, 1.8, 33, 'Right+B (33): runs on'),
    ('prejump', 74, 1.0, 33, 'Nears the gap'),
    ('jump', 75, 0.5, 49, 'A (16): jumps'),
    ('rise', 85, 0.4, 33, 'Right+B (33): clears the gap'),
    ('apex', 95, 0.5, 33, 'Right+B (33): clears the gap'),
    ('fall', 105, 0.4, 33, 'Right+B (33): clears the gap'),
    ('land', 116, 1.0, 33, 'Lands, keeps running'),
    ('run3', 122, 1.2, 33, 'Right+B (33): runs on'),
    ('retry', 126, 2.4, None, 'Hits the patrol: RETRY'),
)
BUTTONS = ('Right', 'Left', 'Up', 'Down', 'A', 'B', 'Select', 'Start')
BUTTON_BITS = (1, 2, 4, 8, 16, 32, 64, 128)


def frame_window(cls, start, end, loop):
    """Visible only during [start, end); hidden the rest of the loop.

    Reduced motion falls back to the element's own authored opacity, so the
    last window (end == loop) is authored opaque as the finished still, and
    every earlier window is authored hidden (see game()).
    """
    head = f'0%,{pct(start - 0.01, loop)}%{{opacity:0}}{pct(start, loop)}%' if start > 0 else '0%'
    if end < loop:
        tail = f'{pct(end - 0.01, loop)}%{{opacity:1}}{pct(end, loop)}%,100%{{opacity:0}}'
    else:
        tail = '100%{opacity:1}'
    return f'@keyframes {cls}{{{head},{tail}}}'


def segments_css(cls, prop, on, off, windows, loop):
    """A property that switches to `on` during each of several windows."""
    parts, cursor = [], 0.0
    for start, end in windows:
        if start > cursor:
            parts.append(f'{pct(cursor, loop)}%,{pct(start - 0.01, loop)}%{{{prop}:{off}}}')
        parts.append(f'{pct(start, loop)}%,{pct(end - 0.01, loop)}%{{{prop}:{on}}}')
        cursor = end
    if cursor < loop:
        parts.append(f'{pct(cursor, loop)}%,100%{{{prop}:{off}}}')
    return f'@keyframes {cls}{{' + ''.join(parts) + '}'


def game():
    from hud_reference import image
    states = story()
    starts, elapsed = [], 0.0
    for _, _, hold, _, _ in SAMPLES:
        starts.append(elapsed)
        elapsed += hold
    loop = elapsed

    def full_frame(g):
        pixels = image(g)
        return {(x, y): pixels[y * 160 + x] for y in range(144) for x in range(160) if pixels[y * 160 + x]}

    frames_px = []
    for sample_id, tick, _, _, _ in SAMPLES:
        g = states[0] if tick is None else states[tick]
        frames_px.append(full_frame(g))

    scale, sx, sy = 3, PAD, BAR + PAD
    px, py = sx + 160 * scale + 40, sy + 8
    pills = []
    button_windows = {b: [] for b in BUTTONS}
    for i, (sample_id, tick, hold, mask, _) in enumerate(SAMPLES):
        if not mask:
            continue
        for label, bit in zip(BUTTONS, BUTTON_BITS):
            if mask & bit:
                button_windows[label].append((starts[i], starts[i] + hold))
    for index, label in enumerate(BUTTONS):
        column, row = divmod(index, 4)
        x, y = px + column * 120, py + 30 + row * 34
        cls = f' class="k{index}"' if button_windows[label] else ''
        pills.append(f'<g{cls}><rect x="{x}" y="{y}" width="108" height="26" rx="13" fill="{PANEL}" stroke="{BORDER}"/>'
                     f'<text x="{x + 54}" y="{y + 17}" text-anchor="middle">{label}</text></g>')
    my = py + 30 + 4 * 34 + 14
    mask_values = sorted({mask for _, _, _, mask, _ in SAMPLES if mask})
    masks = ''.join(f'<text class="mv{value}" x="{px}" y="{my}" opacity="0" xml:space="preserve">'
                    f'<tspan fill="{MUTED}">host input --mask </tspan>{value}</text>' for value in mask_values)
    ly = my + 40
    last_sample = len(SAMPLES) - 1
    legend = ''.join(f'<text class="g{i}" x="{px}" y="{ly}" opacity="{1 if i == last_sample else 0}">{i + 1}  {esc(text)}</text>'
                     for i, (_, _, _, _, text) in enumerate(SAMPLES))
    height = sy + 144 * scale + PAD + 22

    rules = [
        f'text{{font:13px {MONO};fill:{TEXT}}}.h{{font-size:11px;fill:{MUTED}}}',
        f'g[class^="k"] rect{{fill:{PANEL}}}',
    ]
    motion = []
    for i, (sample_id, tick, hold, mask, text) in enumerate(SAMPLES):
        start, end = starts[i], starts[i] + hold
        rules.append(frame_window(f'f{i}', start, end, loop))
        motion.append(f'.f{i}{{animation:f{i} {loop}s step-end infinite}}')
        rules.append(frame_window(f'g{i}', start, end, loop))
        motion.append(f'.g{i}{{animation:g{i} {loop}s step-end infinite}}')
    for value in mask_values:
        windows = [(starts[i], starts[i] + hold) for i, (_, _, hold, mask, _) in enumerate(SAMPLES) if mask == value]
        rules.append(segments_css(f'mv{value}', 'opacity', 1, 0, windows, loop))
        motion.append(f'.mv{value}{{animation:mv{value} {loop}s step-end infinite}}')
    for index, label in enumerate(BUTTONS):
        windows = button_windows[label]
        if not windows:
            continue
        rules.append(segments_css(f'kr{index}', 'fill', ACCENT, PANEL, windows, loop))
        rules.append(segments_css(f'kt{index}', 'fill', PANEL, TEXT, windows, loop))
        motion.append(f'.k{index} rect{{animation:kr{index} {loop}s step-end infinite}}'
                     f'.k{index} text{{animation:kt{index} {loop}s step-end infinite}}')
    style = (''.join(rules) + '@media (prefers-reduced-motion:no-preference){' + ''.join(motion) + '}')

    last = len(SAMPLES) - 1
    layers = []
    for i, pixels in enumerate(frames_px):
        opacity = '1' if i == last else '0'
        layers.append(f'<g class="f{i}" opacity="{opacity}">{paths(pixels)}</g>')

    label = ('Springtrail played through: title, Start, a run, a jump over a gap, a pause and '
            'resume, then a run into a patrol; every frame from the independent game reference')
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{label}">',
           f'<title>{label}</title><style>{style}</style>',
           f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
           f'<path d="M0 {BAR}.5H{WIDTH}" stroke="{BORDER}"/>',
           f'<circle cx="18" cy="15" r="5" fill="#ff5f57"/><circle cx="36" cy="15" r="5" fill="#febc2e"/><circle cx="54" cy="15" r="5" fill="#28c840"/>',
           f'<text class="h" x="{WIDTH / 2}" y="19" text-anchor="middle">Springtrail on the Game Boy screen · 160 × 144 · played at one tenth speed</text>',
           f'<g transform="translate({sx} {sy}) scale({scale})" shape-rendering="crispEdges">',
           '<rect width="160" height="144" fill="#ffffff"/>',
           *layers,
           '</g>',
           f'<rect x="{sx - .5}" y="{sy - .5}" width="{160 * scale + 1}" height="{144 * scale + 1}" fill="none" stroke="{BORDER}"/>',
           f'<text class="h" x="{px}" y="{py + 12}">JOYP buttons (UART INPUT mask)</text>',
           *pills, masks, legend,
           f'<text class="h" x="{PAD}" y="{height - 12}">Exact frames from src/dv/springtrail; every mode and mask above is the real reference state.</text>',
           '</svg>']
    return '\n'.join(svg) + '\n'


# --- Loops 7 and 8: frames captured on the DE10-Lite.
#
# Unlike game-start.svg, no pixel here is rendered on the host: each frame is
# the packed 160x144 snapshot the board returned over UART during one recorded
# session, encoded once into the committed archive under tools/wiki/board_frames/
# and embedded as an indexed-PNG data URI. board_frames.py records the byte
# counts that chose that encoding over the rect runs paths() draws.
#
# Scenes are (first frame index, hold seconds, legend line); every frame from
# one scene's index up to the next holds for that scene's duration.
LIBBET_SCENES = (
    (0, 2.2, 'Title: Start plays, Select demos'),
    (1, 1.2, 'Start (128): the floor loads with the LCD off'),
    (2, 0.6, 'Fade-in to the 2x2 tutorial floor'),
    (8, 1.0, 'Left (2): faces left, no valid neighbour'),
    (13, 1.0, 'Up (4): a valid roll, HUD reads 1 Combo 25% 1/04'),
    (18, 1.0, 'Right (1): off the floor, the wrong move busts the combo'),
    (23, 1.0, 'Down (8): the reverse of a one-shade roll is invalid'),
    (27, 2.4, 'Idle on the top-right cell, combo back to 0'),
)


# Springtrail on the board: the SHOWCASE samples of one frame_proofs.py full
# --showcase session, in capture order. Frame i is games()[SHOWCASE[i]]; the
# scene starts below name the frames the legend describes (index: k).
SPRINGTRAIL_SCENES = (
    (0, 2.2, 'Title, no input'),                                       # 0: k 0
    (1, 1.2, 'Start+B+Right (161): spawn at x 24, B+Right (33) held'),  # 1: k 3
    (2, 0.35, 'Runs right; the camera follows past x 72'),             # 2..12: k 12..92
    (13, 0.3, 'A held (49): the jump over the first gap'),             # 13..24: k 100..144
    (25, 0.5, 'Lands, then A held (49) over the patrol'),              # 25..28: k 151..166
    (29, 1.0, 'Camera 256: the 32-column ring wraps'),                 # 29: k 206
    (30, 0.5, 'A for one VBlank: a low hop over the second gap'),      # 30..32: k 232..248
    (33, 0.9, 'Lands at x 399 and walks under the brick'),             # 33: k 256
    (34, 0.5, 'A held (49): the jump over the third gap'),             # 34..38: k 359..397
    (39, 0.7, 'Camera clamps at 608; the goal is in view'),            # 39..41: k 441..465
    (42, 2.2, 'WON at the goal, score 0'),                             # 42: k 473
    (43, 1.2, 'Start (128): restart at spawn'),                        # 43: k 493
    (44, 0.6, 'B+Right (33) runs into the first gap'),                 # 44..46: k 594..601
    (47, 2.6, 'RETRY after the fall'),                                 # 47: k 604
)

# The loops whose every pixel came off the DE10-Lite rather than a host model.
BOARD_LOOPS = ('libbet-board', 'springtrail-board', 'springtrail-state-board')


def scene_plan(scenes, count):
    """Per-frame (hold, legend) from the scene table, and the loop length."""
    holds, legends = [None] * count, [None] * count
    bounds = [start for start, _, _ in scenes] + [count]
    for index, (start, hold, legend) in enumerate(scenes):
        for frame in range(start, bounds[index + 1]):
            holds[frame], legends[frame] = hold, legend
    assert all(hold is not None for hold in holds), 'the scene table must cover every frame'
    starts, elapsed = [], 0.0
    for hold in holds:
        starts.append(elapsed)
        elapsed += hold
    return holds, legends, starts, elapsed


def joypad_panel(px, py, windows, loop, rules, motion):
    """The eight JOYP pills, lit over the windows their button is held."""
    pills = []
    for index, label in enumerate(BUTTONS):
        column, row = divmod(index, 4)
        x, y = px + column * 120, py + 30 + row * 34
        cls = f' class="k{index}"' if windows[label] else ''
        pills.append(f'<g{cls}><rect x="{x}" y="{y}" width="108" height="26" rx="13" fill="{PANEL}" stroke="{BORDER}"/>'
                     f'<text x="{x + 54}" y="{y + 17}" text-anchor="middle">{label}</text></g>')
        if windows[label]:
            rules.append(segments_css(f'kr{index}', 'fill', ACCENT, PANEL, windows[label], loop))
            rules.append(segments_css(f'kt{index}', 'fill', PANEL, TEXT, windows[label], loop))
            motion.append(f'.k{index} rect{{animation:kr{index} {loop}s step-end infinite}}'
                          f'.k{index} text{{animation:kt{index} {loop}s step-end infinite}}')
    return pills


def merge(spans):
    """Adjacent frame windows joined, so one legend line animates once per scene."""
    merged = [list(spans[0])]
    for begin, end in spans[1:]:
        if begin <= merged[-1][1] + 1e-9:
            merged[-1][1] = end
        else:
            merged.append([begin, end])
    return [tuple(span) for span in merged]


def board_loop(name, heading, strip, footer, scenes):
    """One flipbook of frames the DE10-Lite returned, from the committed archive."""
    from board_frames import load
    archive = load(name)
    frames = archive['frames']
    assert archive['encoding']['chosen'] == 'indexed-png-data-uri', name
    holds, legends, starts, loop = scene_plan(scenes, len(frames))
    last = len(frames) - 1

    scale, sx, sy = 3, PAD, BAR + PAD
    px, py = sx + 160 * scale + 40, sy + 8
    windows = {button: [] for button in BUTTONS}
    for index, frame in enumerate(frames):
        for label, bit in zip(BUTTONS, BUTTON_BITS):
            if frame['mask'] & bit:
                windows[label].append((starts[index], starts[index] + holds[index]))
    windows = {label: merge(spans) if spans else [] for label, spans in windows.items()}

    rules = [f'text{{font:13px {MONO};fill:{TEXT}}}.h{{font-size:11px;fill:{MUTED}}}',
             f'g[class^="k"] rect{{fill:{PANEL}}}',
             'image{image-rendering:pixelated}']
    motion = []
    pills = joypad_panel(px, py, windows, loop, rules, motion)

    my = py + 30 + 4 * 34 + 14
    identity, layers = [], []
    for index, frame in enumerate(frames):
        start, end = starts[index], starts[index] + holds[index]
        opacity = '1' if index == last else '0'
        for prefix in ('f', 'i'):
            rules.append(frame_window(f'{prefix}{index}', start, end, loop))
            motion.append(f'.{prefix}{index}{{animation:{prefix}{index} {loop}s step-end infinite}}')
        layers.append(f'<image class="f{index}" opacity="{opacity}" width="160" height="144" '
                      f'href="{frame["png"]}"/>')
        identity.append(f'<text class="i{index}" x="{px}" y="{my}" opacity="{opacity}" xml:space="preserve">'
                        f'<tspan fill="{MUTED}">seq </tspan>{frame["seq"]}'
                        f'<tspan fill="{MUTED}">  mask </tspan>{frame["mask"]}</text>')

    ly, legend = sy + 144 * scale + 22, []
    for index, (_, _, text) in enumerate(scenes):
        covered = [i for i in range(len(frames)) if legends[i] == text]
        windows_for = merge([(starts[i], starts[i] + holds[i]) for i in covered])
        rules.append(segments_css(f'l{index}', 'opacity', 1, 0, windows_for, loop))
        motion.append(f'.l{index}{{animation:l{index} {loop}s step-end infinite}}')
        opacity = '1' if last in covered else '0'
        legend.append(f'<text class="l{index}" x="{PAD}" y="{ly}" opacity="{opacity}">{esc(text)}</text>')

    height = ly + PAD + 22
    style = ''.join(rules) + '@media (prefers-reduced-motion:no-preference){' + ''.join(motion) + '}'
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="{esc(heading)}">',
           f'<title>{esc(heading)}</title><style>{style}</style>',
           f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="10" fill="{PANEL}" stroke="{BORDER}"/>',
           f'<path d="M0 {BAR}.5H{WIDTH}" stroke="{BORDER}"/>',
           '<circle cx="18" cy="15" r="5" fill="#ff5f57"/><circle cx="36" cy="15" r="5" fill="#febc2e"/><circle cx="54" cy="15" r="5" fill="#28c840"/>',
           f'<text class="h" x="{WIDTH / 2}" y="19" text-anchor="middle">{esc(strip)}</text>',
           f'<g transform="translate({sx} {sy}) scale({scale})">',
           '<rect width="160" height="144" fill="#ffffff"/>',
           *layers,
           '</g>',
           f'<rect x="{sx - .5}" y="{sy - .5}" width="{160 * scale + 1}" height="{144 * scale + 1}" fill="none" stroke="{BORDER}"/>',
           f'<text class="h" x="{px}" y="{py + 12}">JOYP buttons (UART INPUT mask)</text>',
           *pills, *identity, *legend,
           f'<text class="h" x="{PAD}" y="{height - 12}">{esc(footer)}</text>',
           '</svg>']
    return '\n'.join(svg) + '\n'


def documents():
    return {
        'build-and-tests': terminal('Build and tests · nand2mario at 5ce0aa0 · 2026-09-11',
                                    'Real command output captured in one session. Long JSON lines are shortened with …; every shown field is verbatim.',
                                    BUILD, BUILD_LOOP),
        'board-session': terminal('Board session over UART · recorded shapes, not a live capture',
                                  'Commands/replies follow wiki/tools/n2m/host/SPEC.md; dots follow the 70224-dot frame; IDs elided.',
                                  BOARD, BOARD_LOOP),
        'game-start': game(),
        'reproducible-builds': terminal('Two clean builds, one identity · nand2mario at 396b0b4 · 2026-09-11',
                                        'Real sw build output in one shell; JSON shortened with …, every shown field verbatim; the tree is restored.',
                                        BUILDS, BUILDS_LOOP),
        'uart-debugging': terminal('Board session over UART · the recorded Libbet play, not a live capture',
                                   'Shapes follow wiki/tools/n2m/host/SPEC.md; dots, seq and IDs from src/dv/libbet/README.md; hashes elided.',
                                   SESSION, SESSION_LOOP),
        'libbet-board': board_loop(
            'libbet-board',
            'Libbet and the Magic Floor captured on the DE10-Lite: the title, a valid roll and the wrong '
            'move that busts the combo, every frame read back from the board over UART',
            'Libbet and the Magic Floor v0.08 \u00b7 Damian Yerrick, Zlib licence \u00b7 frames captured on the DE10-Lite over UART',
            'Frames captured on the board running the pinned third-party image; wiki/showcase/README.md records the session.',
            LIBBET_SCENES),
        'springtrail-board': board_loop(
            'springtrail-board',
            'Springtrail captured on the DE10-Lite: the title, Start, the run and jumps to the goal, WON, '
            'a restart and the fall that ends in RETRY, every frame read back from the board over UART',
            'Springtrail · the image the repository builds · frames captured on the DE10-Lite over UART',
            'Frames captured on the board during a frame_proofs.py showcase session; wiki/showcase/README.md records it.',
            SPRINGTRAIL_SCENES),
        'springtrail-state-board': board_loop(
            'springtrail-state-board',
            'Current Springtrail captured on the DE10-Lite: title, dynamic scene and first-stage WON',
            'Actual UART source frames | independent state reconstruction matched every shade',
            'Three aligned captures from springtrail_player.py compare; provenance in the frame archive.',
            [(0, 1, 'Title | actual source frame'), (1, 1, 'Dynamic scene | actual source frame'),
             (2, 1, 'First-stage WON | actual source frame')]),
        'verification': terminal('A checker that can fail · from retained Questa receipts, not a fresh capture',
                                 'Retained receipts, not a fresh run: python-joypad at f6fff8f, builder-smoke-fail at c89b47d; JSON shortened.',
                                 TESTS, TESTS_LOOP),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in documents().items():
        path = OUT / f'{name}.svg'
        path.write_text(text, encoding='utf-8', newline='\n')
        print(f'{path.relative_to(ROOT).as_posix()}: {path.stat().st_size} bytes')


if __name__ == '__main__':
    main()
