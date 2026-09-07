"""Compare the two declared continuous Client modes and their measured intervals."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
from pathlib import Path


REAL = 'python-integration-uart'
PRELOADED = 'python-integration-client-preloaded'
REAL_MODULE = 'src/dv/python/integration/test_real_uart.py'
PRELOAD_MODULE = 'src/dv/python/integration/test_client_preloaded.py'


def artifact(root, record, filename):
    matches = [name for name in record['artifacts'] if Path(name).name == filename]
    if len(matches) != 1:
        raise ValueError(f'expected exactly one {filename}')
    name = matches[0]
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError('artifact outside recorded workspace')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != record['artifacts'][name]:
        raise ValueError(f'artifact changed: {filename}')
    return data


def identity(normal, preloaded):
    if any(record['status'] != 'PASS' for record in (normal, preloaded)):
        raise ValueError('comparison requires two accepted runs')
    left, right = normal['options'], preloaded['options']
    if (left.get('target'), right.get('target')) != (REAL, PRELOADED):
        raise ValueError('comparison requires real-UART then preloaded modes')
    a, b = left['definition'], right['definition']
    if (a.get('preload') is not None or b.get('preload') != 'integration' or
            a['args'] != ['-gPRELOADED=0'] or b['args'] != ['-gPRELOADED=1'] or
            a['top'] != 'tb_python_integration' or a['expected_exit'] != 'zero' or
            a['python']['module'] != 'test_real_uart' or
            a['python']['test'] != 'real_uart_contract' or
            b['python']['module'] != 'test_client_preloaded' or
            b['python']['test'] != 'client_preloaded_contract'):
        raise ValueError('comparison mode definition differs')
    canonical = copy.deepcopy(b)
    canonical.pop('preload')
    canonical['args'] = ['-gPRELOADED=0']
    canonical['python']['module'] = 'test_real_uart'
    canonical['python']['test'] = 'real_uart_contract'
    inputs = canonical['python']['inputs']
    if inputs.count(PRELOAD_MODULE) != 1 or REAL_MODULE in inputs:
        raise ValueError('comparison test entry inputs differ')
    inputs[inputs.index(PRELOAD_MODULE)] = REAL_MODULE
    if canonical != a:
        raise ValueError('comparison runtime definitions differ')
    for record in (normal, preloaded):
        declared = set(record['options']['definition']['sources'])
        declared.update(record['options']['definition']['python']['inputs'])
        if not declared <= set(record['inputs']):
            raise ValueError('comparison missing declared inputs')
    normal_inputs, preload_inputs = dict(normal['inputs']), dict(preloaded['inputs'])
    if REAL_MODULE not in normal_inputs or PRELOAD_MODULE not in preload_inputs:
        raise ValueError('comparison missing mode entry input')
    normal_inputs.pop(REAL_MODULE)
    preload_inputs.pop(PRELOAD_MODULE)
    if normal_inputs != preload_inputs:
        raise ValueError('comparison source input sets or hashes differ')
    if (normal['seed'] != preloaded['seed'] or normal['tools'] != preloaded['tools'] or
            left.get('vendor_model') != right.get('vendor_model') or
            left.get('python_runtime') != right.get('python_runtime')):
        raise ValueError('comparison seed, model or runtime differs')


def timings(record, client):
    stamps = client['checkpoints_utc']
    names = ('test_entry', 'loader_start', 'loaded', 'run', 'paused')
    values = [datetime.fromisoformat(record['started'])]
    values += [datetime.fromisoformat(stamps[name]) for name in names]
    values.append(datetime.fromisoformat(record['finished']))
    if any(value.tzinfo is None for value in values) or any(a > b for a, b in zip(values, values[1:])):
        raise ValueError('invalid or unordered timing checkpoints')
    started, entry, loader, loaded, run, paused, finished = values
    return {'stage_to_loaded_seconds': (loaded-started).total_seconds(),
            'loader_commands_seconds': (loaded-loader).total_seconds(),
            'loaded_to_paused_seconds': (paused-loaded).total_seconds(),
            'run_to_paused_seconds': (paused-run).total_seconds(),
            'stage_total_seconds': (finished-started).total_seconds()}


def compare(root, normal_path, preload_path):
    records = [json.loads(path.read_text(encoding='utf-8')) for path in (normal_path, preload_path)]
    identity(*records)
    filenames = ('program.gb', 'initial-state.json', 'retirement.csv', 'bus.csv', 'pixels.csv', 'client.json')
    contents = [{name: artifact(root, record, name) for name in filenames} for record in records]
    equal = {}
    for name in ('program.gb', 'retirement.csv', 'bus.csv', 'pixels.csv'):
        left, right = (item[name] for item in contents)
        if left != right:
            rows = list(zip(left.splitlines(), right.splitlines()))
            index = next((i for i, (a, b) in enumerate(rows) if a != b), len(rows))
            raise ValueError(f'ordered comparison differs: {name} row {index+1}')
        if name != 'program.gb':
            expected = {'retirement.csv': 69, 'bus.csv': 145, 'pixels.csv': 46080}[name]
            if len(left.splitlines()) != expected + 1:
                raise ValueError(f'incomplete observations: {name}')
        elif len(left) != 32768:
            raise ValueError('incomplete software image')
        equal[name] = hashlib.sha256(left).hexdigest()
    initial = [json.loads(item['initial-state.json']) for item in contents]
    expected_public = {'STATE': 0, 'IMAGE_VALID': 1, 'PROFILE': 1, 'DOT_LO': 0,
                       'DOT_HI': 0, 'RETIRE_LO': 0, 'RETIRE_HI': 0, 'INPUT': 0,
                       'INPUT_SOURCE': 0, 'INPUT_EFFECTIVE': 0, 'SNAPSHOT_VALID': 0}
    expected_boundary = {'reset_sys': 0, 'core_reset': 0, 'paused': 1, 'fault': 0,
                         'records': 0, 'bus': 0, 'pixels': 0}
    for state in initial:
        if (state['epoch'] != 2 or state['public'] != expected_public or
                state['boundary'] != expected_boundary or
                state['image_sha256'] != equal['program.gb']):
            raise ValueError('invalid initial loaded-and-paused state')
    if initial[0] != initial[1]:
        raise ValueError('initial states differ')
    clients = [json.loads(item['client.json']) for item in contents]
    if any(client['final_dot'] < 136280 or client['final_state'] != 0 for client in clients):
        raise ValueError('execution did not finish paused after checkpoint')
    return {'status': 'PASS', 'normal_record': str(normal_path), 'preloaded_record': str(preload_path),
            'comparator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'equal_artifacts': equal, 'initial_state': initial[0],
            'normal_timings': timings(records[0], clients[0]),
            'preloaded_timings': timings(records[1], clients[1]),
            'limits': 'Stage timing includes preparation, compile and model startup; excludes prior discovery/hashing and environment installation. Transport histories differ; no exact finite-Tcl failure cause is inferred.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--normal', type=Path, required=True)
    parser.add_argument('--preloaded', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.root, args.normal, args.preloaded), indent=2))


if __name__ == '__main__':
    main()
