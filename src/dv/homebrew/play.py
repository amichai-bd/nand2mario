"""Boot each pinned homebrew image on the board and retain three frames of it.

One ordinary host session per game, with the same device lock, sequence journal
and machine mutex as `python tools/build.py host`: `--load` first runs
`host load --external <game>`, which verifies the pin's SHA-256 and reads every
byte back, then this driver resets, reaches the first screen on wall time and
walks a frozen input script with exact `RUN_DOTS` of one 70224-dot frame.

Plans:
  play    - the frozen SCRIPTS entry for one game; three retained snapshots.
  explore - no input, a snapshot every `--every` frames; used to find out what a
            game shows and which button leaves its title, before a script is
            frozen here.

This is boot-and-play evidence. No reference model exists for third-party code,
so nothing here checks pixels against an expectation; it records what the board
returned. Frames, diffs and `result.json` go under
`workdir/homebrew-play/<game>-<plan>-<stamp>/`; the transaction journal and
device selection go under the build tag.
"""
import argparse
import json
import subprocess
import sys
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'src/dv/libbet'))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.host.client import Client  # noqa: E402
from n2m.host.transport import session  # noqa: E402
from ci.storage import machine_lock  # noqa: E402
import frame_png  # noqa: E402

FRAME = 70224

# Frozen per-game scripts. `--intro-seconds` of wall-paced run from RESET
# reaches the first screen; every step below is exact whole frames:
#   run:N        - N frames with the mask unchanged
#   press:M:H    - apply mask M, hold H frames, release to 0
#   hold:M:N     - apply mask M and run N frames, leaving it applied
#   input:M      - apply mask M and run nothing
#   snap:LABEL   - retain the frame that just completed
# Exactly three `snap` steps are required: the opening screen and two frames of
# play. Masks are active high: Right 1, Left 2, Up 4, Down 8, A 16, B 32,
# Select 64, Start 128 (wiki/src/rtl/joypad/MAS_joypad.md).
SCRIPTS = {}


def parse_script(text):
    steps = []
    for raw in text.split(';'):
        item = raw.strip()
        if not item:
            continue
        kind, _, rest = item.partition(':')
        parts = [part for part in rest.split(':') if part != '']
        if kind == 'snap':
            steps.append(('snap', rest.strip()))
        elif kind == 'run':
            steps.append(('run', int(parts[0])))
        elif kind == 'input':
            steps.append(('input', int(parts[0])))
        elif kind in ('press', 'hold'):
            steps.append((kind, int(parts[0]), int(parts[1])))
        else:
            raise ValueError('unknown script step: ' + item)
        if kind in ('run', 'press', 'hold') and steps[-1][-1] <= 0:
            raise ValueError('step count must be positive: ' + item)
    return steps


