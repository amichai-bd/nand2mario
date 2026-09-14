"""Explicit public waveform selection is validated; Verilator retains the whole top."""
import json
import unittest

import test_python_tb as baseline
from n2m import python_tb


class WaveTests(unittest.TestCase):
    setUp = baseline.PythonTests.setUp
    run_stage = baseline.PythonTests.run_stage

    def test_public_selection_and_rejected_paths(self):
        registry = self.root / 'src/dv/builder/targets.json'
        targets = json.loads(registry.read_text())
        target = targets['python-joypad']
        target['python']['waves'] = ['wave_clock', 'wave_state']
        registry.write_text(json.dumps(targets))
        result = self.run_stage()
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['waves']['format'], 'fst')
        self.assertEqual(list(self.root.glob('workdir/**/run.do')), [])
        for bad in ([], ['same', 'same'], ['dut.private'], ['a/b'], ['a;quit'], [True]):
            target['python']['waves'] = bad
            with self.assertRaisesRegex(ValueError, 'waves'):
                python_tb.validate(self.root, target)


if __name__ == '__main__':
    unittest.main()
