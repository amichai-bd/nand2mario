"""Pick a game, load it and play it: the host entry point for playing on this board.

One window and one UART session. The launcher lists every loadable game, loads
the chosen one, resets, runs it, and hands over to the same on-screen pad
`fpga_viewer.py --gui` opens. It reads no frames and serves no HTTP, because the
player watches the board's own VGA output; the window is the control surface.

`fpga_viewer.py` deliberately never loads, resets or programs the board, so the
launcher is its own command rather than another flag on the viewer.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from ci.storage import machine_lock
from n2m.gui_pad import explain_conflict
from n2m.host.client import Client
from n2m.host.transport import session, session_root
from n2m.launcher import launcher_loop
from n2m.records import atomic_json


def play(args):
    """Own one UART session for the whole launcher: menu, load and pad alike."""
    out = ROOT / 'workdir/builds' / args.tag / 'launcher'
    out.mkdir(parents=True, exist_ok=False)
    print(f'Launcher tag {args.tag}; lease {args.seconds}s; results under {out}', flush=True)
    selection = SimpleNamespace(uart_port=args.uart_port, uart_vid=args.uart_vid,
                                uart_pid=args.uart_pid, uart_identity=args.uart_identity,
                                endpoint_restarted=False)
    result = {'status': 'FAIL', 'reason': 'session not opened', 'changes': 0, 'released': False}
    try:
        with machine_lock(1357311510), (out / 'packets.jsonl').open('w', encoding='utf-8') as packets:
            def record(row):
                packets.write(json.dumps(row) + '\n')
                packets.flush()
            with session(out, selection, session_root(ROOT)) as (wire, sequence, persist, _selected):
                client = Client(wire, sequence=sequence, persist=persist, record=record)
                result = launcher_loop(client, ROOT, expected_build=args.expected_build_id,
                                       record=record, seconds=args.seconds)
    except Exception as error:
        # The player needs the actual cause, above all when someone else holds the board.
        result.update(status='FAIL', reason=type(error).__name__, error=str(error))
        explanation = explain_conflict(error)
        if explanation:
            result['conflict'] = explanation
            print(explanation, file=sys.stderr)
        else:
            print(f'{type(error).__name__}: {error}', file=sys.stderr)
    finally:
        atomic_json(out / 'result.json', result)
    print(json.dumps({'status': result['status'], 'loaded': result.get('loaded'),
                      'changes': result.get('changes', 0), 'released': result.get('released', False),
                      'cleanup': result.get('cleanup')}))
    return 0 if result['status'] == 'PASS' and result.get('released') else 1


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--expected-build-id', required=True, help='reviewed 32-hex wire build identity')
    for name in ('uart-port', 'uart-vid', 'uart-pid', 'uart-identity'):
        result.add_argument('--' + name)
    result.add_argument('--tag', help='unique runtime tag; one is generated when omitted')
    result.add_argument('--seconds', type=int, default=900, help='session lease; default 900, at most 3600')
    return result


def parse_args(argv=None, root=ROOT):
    command_parser = parser()
    args = command_parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    build = (args.expected_build_id or '').lower()
    if len(build) != 32 or any(character not in '0123456789abcdef' for character in build):
        command_parser.error('explicit reviewed 32-digit lowercase build ID required')
    args.expected_build_id = build
    if not 1 <= args.seconds <= 3600:
        command_parser.error('seconds 1..3600 required')
    if args.tag is None:
        args.tag = 'launcher' + uuid.uuid4().hex
    if not args.tag.isalnum():
        command_parser.error('tag must be alphanumeric')
    if (Path(root) / 'workdir/builds' / args.tag / 'launcher').exists():
        command_parser.error('runtime tag already exists; omit --tag for a fresh session')
    return args


def main(argv=None):
    return play(parse_args(argv))


if __name__ == '__main__':
    raise SystemExit(main())
