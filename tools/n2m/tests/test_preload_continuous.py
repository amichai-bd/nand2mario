"""Reject mismatched continuous modes, identities, states and ordered evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('continuous_compare', ROOT / 'src/dv/preload/compare_continuous.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ContinuousComparisonTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / 'workdir/builds/preload-continuous-unit'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        registry = json.loads((ROOT / 'src/dv/builder/targets.json').read_text())
        self.records = []
        self.paths = []
        for index, target in enumerate((module.REAL, module.PRELOADED)):
            definition = registry[target]
            names = set(definition['sources'] + definition['python']['inputs'])
            record = dict(status='PASS', seed=1, tools={'questa': 'pinned'},
                          inputs={name: 'same' for name in names}, artifacts={},
                          started='2026-09-07T00:00:00+00:00', finished='2026-09-07T00:00:10+00:00',
                          options=dict(target=target, definition=definition,
                                       vendor_model={'hash': 'pinned'}, python_runtime={'hash': 'pinned'}))
            self.records.append(record)
            folder = self.root / str(index)
            folder.mkdir()
            self.paths.append(folder / 'result.json')
            image = b'x' * 32768
            state = dict(epoch=2, image_sha256=hashlib.sha256(image).hexdigest(),
                         public=dict(STATE=0, IMAGE_VALID=1, PROFILE=1, DOT_LO=0, DOT_HI=0,
                                     RETIRE_LO=0, RETIRE_HI=0, INPUT=0, INPUT_SOURCE=0,
                                     INPUT_EFFECTIVE=0, SNAPSHOT_VALID=0),
                         boundary=dict(reset_sys=0, core_reset=0, paused=1, fault=0,
                                       records=0, bus=0, pixels=0))
            stamps = {name: f'2026-09-07T00:00:0{i}+00:00' for i, name in
                      enumerate(('test_entry', 'loader_start', 'loaded', 'run', 'paused'), 1)}
            client = dict(final_dot=136479, final_state=0, checkpoints_utc=stamps)
            self.put(index, 'program.gb', image)
            self.put(index, 'initial-state.json', json.dumps(state).encode())
            self.put(index, 'client.json', json.dumps(client).encode())
            for name, count in (('retirement.csv', 69), ('bus.csv', 145), ('pixels.csv', 46080)):
                self.put(index, name, ('header\n' + ''.join(f'{n}\n' for n in range(count))).encode())

    def put(self, index, name, data):
        path = self.root / str(index) / name
        path.write_bytes(data)
        self.records[index]['artifacts'][path.relative_to(self.root).as_posix()] = hashlib.sha256(data).hexdigest()

    def run_compare(self):
        for record, path in zip(self.records, self.paths):
            path.write_text(json.dumps(record))
        return module.compare(self.root, *self.paths)

    def test_matched_pair_and_timing(self):
        result = self.run_compare()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['normal_timings']['stage_to_loaded_seconds'], 3)
        self.assertEqual(result['normal_timings']['loader_commands_seconds'], 1)

    def test_wrong_modes_and_configuration(self):
        baseline = copy.deepcopy(self.records)
        changes = (
            lambda r: r[0]['options'].update(target=module.PRELOADED),
            lambda r: r[1]['options']['definition']['args'].append('+pixel_fault'),
            lambda r: r[1]['options'].update(python_runtime={'hash': 'other'}),
            lambda r: r[1]['options'].update(vendor_model={'hash': 'other'}),
            lambda r: r[1].update(seed=2),
            lambda r: r[1].update(status='FAIL'),
            lambda r: r[1]['options']['definition'].update(timeout_seconds=500),
        )
        for change in changes:
            with self.subTest(change=change):
                self.records = copy.deepcopy(baseline)
                change(self.records)
                with self.assertRaises(ValueError):
                    self.run_compare()

    def test_missing_extra_and_changed_input(self):
        baseline = copy.deepcopy(self.records)
        hdl = self.records[1]['options']['definition']['sources'][0]
        for mutation in ('missing', 'extra', 'changed'):
            self.records = copy.deepcopy(baseline)
            if mutation == 'missing':
                del self.records[1]['inputs'][hdl]
            elif mutation == 'extra':
                self.records[1]['inputs']['extra.sv'] = 'same'
            else:
                self.records[1]['inputs'][hdl] = 'changed'
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_compare()

    def test_actual_reordering(self):
        path = self.root / '1/pixels.csv'
        lines = path.read_bytes().splitlines(keepends=True)
        lines[1], lines[2] = lines[2], lines[1]
        self.put(1, 'pixels.csv', b''.join(lines))
        with self.assertRaisesRegex(ValueError, 'pixels.csv row 2'):
            self.run_compare()

    def test_artifact_tampering(self):
        (self.root / '1/program.gb').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'artifact changed'):
            self.run_compare()

    def test_wrong_initial_state_and_time_order(self):
        path = self.root / '1/initial-state.json'
        state = json.loads(path.read_text())
        state['boundary']['core_reset'] = 1
        self.put(1, 'initial-state.json', json.dumps(state).encode())
        with self.assertRaisesRegex(ValueError, 'initial loaded'):
            self.run_compare()
        state['boundary']['core_reset'] = 0
        self.put(1, 'initial-state.json', json.dumps(state).encode())
        client = json.loads((self.root / '1/client.json').read_text())
        client['checkpoints_utc']['loaded'] = '2026-09-06T00:00:00+00:00'
        self.put(1, 'client.json', json.dumps(client).encode())
        with self.assertRaisesRegex(ValueError, 'timing checkpoints'):
            self.run_compare()


if __name__ == '__main__':
    unittest.main()
