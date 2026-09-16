"""Boot and play the original Stackdrop image on the DE10-Lite over UART.

This is boot-and-play evidence, not a correctness proof. Stackdrop's rules are
already proved against the independent reference model in `src/dv/stackdrop/`;
nothing here re-checks them. What it shows is that the built image loads, boots,
renders and answers scripted input on real hardware.

One durable host session with the same device lock, sequence journal and machine
mutex as `python tools/build.py host`. Two phases, recorded separately:
  free-run   - RESET, RUN, wall-paced wait, HALT, one snapshot of the title,
               and one more free-run stretch after the clear where gravity
               alone moves the piece at native rate with no input applied.
  stepped    - every play action is exact `RUN_DOTS` whole frames, so the
               one-row-per-second gravity never runs ahead of a capture.

The scripted line fills the bottom row with the first four pieces of the frozen
I, O, T, L, J, S, Z cycle and clears it:
  I  left 2, hard drop  -> columns 0..3
  O  right 1, hard drop -> columns 4,5
  T  left 2, hard drop  -> parks above the finished columns
  L  rotate, right 3, hard drop -> columns 6,7, completing the row

With `--package`, the session first runs `host load --package`, which verifies
the built image's SHA-256 and reads all 32768 bytes back, so the archive can
cite the image it played rather than assume it.

Frames, decoded states and `result.json` go under `workdir/stackdrop-play/`;
the transaction journal and device selection go under the build tag. No frame
bytes or decoded images are committed.
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.host.client import Client  # noqa: E402
from n2m.host.transport import session  # noqa: E402
from ci.storage import machine_lock  # noqa: E402
import frame_png  # noqa: E402
from screen import decode  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / 'fixtures'

FRAME = 70224
# Frozen script: (button, repeats, note). One action per press, because the game
# acts on released-to-pressed edges sampled once per VBlank.
SCRIPT = (
    ('start', abi.BUTTON_START, 1, 'leave the title'),
    ('i-left', abi.BUTTON_LEFT, 2, 'I to columns 0..3'),
    ('i-drop', abi.BUTTON_B, 1, 'hard drop I'),
    ('o-right', abi.BUTTON_RIGHT, 1, 'O to columns 4,5'),
    ('o-drop', abi.BUTTON_B, 1, 'hard drop O'),
    ('t-left', abi.BUTTON_LEFT, 2, 'T to columns 0..2'),
    ('t-drop', abi.BUTTON_B, 1, 'hard drop T'),
    ('l-rotate', abi.BUTTON_A, 1, 'L clockwise once'),
    ('l-right', abi.BUTTON_RIGHT, 3, 'L to columns 6,7'),
    ('l-drop', abi.BUTTON_B, 1, 'hard drop L, completing the bottom row'),
)


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
        print(json.dumps(entry, sort_keys=True), flush=True)

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
        last = None
        for _ in range(count):
            last = self.client.run_dots(FRAME)
        self.log(event='run-frames', label=label, frames=count, dots=count * FRAME, last=last)
        return last

    def snapshot(self, label, mode, scale=2):
        metadata, packed = self.client.snapshot()
        pixels = frame_png.unpack(packed)
        name = f'{len(self.frames):02d}-{label}'
        (self.out / (name + '.2bpp')).write_bytes(packed)
        frame_png.write_frame(pixels, self.out / (name + '.png'), scale)
        entry = {'index': len(self.frames), 'label': label, 'mode': mode, 'metadata': metadata,
                 'crc32': f'{zlib.crc32(packed) & 0xffffffff:08x}',
                 'histogram': [pixels.count(s) for s in range(4)],
                 'png': (self.out / (name + '.png')).as_posix()}
        try:
            state = decode(pixels)
            entry['decoded'] = {'status': state['status'], 'score': state['score'],
                                'rotation': state['rotation'], 'next_piece': state['next_piece'],
                                'active': state['active'],
                                'occupied': [i for i, v in enumerate(state['board']) if v],
                                'rows': [''.join(str(state['board'][y * 8 + x]) for x in range(8))
                                         for y in range(12)]}
        except ValueError as error:
            # A frame the decoder rejects is retained and reported, not hidden.
            entry['decode_error'] = repr(error)
        if entry.get('decoded', {}).get('status') == 0 or label == 'title':
            # Pixel-for-pixel comparison with the frozen independent title fixture.
            reference = FIXTURES / 'title.hex'
            frozen = bytes.fromhex(reference.read_text().replace('\n', ''))
            entry['title_reference'] = {
                'fixture': reference.relative_to(ROOT).as_posix(),
                'crc32': f'{zlib.crc32(frozen) & 0xffffffff:08x}',
                'matches': packed == frozen,
                'pixels_different': sum(1 for a, b in zip(frame_png.unpack(frozen), pixels) if a != b)}
        if self.last_pixels is not None:
            entry['pixels_changed_from_previous'] = sum(
                1 for a, b in zip(self.last_pixels, pixels) if a != b)
        self.frames.append(entry)
        self.last_pixels = pixels
        self.log(event='snapshot', **{k: v for k, v in entry.items() if k != 'decoded'},
                 decoded=entry.get('decoded', {}).get('rows'))
        return entry


def to_title(d, args):
    """Free-run: the board runs at native rate; only this stretch uses wall time."""
    d.log(event='reset', result=d.client.control('RESET'))
    d.client.control('RUN')
    time.sleep(args.intro_seconds)
    d.log(event='halt', result=d.client.control('HALT'), counters=d.counters())
    return d.snapshot('title', 'free-run')


def action(d, label, mask, hold, gap, mode):
    """One released-to-pressed edge: hold whole frames, release, settle, capture."""
    d.input(mask, f'{label}-press')
    d.frames_run(hold, f'{label}-held')
    d.input(0, f'{label}-release')
    d.frames_run(gap, f'{label}-settle')
    return d.snapshot(label, mode)


def play(d, args):
    title = to_title(d, args)
    if title.get('decoded', {}).get('status') != 0 or not title['title_reference']['matches']:
        raise ValueError('the free-run capture is not the Stackdrop title screen')
    if args.title_only:
        # Boot to the title and stop, leaving the board paused on it.
        d.log(event='final', score=title['decoded']['score'], counters=d.counters(), regs=d.regs())
        return
    for label, mask, repeats, _note in SCRIPT:
        for index in range(repeats):
            suffix = '' if repeats == 1 else f'-{index + 1}'
            action(d, label + suffix, mask, args.hold, args.gap, 'stepped')
    # Free-run again after the clear: no input, native rate, so gravity alone
    # moves the spawned piece. One row per second is the frozen gravity rate.
    d.client.control('RUN')
    time.sleep(args.gravity_seconds)
    d.log(event='halt', result=d.client.control('HALT'), counters=d.counters())
    d.snapshot('gravity-free-run', 'free-run')
    final = d.frames[-1].get('decoded', {})
    d.log(event='final', score=final.get('score'), rows=final.get('rows'),
          counters=d.counters(), regs=d.regs())


def load_package(args):
    """`host load --package <result.json>`: the built digest and a full readback.

    The driver cannot read the cartridge back itself, so the load the archive
    cites is this verified one, not an unchecked claim about what was resident.
    """
    command = [sys.executable, str(ROOT / 'tools/build.py'), 'host', 'load',
               '--package', args.package, '--uart-port', args.uart_port,
               '--tag', args.tag, '--json']
    print('LOAD', ' '.join(command), flush=True)
    done = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    print(done.stdout.strip(), flush=True)
    if done.returncode:
        print(done.stderr.strip(), flush=True)
        raise ValueError(f'host load --package failed: {done.returncode}')
    return json.loads(done.stdout.strip().splitlines()[-1])


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--uart-port', required=True)
    p.add_argument('--package', help='immutable sw/build/stackdrop/runs/<attempt>/result.json '
                                     'to load and verify before the session')
    p.add_argument('--uart-vid')
    p.add_argument('--uart-pid')
    p.add_argument('--uart-identity')
    p.add_argument('--expected-build-id', required=True, help='reviewed wire build ID, 32 hex digits')
    p.add_argument('--tag', default='stackdrop-play')
    p.add_argument('--hold', type=int, default=3, help='whole frames to hold each press')
    p.add_argument('--gap', type=int, default=3, help='whole frames after each release')
    p.add_argument('--intro-seconds', type=float, default=2.0)
    p.add_argument('--gravity-seconds', type=float, default=4.0,
                   help='free-run seconds after the clear, with no input')
    p.add_argument('--title-only', action='store_true',
                   help='boot to the title, capture it and stop, leaving the board paused there')
    args = p.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%H%M%S')
    out = ROOT / 'workdir/stackdrop-play' / f'play-{stamp}'
    out.mkdir(parents=True)
    folder = ROOT / 'workdir/builds' / args.tag / 'host' / 'script-play' / out.name
    folder.mkdir(parents=True)
    ns = SimpleNamespace(uart_port=args.uart_port, uart_vid=args.uart_vid, uart_pid=args.uart_pid,
                         uart_identity=args.uart_identity, endpoint_restarted=False,
                         tag=args.tag, json=True)
    common = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute',
                                      '--git-common-dir'], text=True).strip()
    state_root = Path(common).parent / 'workdir/host-sessions'
    journal = []
    transactions = folder / 'transactions.jsonl'

    def record(entry):
        with transactions.open('a', encoding='utf-8') as s:
            s.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), **entry},
                               sort_keys=True) + '\n')

    result = {'status': 'FAIL', 'args': vars(args), 'out': out.as_posix(),
              'host_folder': folder.as_posix(),
              'evidence_boundary': 'boot-and-play on hardware; not a correctness proof'}
    client = None
    started = time.monotonic()
    try:
        if args.package:
            result['load'] = load_package(args)
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
                play(d, args)
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
    print('RESULT', result['status'], 'uncertain=', result['uncertain'],
          'wall=', result['wall_seconds'], out.as_posix())
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
