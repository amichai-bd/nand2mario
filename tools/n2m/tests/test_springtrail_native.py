"""Native ledger validation must reject missing, changed and unfinished output."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from src.dv.sameboy import probe
from src.dv.sameboy.springtrail import check

CONTRACT = json.loads(Path('src/dv/sameboy/springtrail.json').read_text())


class NativeLedger(unittest.TestCase):
    def fixture(self):
        rows = [dict(kind='frame', index=0, type=1, dot=70224, mode=0),
                dict(kind='frame', index=1, type=2, dot=76963, mode=0),
                dict(kind='input', index=0, dot=137000, buttons=129),
                dict(kind='frame', index=2, type=0, dot=142628, mode=0),
                dict(kind='input', index=1, dot=207224, buttons=1)]
        rows += [dict(kind='frame', index=i, type=0, dot=142628+(i-2)*70224, mode=1)
                 for i in range(3, 6)]
        rows += [dict(kind='end', frames=6, normal_frames=4, inputs=2, dot=353300)]
        return rows, bytes(23040*6)

    def run_check(self, rows, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path/'observations.log').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
            (path/'frames.shades').write_bytes(data)
            return check(path, CONTRACT, 'springtrail-short')

    def test_complete(self):
        self.assertEqual(len(self.run_check(*self.fixture())['frames']), 6)

    def test_missing_frame(self):
        rows, data = self.fixture()
        del rows[-2]
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_FRAME_COUNT'):
            self.run_check(rows, data)

    def test_truncated_pixels(self):
        rows, data = self.fixture()
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_FRAME_BYTES'):
            self.run_check(rows, data[:-1])

    def test_changed_frame(self):
        rows, data = self.fixture()
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_BLANK_FRAME'):
            self.run_check(rows, bytes([1])+data[1:])

    def test_changed_input(self):
        rows, data = self.fixture()
        rows[2]['buttons'] = 0
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_INPUT_MASK'):
            self.run_check(rows, data)

    def test_late_input(self):
        rows, data = self.fixture()
        rows[2]['dot'] += 25
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_INPUT_TIME'):
            self.run_check(rows, data)

    def test_no_end(self):
        rows, data = self.fixture()
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_END'):
            self.run_check(rows[:-1], data)

    def test_duplicate_frame(self):
        rows, data = self.fixture()
        rows.insert(-1, copy.deepcopy(rows[-2]))
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_ORDER'):
            self.run_check(rows, data)

    def test_wrong_callback_type(self):
        rows, data = self.fixture()
        rows[1]['type'] = 0
        with self.assertRaisesRegex(AssertionError, 'REFERENCE_FRAME_COUNT'):
            self.run_check(rows, data)

    def test_original_image_boundary(self):
        for size in (32767, 32768):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as folder:
                p = Path(folder)
                (p/'rom.gb').write_bytes(bytes(size))
                argv = ['probe', '--case', 'springtrail-short', '--source', str(p/'missing'),
                        '--rom', str(p/'rom.gb'), '--output', str(p/'output')]
                with mock.patch('sys.argv', argv), mock.patch.dict(os.environ, {'N2M_TEST_EXECUTION_DEADLINE':'9999999999'}), mock.patch.object(probe.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'length/hash mismatch before Core load'):
                        probe.main()
                    run.assert_not_called()