class Driver:
    def __init__(self, client, out, journal):
        self.client = client
        self.out = out
        self.journal = journal
        self.frames = []
        self.inputs = []
        self.mask = 0
        self.last_pixels = None

    def log(self, **entry):
        entry['time'] = datetime.now(timezone.utc).isoformat()
        self.journal.append(entry)
        print(json.dumps(entry), flush=True)

    def regs(self, names=('STATE', 'IMAGE_VALID', 'PROFILE', 'INPUT', 'INPUT_SOURCE', 'INPUT_EFFECTIVE')):
        return {n: self.client.read_host(getattr(abi, 'HOST_REG_' + n)) for n in names}

    def counters(self):
        c = self.client
        dot = c.read_host(abi.HOST_REG_DOT_LO) | (c.read_host(abi.HOST_REG_DOT_HI) << 32)
        ret = c.read_host(abi.HOST_REG_RETIRE_LO) | (c.read_host(abi.HOST_REG_RETIRE_HI) << 32)
        return {'dot': dot, 'retire': ret}

    def input(self, mask, label):
        applied = self.client.control('INPUT', mask)
        self.mask = mask
        eff = self.regs(('INPUT', 'INPUT_EFFECTIVE'))
        self.inputs.append({'label': label, 'mask': mask, 'applied': applied, **eff})
        self.log(event='input', label=label, mask=mask, applied=applied, **eff)
        return applied

    def frames_run(self, count, label):
        first = last = None
        for _ in range(count):
            last = self.client.run_dots(FRAME)
            first = first or last
        self.log(event='run-frames', label=label, frames=count, dots=count * FRAME, first=first, last=last)
        return last

    def snapshot(self, label, scale=2):
        metadata, packed = self.client.snapshot()
        pixels = frame_png.unpack(packed)
        name = f'{len(self.frames):02d}-{label}'
        (self.out / (name + '.2bpp')).write_bytes(packed)
        frame_png.write_frame(pixels, self.out / (name + '.png'), scale)
        entry = {'index': len(self.frames), 'label': label, 'metadata': metadata, 'mask': self.mask,
                 'crc32': f'{zlib.crc32(packed) & 0xffffffff:08x}',
                 'histogram': [pixels.count(s) for s in range(4)],
                 'png': (self.out / (name + '.png')).as_posix()}
        if self.last_pixels is not None:
            diff = sum(1 for a, b in zip(self.last_pixels, pixels) if a != b)
            entry['pixels_changed_from_previous'] = diff
            if diff:
                frame_png.write_diff(self.last_pixels, pixels, self.out / (name + '-diff.png'), scale)
        self.frames.append(entry)
        self.last_pixels = pixels
        self.log(event='snapshot', **entry)
        return entry


def to_first_screen(d, args):
    """Wall time paces only the stretch from RESET; every later step is exact."""
    d.log(event='reset', result=d.client.control('RESET'))
    d.client.control('RUN')
    time.sleep(args.intro_seconds)
    d.log(event='halt', result=d.client.control('HALT'), counters=d.counters())


def plan_play(d, args, steps):
    to_first_screen(d, args)
    for step in steps:
        kind = step[0]
        if kind == 'snap':
            d.snapshot(step[1])
        elif kind == 'run':
            d.frames_run(step[1], f'run-{step[1]}')
        elif kind == 'input':
            d.input(step[1], f'input-{step[1]}')
        elif kind == 'hold':
            d.input(step[1], f'hold-{step[1]}')
            d.frames_run(step[2], f'hold-{step[1]}-{step[2]}')
        elif kind == 'press':
            d.input(step[1], f'press-{step[1]}')
            d.frames_run(step[2], f'press-{step[1]}-{step[2]}')
            d.input(0, f'release-{step[1]}')
    d.log(event='final', counters=d.counters(), regs=d.regs())


def plan_explore(d, args, steps):
    to_first_screen(d, args)
    if args.mask:
        d.input(args.mask, f'explore-{args.mask}')
    d.snapshot('explore-0000')
    for index in range(1, args.samples + 1):
        d.frames_run(args.every, f'explore-{index}')
        d.snapshot(f'explore-{index * args.every:04d}')
    if args.mask:
        d.input(0, 'explore-release')
    d.log(event='final', counters=d.counters(), regs=d.regs())


