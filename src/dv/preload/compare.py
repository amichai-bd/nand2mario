"""Compare retained real-load and preloaded executions without relabeling them."""
import argparse
import copy
import hashlib
import json
from pathlib import Path


def compare(root, normal_path, preload_path):
    records = [json.loads(path.read_text(encoding='utf-8')) for path in (normal_path, preload_path)]
    if any(record['status'] != 'PASS' for record in records):
        raise ValueError('complete execution equivalence requires two accepted runs')
    normal, preloaded = (record['options'] for record in records)
    real_peer = 'src/dv/integration/peer.py'
    preload_peer = 'src/dv/preload/peer.py'
    if normal.get('target') != 'integration-smoke' or preloaded.get('target') != 'integration-preloaded':
        raise ValueError('comparison requires real-UART then preloaded target modes')
    left, right = normal['definition'], preloaded['definition']
    if (left['driver']['peer'] != real_peer or left['driver'].get('preload', False) or
            right['driver']['peer'] != preload_peer or right['driver'].get('preload') is not True or
            left['args'] != [] or right['args'] != ['-gPRELOADED=1'] or
            left['top'] != 'tb_integration' or left['expected_exit'] != 'zero'):
        raise ValueError('comparison runtime modes or args differ')
    canonical = copy.deepcopy(right)
    canonical['args'] = []
    canonical['driver']['peer'] = real_peer
    canonical['driver'].pop('preload')
    if real_peer not in canonical['driver']['inputs']:
        raise ValueError('preload is missing its shared execution peer input')
    canonical['driver']['inputs'].remove(real_peer)
    if canonical != left or records[0]['seed'] != records[1]['seed']:
        raise ValueError('comparison runtime definitions or seeds differ')
    if any(not set(option['definition']['sources']) <= set(record['inputs'])
           for option, record in zip((normal, preloaded), records)):
        raise ValueError('comparison is missing declared HDL inputs')
    if set(records[1]['inputs']) != set(records[0]['inputs']) | {preload_peer}:
        raise ValueError('comparison relevant input sets differ')
    common = set(records[0]['inputs']) & set(records[1]['inputs'])
    changed = [name for name in sorted(common) if records[0]['inputs'][name] != records[1]['inputs'][name]]
    if changed or records[0]['tools'] != records[1]['tools']:
        raise ValueError(f'comparison source/tool inputs differ: {changed}')
    if records[0].get('options', {}).get('vendor_model') != records[1].get('options', {}).get('vendor_model'):
        raise ValueError('comparison Intel models differ')
    contents = []
    for record in records:
        selected = {}
        for filename in ('program.gb', 'initial-state.csv', 'retirement.csv', 'bus.csv', 'pixels.csv', 'client.json'):
            matches = [name for name in record['artifacts'] if Path(name).name == filename]
            if len(matches) != 1:
                raise ValueError(f'expected exactly one retained {filename}')
            name = matches[0]
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('comparison artifact outside recorded workspace')
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != record['artifacts'][name]:
                raise ValueError(f'comparison artifact changed: {name}')
            selected[filename] = data
        contents.append(selected)
    counts = {}
    for filename in ('program.gb', 'initial-state.csv', 'retirement.csv', 'bus.csv', 'pixels.csv'):
        left, right = (selected[filename] for selected in contents)
        if left != right:
            rows = list(zip(left.splitlines(), right.splitlines()))
            index = next((i for i, (a, b) in enumerate(rows) if a != b), len(rows))
            raise ValueError(f'ordered comparison differs: {filename} row {index + 1}')
        counts[filename] = {'sha256': hashlib.sha256(left).hexdigest(),
                            'bytes': len(left)}
    clients = [json.loads(selected['client.json']) for selected in contents]
    if clients[0]['load']['initial_state'] != clients[1]['load']['initial_state']:
        raise ValueError('initial public host state differs')
    return {'status': 'PASS', 'normal_record': str(normal_path), 'preloaded_record': str(preload_path),
            'comparator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'equal_artifacts': counts, 'initial_state': clients[0]['load']['initial_state'],
            'normal_timings': clients[0]['timings'], 'preloaded_timings': clients[1]['timings'],
            'common_input_count': len(common),
            'limits': 'Matched execution only; transport request histories differ. Timings name their scope.'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--normal', type=Path, required=True)
    parser.add_argument('--preloaded', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(compare(args.root, args.normal, args.preloaded), indent=2))


if __name__ == '__main__':
    main()
