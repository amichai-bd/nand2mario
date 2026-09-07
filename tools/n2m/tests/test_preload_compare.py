"""Comparison must reject incomplete, changed and reordered execution evidence."""
import hashlib
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('preload_compare', ROOT / 'src/dv/preload/compare.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PreloadComparisonTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'workdir/builds/preload-compare-unit'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = []
        for mode in ('normal', 'preloaded'):
            folder = self.root / mode
            folder.mkdir()
            definition = {'top': 'tb_integration', 'args': [], 'expected_exit': 'zero',
                          'sources': ['rtl'], 'driver': {'peer': 'src/dv/integration/peer.py', 'inputs': []}}
            record = {'status': 'PASS', 'inputs': {'rtl': 'same'}, 'tools': {}, 'artifacts': {},
                      'seed': 1, 'options': {'target': 'integration-smoke', 'definition': definition}}
            if mode == 'preloaded':
                record['options']['target'] = 'integration-preloaded'
                definition['args'] = ['-gPRELOADED=1']
                definition['driver'].update(peer='src/dv/preload/peer.py', preload=True,
                                            inputs=['src/dv/integration/peer.py'])
                record['inputs']['src/dv/preload/peer.py'] = 'extra'
            values = {'program.gb': b'original', 'initial-state.csv': b'epoch\n2\n',
                      'retirement.csv': b'seq,data\n0,01\n1,02\n', 'bus.csv': b'bus\nread\n',
                      'pixels.csv': b'pixel\n0\n1\n',
                      'client.json': json.dumps({'load': {'initial_state': {'STATE': 1}}, 'timings': {}}).encode()}
            for name, data in values.items():
                path = folder / name
                path.write_bytes(data)
                record['artifacts'][path.relative_to(self.root).as_posix()] = hashlib.sha256(data).hexdigest()
            path = folder / 'result.json'
            path.write_text(json.dumps(record))
            self.paths.append(path)

    def test_identical_execution(self):
        self.assertEqual(module.compare(self.root, *self.paths)['status'], 'PASS')

    def test_actual_reordering(self):
        path = self.root / 'preloaded/pixels.csv'
        path.write_bytes(b'pixel\n1\n0\n')
        record = json.loads(self.paths[1].read_text())
        record['artifacts']['preloaded/pixels.csv'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.paths[1].write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'pixels.csv row 2'):
            module.compare(self.root, *self.paths)

    def test_retained_file_tampering(self):
        (self.root / 'normal/program.gb').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            module.compare(self.root, *self.paths)

    def test_incomplete_or_changed_source(self):
        baseline = json.loads(self.paths[1].read_text())
        for field, value, expected in (('status', 'FAIL', 'two accepted'),
                                       ('inputs', {'rtl': 'changed', 'src/dv/preload/peer.py': 'extra'}, 'source/tool')):
            record = copy.deepcopy(baseline)
            record[field] = value
            self.paths[1].write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, expected):
                module.compare(self.root, *self.paths)

    def test_rejects_two_preloaded_records(self):
        with self.assertRaisesRegex(ValueError, 'target modes'):
            module.compare(self.root, self.paths[1], self.paths[1])

    def test_missing_hdl_input(self):
        record = json.loads(self.paths[1].read_text())
        del record['inputs']['rtl']
        self.paths[1].write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'HDL inputs'):
            module.compare(self.root, *self.paths)

    def test_changed_runtime_args(self):
        record = json.loads(self.paths[1].read_text())
        record['options']['definition']['args'].append('+pixel_fault')
        self.paths[1].write_text(json.dumps(record))
        with self.assertRaisesRegex(ValueError, 'runtime modes or args'):
            module.compare(self.root, *self.paths)


if __name__ == '__main__':
    unittest.main()
