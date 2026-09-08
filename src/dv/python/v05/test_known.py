"""Host checks using the pinned public cocotb logic types; no simulator needed."""
import os
from pathlib import Path
import subprocess
import sys
import unittest

from cocotb.types import Logic, LogicArray
from test_v05 import known


class Sample:
    _name = 'sample'

    def __init__(self, value):
        self._value = value
        self.reads = 0

    @property
    def value(self):
        self.reads += 1
        if self.reads != 1:
            raise AssertionError('sample was read twice')
        return self._value


class KnownTests(unittest.TestCase):
    def test_scalar_symbols(self):
        for symbol, expected in [('0', 0), ('1', 1), ('L', 0), ('H', 1)]:
            sample = Sample(Logic(symbol))
            self.assertEqual(known(sample), expected)
            self.assertEqual(sample.reads, 1)
        for symbol in 'XZUW-':
            sample = Sample(Logic(symbol))
            with self.assertRaisesRegex(AssertionError, '^V05_UNKNOWN sample$'):
                known(sample)
            self.assertEqual(sample.reads, 1)

    def test_packed_symbols_and_observed_widths(self):
        for width in (1, 8, 32, 64, 88, 104, 117, 384):
            for symbol in '01LHXZUW-':
                for position in sorted({0, width // 2, width - 1}):
                    text = ('10LH' * ((width + 3) // 4))[:width]
                    text = text[:position] + symbol + text[position + 1:]
                    sample = Sample(LogicArray(text))
                    if symbol in 'XZUW-':
                        with self.assertRaisesRegex(AssertionError, '^V05_UNKNOWN sample$'):
                            known(sample)
                    else:
                        expected = sum(1 << index for index, bit in enumerate(reversed(text)) if bit in '1H')
                        self.assertEqual(known(sample), expected)
                    self.assertEqual(sample.reads, 1)

    def test_resolver_settings_do_not_change_checks(self):
        for resolver in ('error', 'value_error', 'weak', 'zeros', 'ones', 'random'):
            result = subprocess.run(
                [sys.executable, '-B', str(Path(__file__).resolve()), 'KnownTests.test_scalar_symbols',
                 'KnownTests.test_packed_symbols_and_observed_widths'],
                env=dict(os.environ, COCOTB_RESOLVE_X=resolver), capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