def load_external(game, args):
    """`host load --external <game>`: the pinned digest and a full readback."""
    command = [sys.executable, str(ROOT / 'tools/build.py'), 'host', 'load', '--external', game,
               '--uart-port', args.uart_port, '--tag', args.tag, '--json']
    print('LOAD', ' '.join(command), flush=True)
    done = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    print(done.stdout.strip(), flush=True)
    if done.returncode:
        print(done.stderr.strip(), flush=True)
        raise ValueError(f'host load --external {game} failed: {done.returncode}')
    return json.loads(done.stdout.strip().splitlines()[-1])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('plan', choices=('play', 'explore'))
    p.add_argument('game', help='a pinned external image name from tools/n2m/dependencies.json')
    p.add_argument('--uart-port', required=True)
    p.add_argument('--expected-build-id', required=True, help='reviewed wire build ID, 32 hex digits')
    p.add_argument('--tag', default='homebrew-play')
    p.add_argument('--load', action='store_true', help='run host load --external <game> first')
    p.add_argument('--script', help='override the frozen script for this game')
    p.add_argument('--intro-seconds', type=float, default=6.0)
    p.add_argument('--every', type=int, default=30, help='explore: frames between snapshots')
    p.add_argument('--samples', type=int, default=8, help='explore: snapshots after the first')
    p.add_argument('--mask', type=int, default=0, help='explore: a mask held for the whole run')
    args = p.parse_args()

    text = args.script if args.script is not None else SCRIPTS.get(args.game)
    steps = parse_script(text) if text else []
    if args.plan == 'play':
        if not steps:
            p.error(f'no frozen script for {args.game}; pass --script or explore first')
        if sum(1 for step in steps if step[0] == 'snap') != 3:
            p.error('a play script retains exactly three frames')

    stamp = datetime.now(timezone.utc).strftime('%H%M%S')
    out = ROOT / 'workdir/homebrew-play' / f'{args.game}-{args.plan}-{stamp}'
    out.mkdir(parents=True)
    folder = ROOT / 'workdir/builds' / args.tag / 'host' / f'script-{args.game}-{args.plan}' / out.name
    folder.mkdir(parents=True)
    ns = SimpleNamespace(uart_port=args.uart_port, uart_vid=None, uart_pid=None, uart_identity=None,
                         endpoint_restarted=False, tag=args.tag, json=True)
    common = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute',
                                      '--git-common-dir'], text=True).strip()
    state_root = Path(common).parent / 'workdir/host-sessions'
    journal = []
    transactions = folder / 'transactions.jsonl'

    def record(entry):
        with transactions.open('a', encoding='utf-8') as s:
            s.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), **entry}, sort_keys=True) + '\n')

    result = {'status': 'FAIL', 'plan': args.plan, 'game': args.game, 'script': text, 'args': vars(args),
              'out': out.as_posix(), 'host_folder': folder.as_posix()}
    client = None
    started = time.monotonic()
    try:
        if args.load:
            result['load'] = load_external(args.game, args)
        with machine_lock(1357311510), session(folder, ns, state_root) as (transport, sequence, persist, _):
            client = Client(transport, sequence=sequence, record=record, persist=persist)
            d = Driver(client, out, journal)
            result['endpoint'] = client.identify()
            if result['endpoint']['build_id'] != args.expected_build_id.lower():
                raise ValueError('wire build mismatch: ' + result['endpoint']['build_id'])
            before = d.regs()
            d.log(event='preflight', endpoint=result['endpoint'], regs=before, counters=d.counters())
            expected = dict(STATE=abi.STATE_PAUSED, IMAGE_VALID=1, PROFILE=abi.PROFILE_DIRECT_ID,
                            INPUT=0, INPUT_SOURCE=0, INPUT_EFFECTIVE=0)
            if before != expected:
                raise ValueError('preflight requires a paused valid image with neutral UART input')
            try:
                {'play': plan_play, 'explore': plan_explore}[args.plan](d, args, steps)
                result['status'] = 'PASS'
            finally:
                # Leave the board paused with input released; never send after
                # an uncertain completion.
                if not client.uncertain:
                    if client.read_host(abi.HOST_REG_STATE) != abi.STATE_PAUSED:
                        d.log(event='cleanup-halt', result=client.control('HALT'))
                    if client.read_host(abi.HOST_REG_INPUT) != 0:
                        d.log(event='cleanup-input', result=client.control('INPUT', 0))
                    d.log(event='end', regs=d.regs(), counters=d.counters(), sequence=client.sequence)
                result.update(frames=d.frames, inputs=d.inputs, journal=journal)
    except Exception as error:
        result['error'] = repr(error)
        print('ERROR', repr(error), flush=True)
    result['uncertain'] = None if client is None else client.uncertain
    result['wall_seconds'] = round(time.monotonic() - started, 3)
    (out / 'result.json').write_text(json.dumps(result, indent=1, sort_keys=True))
    print('RESULT', result['status'], 'uncertain=', result['uncertain'], 'wall=', result['wall_seconds'],
          out.as_posix())
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
