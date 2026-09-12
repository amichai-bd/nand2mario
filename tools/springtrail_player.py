"""Observe Springtrail on the board as state, or play it autonomously over UART.

`observe` takes one coherent paused observation and writes the structured state
and the reconstructed image beside it. `play` runs the autonomous feedback loop
from the title to WON within its declared budget. Both use the existing Client,
package validator, durable session and serialized machine access; neither
writes game memory.

    python tools/springtrail_player.py observe --tag <tag> --package <result.json>
    python tools/springtrail_player.py play    --tag <tag> --package <result.json>

Physical execution needs the repository's hardware authorization and verified
setup. The decode, reconstruction and strategy are covered without hardware by
`src/dv/springtrail/test_state_reader.py` and `test_state_play.py`.
"""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from n2m import springtrail_play as player  # noqa: E402
from n2m import springtrail_state as reader  # noqa: E402
from n2m.host.client import Client  # noqa: E402
from n2m.host.transport import session  # noqa: E402
from n2m.records import atomic_json, file_hash  # noqa: E402
from n2m.test_budget import supervise  # noqa: E402

MACHINE_MUTEX = 1357311510


def write_image(pixels, path):
    """A viewable copy of a reconstructed frame, using the existing decoder."""
    sys.path.insert(0, str(ROOT / 'src/dv/libbet'))
    try:
        import frame_png
    finally:
        sys.path.pop(0)
    frame_png.write_frame(pixels, path)


def retain(out, index, observation, provenance, *, images=True):
    """One observation on disk: structured state, provenance and its image."""
    record, pixels = reader.reconstruction(observation, provenance)
    atomic_json(out / f'observation-{index:04d}.json',
                {'observation': observation, 'image': record})
    if images:
        write_image(pixels, out / f'observation-{index:04d}.png')
    return record


def run(client, image, binding, out, *, mode, budget=None, images=True, snapshot=False,
        image_stride=60):
    """One tagged operation against an already opened Client."""
    out.mkdir(parents=True, exist_ok=True)
    result = {'status': 'FAIL', 'mode': mode, 'binding': binding.identity()}
    if mode == 'observe':
        result['identity'] = client.identify()
        observation, provenance = player.observe(client, binding)
        result['image'] = retain(out, 0, observation, provenance, images=images)
        result['observation'] = observation
        result['provenance'] = provenance
        if snapshot:
            # An actual PPU frame for comparison. It shows the state observed
            # one boundary earlier, never this observation; see the SPEC.
            metadata, packed = client.snapshot()
            (out / 'snapshot.2bpp').write_bytes(packed)
            result['snapshot'] = {'metadata': metadata, 'represents': 'previous-boundary'}
        result['status'] = 'PASS'
        return result
    kept = []

    def keep(index, observation, provenance):
        # Every observation is retained as structured state; images are kept at
        # a declared stride so a long run does not write hundreds of frames.
        picture = images and index % image_stride == 0
        kept.append(retain(out, index, observation, provenance, images=picture))

    outcome = player.play(client, image, binding, budget=budget, retain=keep)
    result.update(outcome)
    result['observations_retained'] = len(kept)
    result['image_stride'] = image_stride
    atomic_json(out / 'actions.json', outcome['actions'])
    return result


def worker(args):
    out = ROOT / 'workdir/builds' / args.tag / 'springtrail-player' / args.mode
    out.mkdir(parents=True, exist_ok=False)
    image, binding = reader.bind_package(ROOT, args.package)
    selection = SimpleNamespace(uart_port=args.uart_port, uart_vid=args.uart_vid,
                                uart_pid=args.uart_pid, uart_identity=args.uart_identity,
                                endpoint_restarted=args.endpoint_restarted)
    from ci.storage import machine_lock
    state_root = ROOT.parent / 'workdir/host-sessions'
    result = {'status': 'FAIL', 'mode': args.mode, 'tag': args.tag}
    with machine_lock(MACHINE_MUTEX), (out / 'packets.jsonl').open('w', encoding='utf-8') as packets:
        def record(entry):
            packets.write(json.dumps(entry, sort_keys=True) + '\n')
            packets.flush()
        with session(out, selection, state_root) as (transport, sequence, persist, selected):
            client = Client(transport, sequence=sequence, record=record, persist=persist)
            try:
                result = run(client, image, binding, out, mode=args.mode,
                             budget={'wall_seconds': args.wall_seconds} if args.wall_seconds else None,
                             snapshot=args.snapshot, image_stride=args.image_stride)
            finally:
                result['device'] = selected['PNPDeviceID'][:8]
                result['uncertain'] = client.uncertain
                result['artifacts'] = {path.relative_to(ROOT).as_posix(): file_hash(path)
                                       for path in sorted(out.iterdir()) if path.is_file()}
                atomic_json(out / 'result.json', result)
    print(json.dumps({key: value for key, value in result.items()
                      if key not in ('observation', 'actions')}))
    return 0 if result['status'] == 'PASS' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('mode', choices=('observe', 'play'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--package', required=True,
                        help='immutable sw/build/springtrail/runs/<attempt>/result.json')
    for option in ('uart-port', 'uart-vid', 'uart-pid', 'uart-identity'):
        parser.add_argument('--' + option)
    parser.add_argument('--endpoint-restarted', action='store_true')
    parser.add_argument('--snapshot', action='store_true',
                        help='also download one actual PPU frame for comparison')
    parser.add_argument('--wall-seconds', type=int,
                        help='declared wall budget for the play loop')
    parser.add_argument('--image-stride', type=int, default=60,
                        help='reconstruct an image every N observations during play')
    parser.add_argument('--cap', type=int, default=300,
                        help='whole-process supervisor ceiling in seconds')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not args.tag.isalnum():
        parser.error('tag must be alphanumeric')
    if args.worker:
        return worker(args)
    command = [sys.executable, str(Path(__file__).resolve()), *(argv or sys.argv[1:]), '--worker']
    code, output = supervise(command, ROOT, args.tag, ceiling=args.cap)
    print(output, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
