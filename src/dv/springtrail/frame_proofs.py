"""Scrolling, win and death/retry frames on the image the repository builds today.

The frozen script is FRAME_PROOFS.md. The board stays paused between fixed
checkpoints C(n) = LCD + n*PERIOD + 4096, reached with exact RUN_DOTS counts,
so every input is applied at a known dot in the visible interval of frame n
and sampled in VBlank n. Expected frames come only from the independent
models, including the block layer the image draws; the loaded bytes must equal the hash of the build the launcher just
produced from current sources. `run` drives one Client; `main` is the
committed launcher with its own whole-process supervisor, machine mutex and
durable session, shared with `endurance.py`.
"""
import argparse
import hashlib
import json
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
from n2m.records import atomic_json, file_hash  # noqa: E402
from endurance import LCD, PERIOD, MACHINE_MUTEX, build_rom, supervise, decode  # noqa: E402
from blocks_frames import image  # noqa: E402
from blocks_reference import INTACT  # noqa: E402
from power_reference import World, TITLE, PLAYING, RETRY, WON, SMALL, update  # noqa: E402

# The current image carries the block and power layers, so the game model is
# power_reference over the motion player and the pixel model is blocks_frames,
# which draws the block layer in the state the script leaves it.
START = World()
INTACT_BLOCKS = (INTACT, INTACT, INTACT, INTACT)

PHASE = 4096
PIXELS = 23040
# Sampled JOYP masks per VBlank from VBlank 2 on; VBlank 0 and 1 sample 0.
# Mask k is sampled in VBlank k, computed in visible frame k+1, published in
# VBlank k+1 and displayed in source frame k+2, which snapshot C(k+3) returns.
FIRST_VBLANK = 2
SCRIPT = (
    # Success over the current motion model: Start+B+Right, then B+Right with
    # held A jumps over the first gap and the enemy patrol, a one-VBlank A tap
    # over the second gap, and a held A jump over the third gap. WON after
    # update 471 with score 0; no item lies on this route and no block is
    # touched: the brick at column 52 stands right after the second gap, so a
    # held jump there lands against its side, while the tap lands at x 399
    # and walks under it.
    (161, 1), (33, 96), (49, 12), (33, 40), (49, 12), (33, 64), (49, 1),
    (33, 127), (49, 12), (33, 106),
    # Start restart from WON, then neutral while the ring restores 16 pairs.
    (128, 1), (0, 20),
    # Death: B+Right from spawn runs into the first gap; RETRY after 130.
    (33, 110),
    # Start restart from RETRY, then the same neutral settle.
    (128, 1), (0, 20),
)
# Name -> game index k. Frame k+1 displays games()[k]; snapshot at C(k+2).
CAPTURES = (('title', 0), ('spawn', 3), ('first-camera', 36), ('entering-column', 99),
            ('scroll-wrap', 206), ('camera-clamp', 441), ('won', 473), ('won-restart', 493),
            ('retry', 604), ('retry-restart', 625))
# Literal (mode, x, y, camera, score, timer, enemy_x, enemy_vx, blocks, power)
# per capture, written from the rules before any DUT run; a model change must
# fail here. The route touches no block, so every capture shows the four
# blocks intact and the small player.
EXPECTED = {
    'title': (TITLE, 384, 1792, 0, 0, 0, 4096, 8, INTACT_BLOCKS, SMALL),
    'spawn': (PLAYING, 400, 1792, 0, 0, 1, 4104, 8, INTACT_BLOCKS, SMALL),
    'first-camera': (PLAYING, 1168, 1792, 1, 0, 34, 4368, 8, INTACT_BLOCKS, SMALL),
    'entering-column': (PLAYING, 2688, 1792, 96, 0, 97, 4600, -8, INTACT_BLOCKS, SMALL),
    'scroll-wrap': (PLAYING, 5248, 1792, 256, 0, 204, 3936, 8, INTACT_BLOCKS, SMALL),
    'camera-clamp': (PLAYING, 10896, 1792, 608, 0, 439, 4024, 8, INTACT_BLOCKS, SMALL),
    'won': (WON, 11664, 1792, 608, 0, 471, 4280, 8, INTACT_BLOCKS, SMALL),
    'won-restart': (PLAYING, 384, 1792, 0, 0, 19, 4248, 8, INTACT_BLOCKS, SMALL),
    'retry': (RETRY, 2992, 2304, 115, 0, 130, 4336, -8, INTACT_BLOCKS, SMALL),
    'retry-restart': (PLAYING, 384, 1792, 0, 0, 20, 4256, 8, INTACT_BLOCKS, SMALL),
}
# The ring restores two columns per publication; a restart from a scrolled
# camera needs 16 publications before the model's complete world is displayed.
RESTORE_FRAMES = 16
PLANS = {'short': 'entering-column', 'full': 'retry-restart'}
CAPS = {'short': 300, 'full': 300}


