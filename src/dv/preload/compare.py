"""Compare retained real-load and preloaded executions without relabeling them."""
import argparse
import hashlib
import json
from pathlib import Path


def compare(root, normal_path, preload_path):
    records = [json.loads(path.read_text(encoding='utf-8')) for path in (normal_path, preload_path)]
    if any(record['status'] != 'PASS' for record in records):
        raise ValueError('complete execution equivalence requires two accepted runs')
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
