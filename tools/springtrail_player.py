"""Observe Springtrail on the board as state, or play it autonomously over UART.

`observe` takes one coherent paused observation, writes the structured state and
the reconstructed image, and can take the aligned actual frame beside it.
`play` runs the autonomous feedback loop from the title to WON within its
declared budget. `compare` plays and, at each of the five named checkpoints,
captures the aligned actual frame and compares all 23040 shades against the
reconstruction, reporting the measured cost of both paths. All three use the
existing Client, package validator, durable session and serialized machine
access; none writes game memory.

    python tools/springtrail_player.py observe --tag <tag> --package <result.json>
    python tools/springtrail_player.py play    --tag <tag> --package <result.json>
    python tools/springtrail_player.py compare --tag <tag> --package <result.json>

Physical execution needs the repository's hardware authorization and verified
setup. Every timing figure a run reports is whatever that run measured; the
host fixtures measure a fake endpoint and are not board latency. The decode,
reconstruction and strategy are covered without hardware by
`src/dv/springtrail/test_state_reader.py` and `test_state_play.py`.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from n2m import generated_interfaces as abi  # noqa: E402
from n2m import springtrail_play as player  # noqa: E402
from n2m import springtrail_state as reader  # noqa: E402
from n2m.host.client import Client  # noqa: E402
from n2m.host.transport import session  # noqa: E402
from n2m.records import atomic_json, file_hash  # noqa: E402
from n2m.test_budget import supervise  # noqa: E402

MACHINE_MUTEX = 1357311510
# Requests and bytes the actual-pixel path costs, from the generated ABI: one
# SNAPSHOT plus the READ_FRAME chunks its size needs.
FRAME_REQUESTS = 1 + -(-abi.FRAME_BYTES // abi.WIRE_MAX_PAYLOAD)


def _png(pixels, path):
    """A viewable copy of a frame, using the existing decoder."""
    sys.path.insert(0, str(ROOT / 'src/dv/libbet'))
    try:
        import frame_png
    finally:
        sys.path.pop(0)
    frame_png.write_frame(pixels, path)


def _unpack(packed):
    sys.path.insert(0, str(ROOT / 'src/dv/libbet'))
    try:
        import frame_png
    finally:
        sys.path.pop(0)
    return frame_png.unpack(packed)


def retain(out, index, observation, provenance, *, images=True, clock=time.perf_counter):
    """One observation on disk: structured state, provenance and its image."""
    started = clock()
    record, pixels = reader.reconstruction(observation, provenance)
    render_seconds = clock() - started
    record['timings'] = dict(provenance.get('timings', {}), render_seconds=render_seconds)
    # Total image availability: the boundary, the reads, the decode and the
    # render that together turn a paused core into a reconstructed frame.
    record['timings']['image_seconds'] = (record['timings'].get('state_seconds', 0.0)
                                          + render_seconds)
    atomic_json(out / f'observation-{index:04d}.json',
                {'observation': observation, 'image': record})
    if images:
        _png(pixels, out / f'observation-{index:04d}.png')
    return record, pixels


def compare_frame(observation, packed, *, clock=time.perf_counter):
    """All 23040 shades of the reconstruction against one actual frame."""
    started = clock()
    expected = reader.render(observation)
    render_seconds = clock() - started
    started = clock()
    actual = _unpack(packed)
    differing = sum(1 for a, b in zip(expected, actual) if a != b)
    compare_seconds = clock() - started
    first = next((index for index, (a, b) in enumerate(zip(expected, actual)) if a != b), None)
    return {'shades': len(expected), 'differing': differing, 'match': differing == 0,
            'first_difference': None if first is None else {'x': first % 160, 'y': first // 160},
            'render_seconds': render_seconds, 'compare_seconds': compare_seconds}, expected, actual


def run(client, image, binding, out, *, mode, budget=None, images=True, snapshot=False,
        image_stride=60, clock=time.perf_counter):
    """One tagged operation against an already opened Client."""
    out.mkdir(parents=True, exist_ok=True)
    result = {'status': 'FAIL', 'mode': mode, 'binding': binding.identity(),
              'frame_path': {'bytes': abi.FRAME_BYTES, 'requests': FRAME_REQUESTS}}
    if mode == 'observe':
        result['identity'] = client.identify()
        if snapshot:
            pair, packed = player.aligned_pair(client, binding)
            observation, provenance = pair['observation'], pair['provenance']
            result['snapshot'] = {'metadata': pair['metadata'],
                                  'represents': 'this observation',
                                  'taken_at_dot': pair['next_provenance']['dot'],
                                  'alignment': 'observed at one boundary, frame taken at the next'}
            (out / 'snapshot.2bpp').write_bytes(packed)
            comparison, _expected, actual = compare_frame(observation, packed)
            result['comparison'] = comparison
            _png(actual, out / 'snapshot.png')
        else:
            observation, provenance = player.observe(client, binding)
        record, _pixels = retain(out, 0, observation, provenance, images=images)
        result['image'] = record
        result['observation'] = observation
        result['provenance'] = provenance
        result['status'] = 'PASS'
        return result

    kept = []
    comparisons = []
    checkpoints = player.Checkpoints()

    def keep(index, observation, provenance):
        # Every observation is retained as structured state; images are kept at
        # a declared stride so a long run does not write hundreds of frames.
        picture = images and index % image_stride == 0
        kept.append(retain(out, index, observation, provenance, images=picture)[0])

    def capture(connection, previous, previous_provenance, current, current_provenance):
        """At this boundary the completed frame is the one drawn from `previous`."""
        name = checkpoints.classify(previous)
        if name is None:
            return
        started = clock()
        metadata, packed = connection.snapshot()
        snapshot_seconds = clock() - started
        comparison, _expected, actual = compare_frame(previous, packed)
        index = len(comparisons)
        (out / f'checkpoint-{index}-{name}.2bpp').write_bytes(packed)
        _png(actual, out / f'checkpoint-{index}-{name}-actual.png')
        _png(reader.render(previous), out / f'checkpoint-{index}-{name}-reconstructed.png')
        comparisons.append({
            'checkpoint': name, 'dot': previous_provenance['dot'],
            'snapshot_dot': current_provenance['dot'], 'metadata': metadata,
            'state_path': {'bytes': previous_provenance['bytes'],
                           'requests': previous_provenance['requests'],
                           'timings': previous_provenance['timings']},
            'frame_path': {'bytes': abi.FRAME_BYTES, 'requests': FRAME_REQUESTS,
                           'snapshot_seconds': snapshot_seconds},
            **comparison})

    outcome = player.play(client, image, binding, budget=budget, retain=keep,
                          capture=capture if mode == 'compare' else None)
    result.update(outcome)
    result['observations_retained'] = len(kept)
    result['image_stride'] = image_stride
    atomic_json(out / 'actions.json', outcome['actions'])
    if mode == 'compare':
        result['comparisons'] = comparisons
        result['checkpoints_missing'] = checkpoints.missing()
        result['checkpoints_matched'] = [row['checkpoint'] for row in comparisons if row['match']]
        atomic_json(out / 'comparisons.json', comparisons)
        if result['status'] == 'PASS' and (checkpoints.missing()
                                           or any(not row['match'] for row in comparisons)):
            # A disagreement or a checkpoint the run never reached is a finding.
            result['status'] = 'FAIL'
            result.setdefault('reason', 'STATE_COMPARISON')
    result['measurements'] = summarize(result)
    atomic_json(out / 'measurements.json', result['measurements'])
    return result


def summarize(result):
    """Median and range of each measured figure, with its sample count."""
    def stats(values):
        ordered = sorted(values)
        if not ordered:
            return None
        middle = len(ordered) // 2
        median = (ordered[middle] if len(ordered) % 2
                  else (ordered[middle - 1] + ordered[middle]) / 2)
        return {'samples': len(ordered), 'median': round(median, 6),
                'min': round(ordered[0], 6), 'max': round(ordered[-1], 6)}

    actions = result.get('actions') or []
    rows = {
        'boundary_seconds': [a['state_seconds'] for a in actions],
        'loop_seconds': [a['loop_seconds'] for a in actions],
        'decide_seconds': [a['decide_seconds'] for a in actions],
    }
    comparisons = result.get('comparisons') or []
    if comparisons:
        rows['snapshot_seconds'] = [row['frame_path']['snapshot_seconds'] for row in comparisons]
        rows['render_seconds'] = [row['render_seconds'] for row in comparisons]
        rows['compare_seconds'] = [row['compare_seconds'] for row in comparisons]
        rows['state_read_seconds'] = [row['state_path']['timings']['read_seconds']
                                      for row in comparisons]
        rows['state_decode_seconds'] = [row['state_path']['timings']['decode_seconds']
                                        for row in comparisons]
    return {'note': 'measured by this run on this endpoint; not a contract',
            **{name: stats(values) for name, values in rows.items() if values}}


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
    parser.add_argument('mode', choices=('observe', 'play', 'compare'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--package', required=True,
                        help='immutable sw/build/springtrail/runs/<attempt>/result.json')
    for option in ('uart-port', 'uart-vid', 'uart-pid', 'uart-identity'):
        parser.add_argument('--' + option)
    parser.add_argument('--endpoint-restarted', action='store_true')
    parser.add_argument('--snapshot', action='store_true',
                        help='observe: also take the aligned actual frame and compare it')
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