def checkpoint(n):
    return LCD + n * PERIOD + PHASE


def samples():
    """The mask each VBlank samples, from VBlank 0."""
    return [0] * FIRST_VBLANK + [mask for mask, count in SCRIPT for _ in range(count)]


_games = None


def games():
    """games()[k] is the state after the first k sampled updates."""
    global _games
    if _games is None:
        result = [START]
        for mask in samples():
            result.append(update(result[-1], mask))
        _games = tuple(result)
    return _games


def anchor(game):
    p = game.player
    return (game.mode, p.x, p.y, p.camera, game.score, game.timer, game.enemy_x, game.enemy_vx,
            game.blocks, game.power)


def plan_captures(plan):
    assert plan in PLANS, 'FRAME_PLAN'
    names = [name for name, _ in CAPTURES]
    return CAPTURES[:names.index(PLANS[plan]) + 1]


def history(k):
    """Input history before games()[k]: (mask, count) runs of the sampled masks."""
    runs = []
    for mask in samples()[:k]:
        if runs and runs[-1][0] == mask:
            runs[-1][1] += 1
        else:
            runs.append([mask, 1])
    return [tuple(run) for run in runs]


def require_current_rom(rom, expected_sha256):
    """The loaded bytes must be the build just produced from current sources."""
    actual = hashlib.sha256(rom).hexdigest()
    assert len(rom) == 32768 and actual == expected_sha256, \
        'FRAME_ROM: image differs from the current build'
    return actual


def unpack(packed):
    assert len(packed) == 5760, 'FRAME_SIZE'
    return bytes((b >> shift) & 3 for b in packed for shift in (0, 2, 4, 6))


