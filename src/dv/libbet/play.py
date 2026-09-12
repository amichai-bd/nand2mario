"""Drive Libbet over UART with exact frame pacing; retain every frame and dot.

One durable host session with the same device lock, sequence journal and
machine mutex as `python tools/build.py host`. Plans:
  play     - title, Start, four directional presses, halt.
  demo     - title, Select, free-running attract mode snapshots up to 30 s.
  showcase - the play sequence sampled evenly for wiki/showcase/libbet-board.svg.
Frames, diffs and `result.json` go under `workdir/libbet-play/<plan>-<stamp>/`;
the transaction journal and device selection go under the build tag.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.host.client import Client  # noqa: E402
from n2m.host.transport import session  # noqa: E402
from ci.storage import machine_lock  # noqa: E402
import frame_png  # noqa: E402

FRAME = 70224
DIRECTIONS = (('left', abi.BUTTON_LEFT), ('up', abi.BUTTON_UP),
              ('right', abi.BUTTON_RIGHT), ('down', abi.BUTTON_DOWN))
# Frozen showcase sampling, in frames. The recorded play session
# (src/dv/libbet/README.md) fixes what each sample shows: the fade-in reaches
# the 2x2 tutorial floor by start+60, Left only faces, Up is the valid roll to
# `1 Combo 25% 1/04`, Right is the wrong move that busts the combo back to
# `0 Combo`, and Down is invalid as the reverse of a one-shade roll.
FADE_SAMPLES, FADE_STEP = 6, 10
MOVE_SAMPLES, MOVE_STEP = 4, 8


class Driver:
    def __init__(self, client, out, journal):
        self.client = client
        self.out = out
        self.journal = journal
        self.frames = []
        self.inputs = []
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
        entry = {'index': len(self.frames), 'label': label, 'metadata': metadata,
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
        return pixels, entry


def to_title(d, args):
    # The intro roll and the copyright card take about 7.5 s from reset; the
    # card ignores Start for its first 120 vblanks. Wall time paces only this
    # stretch; every later step is exact RUN_DOTS frames.
    d.log(event='reset', result=d.client.control('RESET'))
    d.client.control('RUN')
    time.sleep(args.intro_seconds)
    d.log(event='halt', result=d.client.control('HALT'), counters=d.counters())
    d.snapshot('title')


def press(d, mask, name, hold):
    # Libbet's read_pad forms new_keys against the previous vblank's cur_keys,
    # so one press seen by two consecutive reads registers once; release is
    # not required for the title, and in-game rolls need a fresh press.
    d.input(mask, f'{name}-press')
    d.frames_run(hold, f'{name}-held')
    d.snapshot(f'{name}-held')
    d.input(0, f'{name}-release')


def plan_play(d, args):
    to_title(d, args)
    d.input(abi.BUTTON_START, 'start-press')
    d.frames_run(args.hold, 'start-held')
    d.input(0, 'start-release')
    d.snapshot('after-start-release')
    d.frames_run(10, 'after-start')
    d.snapshot('start+10')
    d.frames_run(50, 'fade-in')
    d.snapshot('start+60')
    for name, mask in DIRECTIONS:
        press(d, mask, name, args.hold)
        d.frames_run(8, f'{name}+8')
        d.snapshot(f'{name}+8')
        d.frames_run(24, f'{name}+32')
        d.snapshot(f'{name}+32')
    d.log(event='final', counters=d.counters(), regs=d.regs())


def sample_run(d, count, step, label):
    """`count` snapshots, `step` exact frames apart, with no input change."""
    for index in range(count):
        d.frames_run(step, f'{label}+{(index + 1) * step}')
        d.snapshot(f'{label}+{(index + 1) * step}')


def plan_showcase(d, args):
    """The play sequence, sampled evenly, retained for the wiki loop."""
    to_title(d, args)
    d.input(abi.BUTTON_START, 'start-press')
    d.frames_run(args.hold, 'start-held')
    d.input(0, 'start-release')
    d.snapshot('after-start-release')
    sample_run(d, FADE_SAMPLES, FADE_STEP, 'start')
    for name, mask in DIRECTIONS:
        d.input(mask, f'{name}-press')
        d.frames_run(args.hold, f'{name}-held')
        d.snapshot(f'{name}-held')
        d.input(0, f'{name}-release')
        sample_run(d, MOVE_SAMPLES, MOVE_STEP, name)
    d.log(event='final', counters=d.counters(), regs=d.regs())


def plan_demo(d, args):
    to_title(d, args)
    d.input(abi.BUTTON_SELECT, 'select-press')
    d.frames_run(args.hold, 'select-held')
    d.input(0, 'select-release')
    d.snapshot('after-select-release')
    d.client.control('RUN')
    start = time.monotonic()
    for at in (2, 5, 10, 15, 20, 25, 30):
        while time.monotonic() - start < at:
            time.sleep(0.05)
        d.snapshot(f'demo-{at:02d}s')
    d.log(event='halt', result=d.client.control('HALT'), counters=d.counters(), regs=d.regs())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('plan', choices=('play', 'demo', 'showcase'))
    p.add_argument('--uart-port', required=True)
    p.add_argument('--expected-build-id', required=True, help='reviewed wire build ID, 32 hex digits')
    p.add_argument('--tag', default='libbet-play')
    p.add_argument('--hold', type=int, default=3, help='frames to hold each press')
    p.add_argument('--intro-seconds', type=float, default=8.0)
    args = p.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%H%M%S')
    out = ROOT / 'workdir/libbet-play' / f'{args.plan}-{stamp}'
    out.mkdir(parents=True)
    folder = ROOT / 'workdir/builds' / args.tag / 'host' / f'script-{args.plan}' / out.name
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

    result = {'status': 'FAIL', 'plan': args.plan, 'args': vars(args), 'out': out.as_posix(),
              'host_folder': folder.as_posix()}
    client = None
    started = time.monotonic()
    try:
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
                {'play': plan_play, 'demo': plan_demo, 'showcase': plan_showcase}[args.plan](d, args)
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
