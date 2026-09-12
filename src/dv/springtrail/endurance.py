"""UART endurance transport with a legacy gameplay expectation model.

The current build/anchor binding remains enforced, but this static gameplay
oracle predates progression and is not current-image 90-cycle qualification.
Issue511 owns lives/countdown scheduling. Host runner tests qualify protocol,
duration and cleanup paths using synthetic legacy frames, not current FPGA play.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.records import atomic_json, file_hash  # noqa: E402
from n2m import process_tree  # noqa: E402
from interactions_reference import Game, PLAYING, PAUSED, RETRY, update as flow_update  # noqa: E402
from motion_reference import Player, step  # noqa: E402
from motion_frames import image  # noqa: E402
from motion_game_reference import LCD  # noqa: E402
from startup_anchor import derive, symbol_table  # noqa: E402

# LCD is the source-derived startup anchor of the current image, frozen once
# in motion_game_reference and checked against the source listing; `require_anchor`
# refuses a built image that derives any other dot. Not chosen from the DUT.
PERIOD, DOT_HZ = 70224, 4194304
CYCLE_SECONDS = 20
# Even cycles run (Right+B), odd cycles jump then walk (Right+A). Both routes
# end in the first gap, converge for every JOYP first-sample variant and are
# independent of the enemy patrol phase; the host tests prove that.
ROUTES = (33, 17)
ROUTE_HOLD = 5.5
# Longest converging route is 267 updates plus display lag; 280 frame periods
# after the applied dot guarantees the settled RETRY frame.
ROUTE_PERIODS = 280
PAUSE_CYCLES = (0, 30, 60)
PLANS = {'short': 2, 'full': 90}
CAPS = {'short': 300, 'full': 1980}
SPAWN = Game(player=Player())
MACHINE_MUTEX = 1357311510


def update(game, buttons):
    """Current-image game rule: frozen flow over the current motion player."""
    return flow_update(game, buttons, step=step)


def first_samples(route):
    """Masks one VBlank may sample when INPUT changes between JOYP row reads."""
    return sorted({0, route & 0x0f, route & 0xf0, route})


def terminal(route, first=None, enemy=None):
    """Settled RETRY state after holding `route` from spawn, and its length."""
    game = replace(SPAWN, mode=PLAYING)
    if enemy is not None:
        game = replace(game, enemy_x=enemy[0], enemy_vx=enemy[1])
    game = update(game, route if first is None else first)
    count = 1
    while game.mode != RETRY:
        assert count < ROUTE_PERIODS - 8, 'ENDURANCE_ROUTE_LENGTH'
        game = update(game, route)
        count += 1
    return game, count


def exclusion(game):
    """Pixels the patrolling enemy (world x240..303, y120..135) may touch."""
    cam = game.player.camera
    return frozenset(y*160+x for y in range(120, 136)
                     for x in range(max(0, 240-cam), min(160, 304-cam)))


_expected = {}


def expected(sample):
    """(image, checked indices) for a frozen sample identity."""
    if sample not in _expected:
        excluded = frozenset()
        if sample == 'title':
            game = SPAWN
        elif sample == 'play':
            game = replace(SPAWN, mode=PLAYING)
        elif sample == 'paused':
            game = replace(SPAWN, mode=PAUSED)
        else:
            game = terminal(int(sample.removeprefix('retry-')))[0]
            excluded = exclusion(game)
        indices = [i for i in range(23040) if i not in excluded]
        _expected[sample] = (image(game), indices)
    return _expected[sample]


def check_pixels(packed, sample):
    assert len(packed) == 5760, 'ENDURANCE_FRAME_SIZE'
    pixels = bytes((b >> shift) & 3 for b in packed for shift in (0, 2, 4, 6))
    wanted, indices = expected(sample)
    mismatch = next((i for i in indices if pixels[i] != wanted[i]), None)
    assert mismatch is None, f'ENDURANCE_PIXELS sample={sample} pixel={mismatch}'
    return len(indices)


def require_anchor(rom, symbols=None):
    """The built image must derive the frozen anchor; a moved anchor stops here."""
    result = derive(rom, symbols)
    assert result['lcd'] == LCD, f'ENDURANCE_ANCHOR: image derives {result["lcd"]}, frozen {LCD}'
    return result


def require_current_rom(rom, expected_sha256):
    """The loaded bytes must be the build just produced from current sources."""
    actual = hashlib.sha256(rom).hexdigest()
    assert len(rom) == 32768 and actual == expected_sha256, \
        'ENDURANCE_ROM: image differs from the current build'
    return actual


def run(client, rom, root, *, epoch, cycles, rom_sha256, deadline=None,
        clock=time.monotonic, sleep=time.sleep):
    """`cycles` fixed 20 s cycles, then three complete reset/load/start cycles."""
    require_current_rom(rom, rom_sha256)
    assert cycles in PLANS.values(), 'ENDURANCE_PLAN'
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    log = []
    last = None
    mask = 0
    armed = False
    result = dict(status='FAIL', cycles=cycles, planned_seconds=cycles*CYCLE_SECONDS,
                  rom_sha256=rom_sha256, lcd=LCD, routes=ROUTES, pause_cycles=PAUSE_CYCLES,
                  samples=[], lifecycles=[])

    def record(kind, **fields):
        row = dict(kind=kind, wall=clock(), **fields)
        log.append(row)
        atomic_json(root/'journal.json', log)

    def within_cap(where):
        assert deadline is None or clock() < deadline, f'ENDURANCE_WALL_CAP {where}'

    def wide(low, high):
        # Live counters cross 32 bits inside 30 minutes; no torn low/high read.
        for _ in range(3):
            first = client.read_host(high)
            value = client.read_host(low)
            if first == client.read_host(high):
                return (first << 32) | value
        raise AssertionError('ENDURANCE_COUNTER_ROLLOVER')

    def public(running):
        state = dict(dot=wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI),
                     retired=wide(abi.HOST_REG_RETIRE_LO, abi.HOST_REG_RETIRE_HI))
        assert client.read_host(abi.HOST_REG_STATE) == (abi.STATE_RUNNING if running else abi.STATE_PAUSED), 'ENDURANCE_STATE'
        assert client.read_host(abi.HOST_REG_IMAGE_VALID) == 1, 'ENDURANCE_IMAGE'
        assert client.read_host(abi.HOST_REG_INPUT_SOURCE) == abi.INPUT_SOURCE_UART, 'ENDURANCE_SOURCE'
        assert client.read_host(abi.HOST_REG_INPUT) == client.read_host(abi.HOST_REG_INPUT_EFFECTIVE) == mask, 'ENDURANCE_INPUT'
        return state

    def buttons(value):
        nonlocal mask
        before = wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI)
        reply = client.control('INPUT', value)
        after = wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI)
        assert before <= reply['dot'] <= after, 'ENDURANCE_INPUT_DOT'
        mask = value
        record('input', mask=mask, applied_dot=reply['dot'], before=before, after=after)
        return reply['dot']

    def capture(name, sample, running, after=0):
        nonlocal last
        before = public(running)
        meta, packed = client.snapshot()
        frontier = public(running)
        assert meta['epoch'] == epoch, 'ENDURANCE_EPOCH'
        assert meta['size'] == 5760, 'ENDURANCE_FRAME_SIZE'
        row = LCD+meta['seq']*PERIOD+143*456
        assert row <= meta['dot'] < row+456, 'ENDURANCE_FRAME_DOT'
        assert after <= meta['dot'] <= frontier['dot'], 'ENDURANCE_SAMPLE_TIME'
        # A snapshot is the latest complete frame, not proof of every frame.
        assert before['dot']-meta['dot'] < 2*PERIOD, 'ENDURANCE_STALE_SAMPLE'
        if last is not None:
            assert meta['seq'] > last['seq'] and meta['dot'] > last['dot'], 'ENDURANCE_FRAME_PROGRESS'
        count = check_pixels(packed, sample)
        path = root/(name+'.2bpp')
        path.write_bytes(packed)
        row = dict(name=name, sample=sample, metadata=meta, checked_pixels=count,
                   file=path.name, sha256=file_hash(path), before=before, frontier=frontier)
        result['samples'].append(row)
        record('sample', **row)
        last = meta
        return frontier

    def advance(target):
        current = public(False)['dot']
        while current < target:
            amount = min(PERIOD, target-current)
            reply = client.run_dots(amount)
            assert reply == dict(dot=current+amount, executed=amount, reason=abi.WIRE_RUN_DOTS_COUNT), 'ENDURANCE_COUNT'
            current += amount
        assert current == target, 'ENDURANCE_START_DOT'

    def start(name, reset):
        nonlocal epoch, last, mask, armed
        within_cap(name)
        if reset:
            client.control('RESET')
            epoch += 1
        armed = True
        receipt = client.load(rom)  # every byte uploaded and read back
        epoch += 2
        last = None
        buttons(0)
        assert public(False)['dot'] == 0, 'ENDURANCE_LOAD_DOT'
        advance(LCD+2*PERIOD+4096)
        capture(name+'-title', 'title', False)
        buttons(128)
        advance(LCD+3*PERIOD+4096)
        buttons(0)
        advance(LCD+5*PERIOD+4096)
        capture(name+'-play', 'play', False)
        record('lifecycle', name=name, epoch=epoch, receipt=receipt)
        return receipt

    def press_start(name, sample, running=True):
        sleep(.1)
        applied = buttons(128)
        sleep(.15)
        capture(name, sample, running, applied+3*PERIOD)
        buttons(0)

    try:
        result['initial_load'] = start('origin', False)
        first = public(False)
        client.control('RUN')
        began = clock()  # Reply follows RUN; this origin cannot overclaim duration.
        record('continuous_start', dot=first['dot'])
        previous = first
        for index in range(cycles):
            within_cap(f'cycle {index}')
            deadline_cycle = began+(index+1)*CYCLE_SECONDS
            assert clock() < began+index*CYCLE_SECONDS+1, 'ENDURANCE_SCHEDULE_LATE'
            route = ROUTES[index % 2]
            applied = buttons(route)
            sleep(ROUTE_HOLD)
            current = capture(f'{index:03d}-retry', f'retry-{route}', True, applied+ROUTE_PERIODS*PERIOD)
            assert current['dot'] > previous['dot'] and current['retired'] > previous['retired'], 'ENDURANCE_PROGRESS'
            buttons(0)
            press_start(f'{index:03d}-restart', 'play')
            if index in PAUSE_CYCLES:
                press_start(f'{index:03d}-pause', 'paused')
                press_start(f'{index:03d}-resume', 'play')
            assert clock() < deadline_cycle, 'ENDURANCE_CYCLE_BUDGET'
            sleep(max(0, deadline_cycle-clock()))
            previous = current
        # One second absorbs crystal/host clock phase without shortening either
        # the physical duration or the independently checked emulated duration.
        sleep(1)
        final_live = capture('continuous-final', 'play', True)
        elapsed = clock()-began
        assert elapsed >= cycles*CYCLE_SECONDS, 'ENDURANCE_DURATION'
        assert final_live['dot']-first['dot'] >= cycles*CYCLE_SECONDS*DOT_HZ, 'ENDURANCE_DOT_DURATION'
        halted = client.control('HALT')
        record('continuous_end', elapsed=elapsed, halt=halted, frontier=final_live)
        result.update(continuous_seconds=elapsed, continuous_dot_delta=final_live['dot']-first['dot'])
        buttons(0)
        for index in range(3):
            result['lifecycles'].append(start(f'cycle-{index+1}', True))
        assert len(result['lifecycles']) == 3, 'ENDURANCE_LIFECYCLE_COUNT'
        result['status'] = 'PASS'
    except BaseException as error:
        result.update(status='FAIL', error=f'{type(error).__name__}: {error}')
        raise
    finally:
        try:
            if armed and not client.uncertain:
                client.control('HALT')
                buttons(0)
                result['final'] = public(False)
                result['epoch'] = epoch
            elif armed:
                raise RuntimeError('ENDURANCE_UNCERTAIN_CLEANUP')
        except BaseException as error:
            result.update(status='FAIL', cleanup_error=f'{type(error).__name__}: {error}')
            raise
        finally:
            result['uncertain'] = client.uncertain
            result['next_sequence'] = client.sequence
            atomic_json(root/'result.json', result)
    return result


def build_rom(tag):
    """Build the current image and return (path, sha256 from the build's own manifest)."""
    raw = subprocess.check_output([sys.executable, str(ROOT/'tools/build.py'), 'sw', 'build',
                                   'springtrail', '--tag', tag, '--json'], cwd=ROOT, text=True)
    package = json.loads(raw.strip().splitlines()[-1])
    assert package['status'] == 'PASS', 'ENDURANCE_BUILD'
    rom = ROOT/package['rom']
    # Refuse to reach a board with an image whose startup moved the anchor;
    # build.json then records every term of the derivation.
    symbols = symbol_table(json.loads(rom.with_name('symbols.json').read_text(encoding='utf-8')))
    package['anchor'] = require_anchor(rom.read_bytes(), symbols)
    return rom, package['artifacts'][package['rom']], package


def worker(args):
    from n2m.host.client import Client
    from n2m.host.transport import session
    from ci.storage import machine_lock
    out = Path(args.out)
    folder = ROOT/'workdir/builds'/args.tag/'host'/f'endurance-{args.plan}'/out.name
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
            # first load advances from; nothing about its image is assumed.
            meta, _ = client.snapshot()
            session_record['prior_epoch'] = meta['epoch']
            deadline = started+args.deadline if args.deadline else None
            result = run(client, rom, out/'run', epoch=meta['epoch'], cycles=PLANS[args.plan],
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


def decode(out):
    """Row-major PNGs beside every retained packed frame; artifacts only."""
    sys.path.insert(0, str(ROOT/'src/dv/libbet'))
    import frame_png
    for packed in sorted(out.glob('run/*.2bpp')):
        frame_png.write_frame(frame_png.unpack(packed.read_bytes()), packed.with_suffix('.png'), 2)


def supervise(command, cap, out):
    """Whole-process bound: kill the worker tree 12 s before `cap`, record it."""
    started = time.monotonic()
    record = dict(started=datetime.now(timezone.utc).isoformat(), cap_seconds=cap,
                  command=command, status='RUNNING')
    atomic_json(out/'budget.json', record)
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    # An owned process tree (job object or POSIX session group): the kill
    # reaps every descendant at once, including one spawned while cleanup
    # starts, and cleanup is complete only when the job reports none alive.
    with process_tree.Tree(command, cwd=ROOT, **options) as tree:
        process = tree.process
        try:
            process.wait(timeout=cap-12)
            record['status'] = 'FINISHED'
        except subprocess.TimeoutExpired:
            record['status'] = 'TIMEOUT'
            try:
                tree.terminate(timeout=5)
                process.wait(timeout=5)
                record['cleanup_complete'] = True
            except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
                record['cleanup_complete'] = False
                record['cleanup_error'] = str(error)
                try:
                    survivors = tree.survivors()
                except OSError as query_error:
                    survivors = None
                    record['survivors_error'] = str(query_error)
                if survivors:
                    record['survivors'] = survivors
                process.kill()
                process.wait(timeout=2)
    record.update(raw_exit_code=process.returncode, elapsed_seconds=round(time.monotonic()-started, 3),
                  finished=datetime.now(timezone.utc).isoformat())
    atomic_json(out/'budget.json', record)
    return 0 if record['status'] == 'FINISHED' and process.returncode == 0 else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('plan', choices=tuple(PLANS))
    parser.add_argument('--uart-port', required=True)
    parser.add_argument('--expected-build-id', required=True, help='reviewed wire build ID, 32 hex digits')
    parser.add_argument('--tag', default='endurance264')
    parser.add_argument('--cap', type=int, help='whole-process seconds; default 300 short, 1980 full')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--rom', help=argparse.SUPPRESS)
    parser.add_argument('--rom-sha256', help=argparse.SUPPRESS)
    parser.add_argument('--out', help=argparse.SUPPRESS)
    parser.add_argument('--deadline', type=float, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    cap = args.cap or CAPS[args.plan]
    out = ROOT/'workdir/endurance264'/f'{args.plan}-{datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")}'
    out.mkdir(parents=True)
    rom, digest, package = build_rom(args.tag)
    assert hashlib.sha256(rom.read_bytes()).hexdigest() == digest, 'ENDURANCE_BUILD_HASH'
    atomic_json(out/'build.json', dict(package=package, rom=rom.as_posix(), sha256=digest))
    print('ROM', rom.as_posix(), digest, flush=True)
    # The worker fails itself 24 s before the cap so cleanup HALT/INPUT0 runs
    # before the 12 s tree kill; the cap is the whole-process limit.
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
