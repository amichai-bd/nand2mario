"""The independent Core must not receive a rounded or substituted image."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from src.dv.sameboy import probe


class SameBoyImageBoundary(unittest.TestCase):
    def reject_before_tools(self, image):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            rom = directory / 'program.gb'
            rom.write_bytes(image)
            output = directory / 'attempt'
            argv = ['probe', '--source', str(directory / 'unused-source'),
                    '--rom', str(rom), '--output', str(output)]
            with mock.patch('sys.argv', argv), mock.patch.object(probe.subprocess, 'run') as run:
                with self.assertRaisesRegex(ValueError, 'length/hash mismatch before Core load'):
                    probe.main()
                run.assert_not_called()
            record = json.loads((output / 'result.json').read_text())
            self.assertEqual(record['status'], 'FAIL')
            self.assertEqual(record['commands'], [])

    def test_truncated_image_fails_before_core(self):
        self.reject_before_tools(bytes(32767))

    def test_same_size_substituted_image_fails_before_core(self):
        self.reject_before_tools(bytes(32768))


if __name__ == '__main__':
    unittest.main()
