"""Board proof of the composite menu: every frame class read back over SNAPSHOT, pixel-exact.

The board has no physical joypad and a UART round trip is longer than the
one-frame classes last (a staged footer, a scroll ramp step, a splash frame),
so the proof holds the core host-paused and advances it one frame at a time:
`RESET` leaves the core PAUSED, `RUN_DOTS 70224` executes exactly one frame
of dots, `INPUT` sets the joypad the menu samples in the next VBlank, and
`SNAPSHOT` returns the last completed frame. Every capture is compared with
`reference.py` through `board_compare` against the catalogue read from the
board itself. A host `RESET` re-arms the boot splash only while `$A003` is
still `$FF`, which a core reset keeps and only a global reset clears, so the
splash runs first and the refused select and the game select come last.

`run` drives one Client under the caller's exclusive lock and open session;
`main` is the launcher with the machine mutex and the durable UART session,
as `src/dv/springtrail/board_bringup.py`. It proves the programmed build the
caller names, never a frozen one: the build id and the catalogue are read
from the board.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m.records import atomic_json, file_hash  # noqa: E402
from n2m.host import library  # noqa: E402
from n2m.host.client import RejectedCommand  # noqa: E402
import board_compare  # noqa: E402
import reference  # noqa: E402

FRAME_DOTS = 70224
BOOT_FRAMES_MAX = 64
# One frame of alignment slack: the pause point inside a frame decides whether
# a step's completed frame already shows the writes of that step's VBlank.
WAIT_FRAMES = 1
SWAP_STATUS_READS = 64
WHOLE_PROCESS_BUDGET_SECONDS = 900
MACHINE_MUTEX = 1357311510
STEPS = ('splash', 'idle', 'cursor', 'ramp', 'empty', 'refused', 'select', 'return')
TAGLINE_SLOT, EMPTY_SLOT, GAME_SLOT = 2, 11, 2
LAST, OFF = reference.SCROLL_SLOT, reference.SCROLL_SLOT - 1
INVALID = reference.RESULT_INVALID_SLOT


class Proof:
    """The scripted session over one Client; every capture is retained and compared as it is read."""

    def __init__(self, client, folder, log, entries):
        self.client, self.folder, self.log, self.entries = client, Path(folder), log, entries
        self.captures = []
        self.result, self.index = reference.RESULT_NONE, reference.NO_INDEX
        # The sample the last compared frame matched, with the status bytes it
        # was read under, for the one-frame alignment slack.
        self.last = None

    def step(self, frames=1, exact=True):
        for _ in range(frames):
            reply = self.client.run_dots(FRAME_DOTS)
            if exact:
                assert reply['reason'] == abi.WIRE_RUN_DOTS_COUNT and reply['executed'] == FRAME_DOTS, 'MENU_BOARD_STEP'

    def press(self, mask, exact=True):
        """One button edge: held across exactly one VBlank, then released."""
        self.client.control('INPUT', mask)
        self.step(exact=exact)
        self.client.control('INPUT', 0)

    def compare(self, packed, sample, phases=(0, 1), result=None, index=None):
        result = self.result if result is None else result
        index = self.index if index is None else index
        return board_compare.compare(packed, self.entries, board_compare.candidates(sample, phases, result, index))

    def snapshot(self, name, sample, phases=(0, 1), require=True):
        metadata, packed = self.client.snapshot()
        out = self.folder / f'{len(self.captures):02d}-{name}'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'frame.2bpp').write_bytes(packed)
        record = self.compare(packed, sample, phases)
        record.update(name=name, sample=sample, metadata=metadata, sha256=hashlib.sha256(packed).hexdigest(),
                      result=self.result, index=self.index,
                      rendered=board_compare.render(packed, self.entries, record, out))
        (out / 'compare.json').write_text(json.dumps(record, indent=2, sort_keys=True), encoding='utf-8')
        brief = dict(name=name, sample=sample, matches=record['matches'], frame_crc32=record['frame_crc32'],
                     sha256=record['sha256'], epoch=metadata['epoch'], seq=metadata['seq'], dot=metadata['dot'])
        self.captures.append(brief)
        self.log(dict(kind='capture', **brief))
        if require:
            assert record['matches'], f'MENU_BOARD_PIXEL {name} {sample}'
        if record['matches']:
            self.last = (sample, self.result, self.index)
        return record, packed

    def expect(self, name, sample, phases=(0, 1)):
        """Step until the next completed frame is `sample`, allowing one frame of alignment slack.

        The frame before it may repeat once (the step's VBlank had not shown
        the change yet); anything else fails at once with the capture kept.
        """
        for attempt in range(WAIT_FRAMES + 1):
            self.step()
            record, packed = self.snapshot(name, sample, phases, require=False)
            if record['matches']:
                return record
            if attempt < WAIT_FRAMES and self.last is not None:
                still, result, index = self.last
                if self.compare(packed, still, (0, 1), result, index)['matches']:
                    self.log(dict(kind='wait', name=name, still=still))
                    continue
            raise AssertionError(f'MENU_BOARD_PIXEL {name} {sample}')
        raise AssertionError(f'MENU_BOARD_PIXEL {name} {sample}')

    def move(self, mask, slot, before):
        """One cursor move: the staged footer frame, then the settled one."""
        self.press(mask)
        self.expect(f'footer-{slot}-{before}', f'footer-{slot}-{before}')
        self.expect(f'cursor-{slot}', f'cursor-{slot}')

    def library_status(self):
        return library.decode_library_status(self.client.read_host(abi.HOST_REG_LIBRARY_STATUS))

    def endpoint(self):
        return library.read_endpoint(self.client)

    def pause(self):
        if self.client.read_host(abi.HOST_REG_STATE) == abi.STATE_RUNNING:
            self.client.control('HALT')
            self.log(dict(kind='halt'))

    # Steps, in session order.
    def splash(self):
        status = self.library_status()
        assert status['a003'] == reference.NO_INDEX, 'MENU_BOARD_SPLASH_ARMED'
        self.client.control('RESET')
        assert self.client.read_host(abi.HOST_REG_STATE) == abi.STATE_PAUSED, 'MENU_BOARD_RESET_PAUSED'
        boot_frames = 0
        while True:
            self.step()
            boot_frames += 1
            try:
                record, _ = self.snapshot('splash-first', 'splash')
                break
            except RejectedCommand as error:
                assert error.status == abi.STATUS_NO_FRAME and boot_frames < BOOT_FRAMES_MAX, 'MENU_BOARD_BOOT'
        numbers = {int(name.removeprefix('splash-')) for name in record['matches']}
        first = current = min(numbers)
        assert current <= 1, f'MENU_BOARD_SPLASH_START {current}'
        seq = record['metadata']['seq']
        self.log(dict(kind='splash', boot_frames=boot_frames, first=first))
        # Frames inside one fade hold are identical, so the first frame may be
        # 0 or 1; the next step tells which, and every step is one frame. The
        # snapshot observer also publishes the frame that ends at the VBlank
        # in which the menu's first loop iteration runs, one blank frame
        # before displayed frame 0, so one extra leading frame of the first
        # hold is accepted; the fade must then advance.
        lead = 0
        while current < reference.SETTLED_FRAME:
            self.step()
            record, _ = self.snapshot(f'splash-{current + 1}', 'splash')
            numbers = {int(name.removeprefix('splash-')) for name in record['matches']}
            if current + 1 in numbers:
                current += 1
            elif current + 2 in numbers:
                current += 2
            elif numbers == {0, 1} and current == 1 and not lead:
                lead = 1
                self.log(dict(kind='splash-lead', seq=record['metadata']['seq']))
            else:
                raise AssertionError(f'MENU_BOARD_SPLASH_ORDER after {current}: {sorted(numbers)}')
            assert record['metadata']['seq'] == seq + 1, 'MENU_BOARD_SPLASH_SEQ'
            seq = record['metadata']['seq']
        self.last = ('menu', self.result, self.index)
        return dict(boot_frames=boot_frames, first=first, lead=lead, frames=current - first + 1)

    def idle(self):
        """Sixteen frames flip bit 4 of the frame counter, so the phase alternates from wherever it is."""
        record, _ = self.snapshot('idle-first', 'phase')
        phase = int(record['matches'][0].removeprefix('phase-'))
        phases = [phase]
        for _ in range(2):
            phase ^= 1
            self.step(reference.PHASE_HOLD)
            self.snapshot(f'idle-phase-{phase}', f'phase-{phase}')
            phases.append(phase)
        self.last = ('menu', self.result, self.index)
        return dict(phases=phases)

    def cursor(self):
        self.move(abi.BUTTON_DOWN, 1, 0)
        self.move(abi.BUTTON_DOWN, TAGLINE_SLOT, 1)
        return True

    def ramp(self):
        for slot in range(TAGLINE_SLOT + 1, OFF + 1):
            self.move(abi.BUTTON_DOWN, slot, slot - 1)
        self.press(abi.BUTTON_DOWN)
        for step in range(1, reference.SCROLL_FRAMES + 1):
            self.expect(f'scroll-{step}', f'scroll-{step}')
        self.press(abi.BUTTON_UP)
        for step in range(1, reference.SCROLL_FRAMES):
            self.expect(f'back-{step}', f'back-{step}')
        self.expect(f'cursor-{OFF}', f'cursor-{OFF}')
        return True

    def empty(self):
        for slot in range(OFF - 1, EMPTY_SLOT - 1, -1):
            self.move(abi.BUTTON_UP, slot, slot + 1)
        return True

    def refused(self):
        self.press(abi.BUTTON_A)
        self.result, self.index = INVALID, EMPTY_SLOT
        self.expect('refused', f'cursor-{EMPTY_SLOT}')
        status = self.library_status()
        assert status['result'] == 'INVALID_SLOT' and status['a003'] == EMPTY_SLOT, 'MENU_BOARD_REFUSED_STATUS'
        assert 'window_ready' in status['flags'], 'MENU_BOARD_REFUSED_WINDOW'
        self.move(abi.BUTTON_UP, EMPTY_SLOT - 1, EMPTY_SLOT)
        return status

    def select(self, game_frame_sha256=None, settle_seconds=2.0):
        for slot in range(EMPTY_SLOT - 2, GAME_SLOT - 1, -1):
            self.move(abi.BUTTON_UP, slot, slot + 1)
        # The swap resets the core inside this frame, so the step may stop short.
        self.press(abi.BUTTON_A, exact=False)
        for _ in range(SWAP_STATUS_READS):
            status = self.library_status()
            if 'copy_busy' not in status['flags']:
                break
        assert status['result'] == 'OK' and status['a003'] == GAME_SLOT, 'MENU_BOARD_SELECT_STATUS'
        endpoint = self.endpoint()
        assert endpoint['PROFILE'] == abi.PROFILE_DIRECT_ID and endpoint['IMAGE_VALID'], 'MENU_BOARD_SELECT_PROFILE'
        if endpoint['STATE'] == abi.STATE_PAUSED:
            self.client.control('RUN')
        time.sleep(settle_seconds)
        metadata, packed = self.client.snapshot()
        out = self.folder / f'{len(self.captures):02d}-game'
        out.mkdir(parents=True, exist_ok=True)
        (out / 'frame.2bpp').write_bytes(packed)
        digest = hashlib.sha256(packed).hexdigest()
        brief = dict(name='game', sample=None, sha256=digest, epoch=metadata['epoch'], seq=metadata['seq'],
                     dot=metadata['dot'], expected_sha256=game_frame_sha256,
                     matches=['game'] if digest == game_frame_sha256 else [])
        self.captures.append(brief)
        self.log(dict(kind='capture', **brief))
        if game_frame_sha256 is not None:
            assert digest == game_frame_sha256, 'MENU_BOARD_GAME_FRAME'
        return dict(endpoint=endpoint, library_status=status, frame=brief)

    def back(self, settle_seconds=1.0):
        outcome = library.return_to_menu(self.client, wait=True)
        assert outcome['endpoint']['PROFILE'] == abi.PROFILE_LOADER_ID, 'MENU_BOARD_RETURN_PROFILE'
        if outcome['endpoint']['STATE'] == abi.STATE_PAUSED:
            self.client.control('RUN')
        # A select left its index behind, so the returned menu starts settled
        # and running; its phase follows the wall clock, so both are tried.
        self.result, self.index = reference.RESULT_NONE, reference.NO_INDEX
        time.sleep(settle_seconds)
        self.snapshot('menu-after-return', 'phase')
        return outcome


def run(client, folder, log, expected_build, steps=STEPS, packed_catalogue_sha256=None,
        game_frame_sha256=None):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    result = dict(status='FAIL', steps=list(steps))
    proof = None
    try:
        identity = client.identify()
        assert identity['build_id'] == expected_build, 'MENU_BOARD_BUILD_ID'
        result['identity'] = identity
        raw, rows = library.read_catalogue(client)
        (folder / 'catalogue.bin').write_bytes(raw)
        result['catalogue'] = dict(sha256=hashlib.sha256(raw).hexdigest(), rows=rows)
        if packed_catalogue_sha256 is not None:
            assert result['catalogue']['sha256'] == packed_catalogue_sha256, 'MENU_BOARD_CATALOGUE'
        proof = Proof(client, folder, log, library.parse_catalogue(raw))
        result['library_status_before'] = proof.library_status()
        if steps and steps[0] != 'splash':
            proof.pause()
        for step in steps:
            if step == 'select':
                result[step] = proof.select(game_frame_sha256)
            elif step == 'return':
                result[step] = proof.back()
            else:
                result[step] = getattr(proof, step)()
        result['status'] = 'PASS'
        return result
    finally:
        result['captures'] = proof.captures if proof is not None else []
        if result['status'] != 'PASS' and not client.uncertain:
            client.control('INPUT', 0)
        result['uncertain'] = client.uncertain
        atomic_json(folder / 'result.json', result)


def worker(args, clock=time.monotonic):
    from n2m.host.client import Client
    from n2m.host.transport import session, session_root
    from ci.storage import machine_lock

    started = clock()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ns = SimpleNamespace(uart_port=args.uart_port, uart_vid=None, uart_pid=None, uart_identity=None,
                         endpoint_restarted=args.endpoint_restarted, tag=args.tag, json=True)
    transactions = out / 'transactions.jsonl'

    def record(entry):
        with transactions.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), **entry}, sort_keys=True) + '\n')

    session_record = dict(status='FAIL', args={k: str(v) for k, v in vars(args).items()}, out=out.as_posix())
    try:
        with machine_lock(MACHINE_MUTEX), session(out, ns, session_root(ROOT)) as (transport, sequence, persist, selected):
            client = Client(transport, sequence=sequence, record=record, persist=persist)
            session_record['uart_identity'] = {k: selected.get(k) for k in ('DeviceID', 'Name', 'PNPDeviceID')}
            outcome = run(client, out, record, args.expected_build_id.lower(), args.steps.split(','),
                          args.packed_catalogue_sha256, args.game_frame_sha256)
            session_record.update(status=outcome['status'], result=outcome)
    finally:
        session_record['wall_seconds'] = clock() - started
        session_record['artifacts'] = {path.relative_to(out).as_posix(): file_hash(path)
                                       for path in sorted(out.rglob('*')) if path.is_file() and path.name != 'session.json'}
        atomic_json(out / 'session.json', session_record)
    return session_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--expected-build-id', required=True, help='32 hex chars, the programmed fit\'s wire build id')
    parser.add_argument('--out', required=True)
    parser.add_argument('--steps', default=','.join(STEPS), help=f'comma-separated subset of {",".join(STEPS)}, in order')
    parser.add_argument('--packed-catalogue-sha256', help='the fit\'s packed catalogue.bin digest; the board copy must equal it')
    parser.add_argument('--game-frame-sha256', help='the retained V05 frame digest the selected game must show')
    parser.add_argument('--tag')
    parser.add_argument('--uart-port')
    parser.add_argument('--endpoint-restarted', action='store_true')
    args = parser.parse_args(argv)
    unknown = set(args.steps.split(',')) - set(STEPS)
    if unknown:
        parser.error(f'unknown steps: {", ".join(sorted(unknown))}')
    result = worker(args)
    assert result['wall_seconds'] <= WHOLE_PROCESS_BUDGET_SECONDS, 'MENU_BOARD_WALL_BUDGET'
    print(json.dumps({k: v for k, v in result.items() if k != 'artifacts'}, indent=2, sort_keys=True, default=str))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
