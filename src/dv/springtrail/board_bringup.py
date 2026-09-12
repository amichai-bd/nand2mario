"""GAP-005 physical proxies: heartbeat, VGA test-card CRC, ping/build-ID, CRC rejection.

Closes wiki/preflight-gaps.md#gap-005-board-wiring-and-safe-bring-up together
with wiki/src/board-bring-up.md. No monitor is attached to this board; the
VGA test-card result is the exact pixel/CRC match of the UART-read framebuffer
against `endurance.expected('title')`'s independent image, the same reference
the continuous milestone (#264) already uses, not an observed picture.

`run` drives one Client under the caller's exclusive lock and open session;
`main` is the committed launcher with its own machine mutex, durable session
and whole-process supervisor. This proves the current build, not a frozen
historical one: `build_rom` builds springtrail from current sources and
`require_current_rom` only requires that exact freshly built image.
"""
import argparse
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
from endurance import LCD, PERIOD, MACHINE_MUTEX, build_rom, check_pixels, require_current_rom  # noqa: E402

WHOLE_PROCESS_BUDGET_SECONDS = 120
TITLE_ADVANCE_DOT = LCD + 2 * PERIOD + 4096


def run(client, rom, rom_sha256, folder, log, expected_build, crc_proof_run):
    require_current_rom(rom, rom_sha256)
    folder = Path(folder)
    result = dict(status='FAIL', rom_sha256=rom_sha256, lcd=LCD)

    def note(kind, **values):
        log(dict(kind=kind, **values))

    def wide(low, high):
        for _ in range(3):
            first = client.read_host(high)
            value = client.read_host(low)
            if first == client.read_host(high):
                return (first << 32) | value
        raise AssertionError('BRINGUP_COUNTER_ROLLOVER')

    completed = False
    try:
        identity = client.identify()
        assert identity['build_id'] == expected_build, 'BRINGUP_BUILD_ID'
        result['identity'] = identity
        assert client.read_host(abi.HOST_REG_STATE) == abi.STATE_PAUSED, 'BRINGUP_INITIAL_STATE'
        loaded = client.load(rom)
        result['load'] = loaded
        # Fresh programming with no RESET sent leaves epoch0; LOAD_BEGIN/END
        # supply the two loader resets that predict epoch2 (PHYSICAL.md).
        epoch = 2
        assert wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI) == 0, 'BRINGUP_LOAD_DOT'
        current = 0
        while current < TITLE_ADVANCE_DOT:
            amount = min(PERIOD, TITLE_ADVANCE_DOT - current)
            reply = client.run_dots(amount)
            assert reply == dict(dot=current + amount, executed=amount, reason=abi.WIRE_RUN_DOTS_COUNT), 'BRINGUP_RUN_DOTS'
            current += amount
        # `current` only counts what the host asked for. The heartbeat is the
        # endpoint's own counter agreeing that it advanced from the zero above.
        counted = wide(abi.HOST_REG_DOT_LO, abi.HOST_REG_DOT_HI)
        assert counted == current > 0, 'BRINGUP_HEARTBEAT'
        note('heartbeat', dot=counted, requested=current)
        result['heartbeat'] = {'dot': counted, 'requested': current}
        meta, packed = client.snapshot()
        assert meta['epoch'] == epoch, 'BRINGUP_EPOCH'
        assert meta['size'] == 5760, 'BRINGUP_FRAME_SIZE'
        # The exact-scanline freshness window endurance.py also checks is not
        # reproduced here. LCD is the source-derived anchor `build_rom` already
        # required this image to derive; the full pixel-for-pixel match below
        # is the actual proof, and a wrong captured frame fails it.
        checked_pixels = check_pixels(packed, 'title')
        pixels = bytes((b >> shift) & 3 for b in packed for shift in (0, 2, 4, 6))
        crc32 = f'{zlib.crc32(pixels):08x}'
        path = folder / 'title.2bpp'
        path.write_bytes(packed)
        row = dict(metadata=meta, checked_pixels=checked_pixels, crc32=crc32, sha256=file_hash(path))
        result['test_card'] = row
        note('test_card', **row)
        client.control('HALT')
        client.control('INPUT', 0)
        assert client.read_host(abi.HOST_REG_STATE) == abi.STATE_PAUSED, 'BRINGUP_FINAL_STATE'
        result['crc_rejection'] = crc_proof_run(client)
        note('crc_rejection', **result['crc_rejection'])
        result['status'] = 'PASS'
        completed = True
        return result
    finally:
        if not completed and not client.uncertain:
            client.control('HALT')
            client.control('INPUT', 0)
        result['uncertain'] = client.uncertain
        atomic_json(folder / 'result.json', result)


def worker(args, clock=time.monotonic):
    from n2m.host.client import Client
    from n2m.host.transport import session
    from n2m.host.crc_proof import run as crc_proof_run
    from ci.storage import machine_lock

    started = clock()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    ns = SimpleNamespace(uart_port=args.uart_port, uart_vid=None, uart_pid=None, uart_identity=None,
                         endpoint_restarted=args.endpoint_restarted, tag=args.tag, json=True)
    import subprocess
    common = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', '--path-format=absolute',
                                      '--git-common-dir'], text=True).strip()
    state_root = Path(common).parent / 'workdir/host-sessions'
    transactions = out / 'transactions.jsonl'

    def record(entry):
        with transactions.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(), **entry}, sort_keys=True) + '\n')

    rom, rom_sha256, package = build_rom(args.tag or 'bringup')
    rom_bytes = rom.read_bytes()
    session_record = dict(status='FAIL', args={k: str(v) for k, v in vars(args).items()}, out=out.as_posix(),
                          rom_build=package)
    try:
        with machine_lock(MACHINE_MUTEX), session(out, ns, state_root) as (transport, sequence, persist, selected):
            client = Client(transport, sequence=sequence, record=record, persist=persist)
            session_record['uart_identity'] = {k: selected.get(k) for k in ('DeviceID', 'Name', 'PNPDeviceID')}
            outcome = run(client, rom_bytes, rom_sha256, out, record, args.expected_build_id.lower(), crc_proof_run)
            session_record.update(status=outcome['status'], result=outcome)
    finally:
        # Retained evidence must carry the measured wall time of a failed run too.
        session_record['wall_seconds'] = clock() - started
        atomic_json(out / 'session.json', session_record)
    return session_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--expected-build-id', required=True, help='32 hex chars, from the programmed fpga build record')
    parser.add_argument('--out', required=True)
    parser.add_argument('--tag')
    parser.add_argument('--uart-port')
    parser.add_argument('--endpoint-restarted', action='store_true')
    args = parser.parse_args(argv)
    result = worker(args)
    assert result['wall_seconds'] <= WHOLE_PROCESS_BUDGET_SECONDS, 'BRINGUP_WALL_BUDGET'
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
