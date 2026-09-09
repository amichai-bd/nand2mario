"""Run the fixed Stackdrop comparison on an explicitly verified UART setup."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/dv/stackdrop'))
from screen import decode
sys.path.pop(0)
from ci.storage import machine_lock
from n2m.host.client import Client
from n2m.host.package import read_package
from n2m.host.transport import session
from n2m.records import atomic_json, file_hash
from n2m.stackdrop_session import play
from n2m.test_budget import supervise

ROM = 'af11fbfae2ddf1607ca3c70f32d47eadb62fd5a1c5b5c3f3ead8ea6f2afa0c74'


def finish(client, result, path):
    """Never issue recovery commands after uncertain completion."""
    try:
        if not client.uncertain:
            client.control('HALT')
            client.control('INPUT', 0)
    except Exception:
        result['status'] = 'FAIL'
        raise
    finally:
        result['uncertain'] = client.uncertain
        result['sequence'] = client.sequence
        atomic_json(path, result)


def worker(args):
    folder = ROOT/'workdir/builds'/args.tag/'player'
    folder.mkdir(parents=True, exist_ok=False)
    setup = json.loads(Path(args.setup).read_text())
    state_path = Path(args.state)
    state = json.loads(state_path.read_text())
    expected = [] if args.mode == 'baseline' else ['baseline']
    if state['completed'] != expected or state.get('attempted'):
        raise ValueError('STACKDROP_COMPARISON_ORDER')
    image, package = read_package(ROOT, args.package)
    if package['rom_sha256'] != ROM:
        raise ValueError('STACKDROP_PACKAGE')
    fit_path = Path(setup['fit_record'])
    if file_hash(fit_path) != setup['fit_sha256']:
        raise ValueError('STACKDROP_FIT_RECORD')
    fit = json.loads(fit_path.read_text())
    if fit['status'] != 'PASS' or file_hash(Path(setup['sof'])) != setup['sof_sha256']:
        raise ValueError('STACKDROP_FIT')
    changed = [p for p, h in fit['inputs'].items() if file_hash(ROOT/p) != h]
    if changed != setup['qualified_changed_inputs']:
        raise ValueError('STACKDROP_FIT_INPUTS')
    selection = SimpleNamespace(uart_port=setup['port'], uart_vid=None,
                               uart_pid=None, uart_identity=None,
                               endpoint_restarted=False)
    result = dict(status='FAIL', mode=args.mode, package=package,
                  source=subprocess_head(), fit_reuse_changed_inputs=changed,
                  setup_sha256=file_hash(Path(args.setup)),
                  prior_state_sha256=file_hash(state_path))
    with machine_lock(1357311510), (folder/'packets.jsonl').open('w') as packets, (folder/'observations.jsonl').open('w') as observations:
        def record(entry):
            packets.write(json.dumps(entry)+'\n')
            packets.flush()

        def retain(kind, value):
            observations.write(json.dumps(dict(kind=kind, **value))+'\n')
            observations.flush()

        with session(folder, selection, setup['session_root']) as (transport, sequence, persist, selected):
            if hashlib.sha256(selected['PNPDeviceID'].casefold().encode()).hexdigest() != setup['device_key']:
                raise ValueError('STACKDROP_DEVICE')
            state['attempted'] = args.mode
            atomic_json(state_path, state)
            client = Client(transport, sequence=sequence, record=record, persist=persist)
            try:
                outcome = play(client, image, state['current'], args.mode, decode, retain)
                result.update(outcome, status='PASS')
            finally:
                finish(client, result, folder/'result.json')
            state['current'] = {k: result[k] for k in ('frame','halt_dot','build_id','sequence')}
            state['completed'].append(args.mode)
            state['scores'][args.mode] = result['score']
            state['attempted'] = None
            if args.mode == 'strategy':
                state['improved'] = state['scores']['strategy'] > state['scores']['baseline']
            atomic_json(state_path, state)
            if args.mode == 'strategy' and not state['improved']:
                raise ValueError('STACKDROP_NO_IMPROVEMENT')
    print(json.dumps(result))


def subprocess_head():
    import subprocess
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('baseline','strategy'))
    parser.add_argument('--tag', required=True)
    parser.add_argument('--setup', required=True)
    parser.add_argument('--state', required=True)
    parser.add_argument('--package', required=True)
    parser.add_argument('--worker', action='store_true')
    arguments = parser.parse_args()
    if not arguments.tag.isalnum():
        parser.error('tag must be alphanumeric')
    if arguments.worker:
        worker(arguments)
    else:
        code, output = supervise([sys.executable, str(Path(__file__)), *sys.argv[1:], '--worker'], ROOT, arguments.tag)
        print(output, end='')
        raise SystemExit(code)
