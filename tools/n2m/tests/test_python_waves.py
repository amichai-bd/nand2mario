"""Explicit public waveform selection preserves both retained formats."""
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
        script = next(self.root.glob('workdir/**/run.do')).read_text()
        paths = f"/{target['top']}/wave_clock /{target['top']}/wave_state"
        self.assertIn('log ' + paths + '\n', script)
        self.assertIn('vcd add ' + paths + '\n', script)
        self.assertNotIn('/*', script)
        for bad in ([], ['same', 'same'], ['dut.private'], ['a/b'], ['a;quit'], [True]):
            target['python']['waves'] = bad
            with self.assertRaisesRegex(ValueError, 'waves'):
                python_tb.validate(self.root, target)


if __name__ == '__main__':
    unittest.main()