def run(client, rom, root, *, epoch, plan, rom_sha256, deadline=None, clock=time.monotonic):
    """One paused history from a full load through the plan's last capture."""
    require_current_rom(rom, rom_sha256)
    captures = plan_captures(plan)
    states = games()
    for name, k in captures:
        assert anchor(states[k]) == EXPECTED[name], f'FRAME_PLAN_STATE {name}'
    last = captures[-1][1] + 2
    masks = samples()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    log = []
    mask = 0
    armed = False
    result = dict(status='FAIL', plan=plan, rom_sha256=rom_sha256, lcd=LCD, period=PERIOD,
                  script=SCRIPT, captures=[], inputs=[])

    def record(kind, **fields):
        row = dict(kind=kind, wall=clock(), **fields)
        log.append(row)
        atomic_json(root/'journal.json', log)

    def within_cap(where):
        assert deadline is None or clock() < deadline, f'FRAME_WALL_CAP {where}'

    def wide(low, high):
        for _ in range(3):
            first = client.read_host(high)
            value = client.read_host(low)
            if first == client.read_host(high):
                return (first << 32) | value
        raise AssertionError('FRAME_COUNTER_ROLLOVER')

    def public():
        state = dict(dot=wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI),
                     retired=wide(abi.HOST_REG_RETIRE_LO, abi.HOST_REG_RETIRE_HI))
        assert client.read_host(abi.HOST_REG_STATE) == abi.STATE_PAUSED, 'FRAME_STATE'
        assert client.read_host(abi.HOST_REG_IMAGE_VALID) == 1, 'FRAME_IMAGE'
        assert client.read_host(abi.HOST_REG_INPUT_SOURCE) == abi.INPUT_SOURCE_UART, 'FRAME_SOURCE'
        assert client.read_host(abi.HOST_REG_INPUT) == client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) == mask, 'FRAME_INPUT'
        return state

    def buttons(value, dot):
        nonlocal mask
        reply = client.control('INPUT', value)
        assert reply['dot'] == dot, 'FRAME_INPUT_DOT'
        mask = value
        row = dict(mask=value, dot=dot, vblank=(dot-LCD)//PERIOD)
        result['inputs'].append(row)
        record('input', **row)

    def advance(current, target):
        while current < target:
            amount = min(PERIOD, target-current)
            reply = client.run_dots(amount)
            assert reply == dict(dot=current+amount, executed=amount, reason=abi.WIRE_RUN_DOTS_COUNT), 'FRAME_RUN_DOTS'
            current += amount
        return current

    def capture(name, k, dot):
        frame = k+1
        before = public()
        assert before['dot'] == dot, 'FRAME_CAPTURE_DOT'
        meta, packed = client.snapshot()
        assert meta['epoch'] == epoch and meta['seq'] == frame, 'FRAME_IDENTITY'
        row = LCD+frame*PERIOD+143*456
        assert row <= meta['dot'] < row+456, 'FRAME_COMPLETION'
        assert meta['size'] == 5760, 'FRAME_SIZE'
        pixels = unpack(packed)
        wanted = image(states[k])
        mismatch = next((i for i in range(PIXELS) if pixels[i] != wanted[i]), None)
        path = root/(name+'.2bpp')
        path.write_bytes(packed)
        assert mismatch is None, f'FRAME_PIXELS {name} pixel={mismatch}'
        assert public() == before, 'FRAME_CAPTURE_HOLD'
        entry = dict(name=name, game=k, frame=frame, pause_dot=dot, metadata=meta,
                     state=EXPECTED[name], history=history(k), checked_pixels=PIXELS,
                     crc32=f'{zlib.crc32(pixels):08x}', file=path.name, sha256=file_hash(path),
                     retired=before['retired'])
        result['captures'].append(entry)
        record('capture', **entry)

    try:
        within_cap('load')
        armed = True
        result['load'] = client.load(rom)  # every byte uploaded and read back
        epoch += 2
        result['epoch'] = epoch
        buttons(0, 0)
        assert public()['dot'] == 0, 'FRAME_LOAD_DOT'
        due = {k+2: name for name, k in captures}
        dot = 0
        for n in range(1, last+1):
            within_cap(f'C({n})')
            dot = advance(dot, checkpoint(n))
            if n in due:
                capture(due[n], n-2, dot)
            if FIRST_VBLANK <= n < len(masks) and masks[n] != mask:
                buttons(masks[n], dot)
        if mask:
            # The short plan stops mid-route; release at its final checkpoint.
            buttons(0, dot)
        final = public()
        assert final['dot'] == dot and not client.uncertain, 'FRAME_FINAL_STATE'
        result.update(final=final, final_dot=dot, checkpoints=last, status='PASS')
    except BaseException as error:
        result.update(status='FAIL', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        try:
            if armed and not client.uncertain:
                client.control('HALT')
                reply = client.control('INPUT', 0)
                mask = 0
                result['cleanup'] = dict(input_dot=reply['dot'], public=public())
            elif armed:
                raise RuntimeError('FRAME_UNCERTAIN_CLEANUP')
        except BaseException as error:
            result.update(status='FAIL', cleanup_error=f'{type(error).__name__}: {error}')
            raise
        finally:
            result['uncertain'] = client.uncertain
            result['next_sequence'] = client.sequence
            atomic_json(root/'result.json', result)
    return result


def worker(args):
    from n2m.host.client import Client
    from n2m.host.transport import session
    from ci.storage import machine_lock
    import subprocess
    out = Path(args.out)
    folder = ROOT/'workdir/builds'/args.tag/'host'/f'frames-{args.plan}'/out.name
    folder.mkdir(parents=True)
    ns = SimpleNamespace(uart_port=args.uart_port, uart_vid=None, uart_pid=None, uart_identity=None,
                         endpoint_restarted=False, tag=args.tag, json=True)
    common = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute',
                                      '--git-common-dir'], text=True).strip()
    state_root = Path(common).parent/'workdir/host-sessions'
    transactions = folder/'transactions.jsonl'

    def record(entry):
        with transactions.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), **entry}, sort_keys=True)+'\n')

    rom = Path(args.rom).read_bytes()
    session_record = dict(status='FAIL', plan=args.plan, args=vars(args), host_folder=folder.as_posix())
    started = time.monotonic()
    client = None
    try:
        with machine_lock(MACHINE_MUTEX), session(folder, ns, state_root) as (transport, sequence, persist, _):
            client = Client(transport, sequence=sequence, record=record, persist=persist)
            session_record['endpoint'] = client.identify()
            if session_record['endpoint']['build_id'] != args.expected_build_id.lower():
                raise ValueError('wire build mismatch: '+session_record['endpoint']['build_id'])
            names = ('STATE', 'IMAGE_VALID', 'PROFILE', 'INPUT', 'INPUT_SOURCE', 'INPUT_EFFECTIVE')
            before = {n: client.read_host(getattr(abi, 'HOST_REG_'+n)) for n in names}
            session_record['preflight'] = before
            if before != dict(STATE=abi.STATE_PAUSED, IMAGE_VALID=1, PROFILE=abi.PROFILE_DIRECT_ID,
                              INPUT=0, INPUT_SOURCE=abi.INPUT_SOURCE_UART, INPUT_EFFECTIVE=0):
                raise ValueError('preflight requires a paused valid image with neutral UART input')
            # The paused board's current snapshot binds the reset epoch the
            # load advances from; nothing about its image is assumed.
            meta, _ = client.snapshot()
            session_record['prior_epoch'] = meta['epoch']
            deadline = started+args.deadline if args.deadline else None
            result = run(client, rom, out/'run', epoch=meta['epoch'], plan=args.plan,
                         rom_sha256=args.rom_sha256, deadline=deadline)
            session_record['status'] = result['status']
    except Exception as error:
        session_record['error'] = repr(error)
        print('ERROR', repr(error), flush=True)
    session_record['uncertain'] = None if client is None else client.uncertain
    session_record['next_sequence'] = None if client is None else client.sequence
    session_record['wall_seconds'] = round(time.monotonic()-started, 3)
    atomic_json(out/'session.json', session_record)
    print('RESULT', session_record['status'], 'uncertain=', session_record['uncertain'],
          'wall=', session_record['wall_seconds'], out.as_posix(), flush=True)
    return 0 if session_record['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', choices=tuple(PLANS))
    parser.add_argument('--uart-port', required=True)
    parser.add_argument('--expected-build-id', required=True, help='reviewed wire build ID, 32 hex digits')
    parser.add_argument('--tag', default='frames384')
    parser.add_argument('--cap', type=int, help='whole-process seconds; default 300')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--rom', help=argparse.SUPPRESS)
    parser.add_argument('--rom-sha256', help=argparse.SUPPRESS)
    parser.add_argument('--out', help=argparse.SUPPRESS)
    parser.add_argument('--deadline', type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    cap = args.cap or CAPS[args.plan]
    out = ROOT/'workdir/builds'/args.tag/'frames'/f'{args.plan}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}'
    out.mkdir(parents=True)
    rom, digest, package = build_rom(args.tag)
    assert hashlib.sha256(rom.read_bytes()).hexdigest() == digest, 'FRAME_BUILD_HASH'
    atomic_json(out/'build.json', dict(package=package, rom=rom.as_posix(), sha256=digest))
    print('ROM', rom.as_posix(), digest, flush=True)
    # The worker refuses further checkpoints 24 s before the cap so cleanup
    # HALT/INPUT 0 runs before the 12 s tree kill; the cap is the whole limit.
    command = [sys.executable, str(Path(__file__).resolve()), args.plan, '--worker',
               '--uart-port', args.uart_port, '--expected-build-id', args.expected_build_id,
               '--tag', args.tag, '--rom', str(rom), '--rom-sha256', digest, '--out', str(out),
               '--deadline', str(cap-24)]
    code = supervise(command, cap, out)
    decode(out)
    print('DONE', 'PASS' if code == 0 else 'FAIL', out.as_posix(), flush=True)
    return code


if __name__ == '__main__':
    sys.exit(main())
