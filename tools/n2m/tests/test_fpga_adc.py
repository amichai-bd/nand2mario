"""Sensitivity of the exact explained vendor-warning boundary."""
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.n2m import fpga, fpga_adc


class AdcDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path.cwd() / "workdir/adc-classifier-fixture"
        text = (Path(__file__).parent / "data/adc-unused-features.txt").read_text()
        self.text = text.replace("{folder}", self.folder.as_posix())
        self.sources = {n: {"sha256": h} for n, h in fpga_adc.SUPPORTED_CONTROL.items()}
        self.hashes = patch.object(fpga_adc, "file_hash", side_effect=lambda p: fpga_adc.SUPPORTED_CONTROL[p.name])
        self.hashes.start()
        self.addCleanup(self.hashes.stop)

    def classify(self, text=None):
        text = self.text if text is None else text
        explained = fpga_adc.explained_diagnostics(text, self.folder, self.sources)
        return fpga.diagnostics(text, explained)

    def test_exact_retained_vendor_inventory_visible(self):
        result = self.classify()
        self.assertEqual(len(result), 15)
        self.assertTrue(all(r["reason"] for r in result))

    def test_missing_duplicate_extra_or_wrong_instance_rejected(self):
        lines = self.text.splitlines()
        cases = ["\n".join(lines[1:]), self.text + lines[-1] + "\n",
                 self.text + 'Warning (10036): unrelated unused register\n',
                 self.text.replace('ts_avrg_fifo', 'product_memory'),
                 self.text.replace('q_b[11]', 'q_b[12]')]
        for text in cases:
            with self.subTest(text=text[-80:]), self.assertRaises(ValueError):
                self.classify(text)

    def test_other_warning_and_missing_source_pin_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexplained"):
            self.classify(self.text + 'Warning (15058): wrong clock mode\n')
        self.sources['altera_modular_adc_control_fsm.v']['sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, "unsupported ADC source"):
            self.classify()

    def test_changed_copied_vendor_source_rejected(self):
        with patch.object(fpga_adc, 'file_hash', return_value='changed'):
            with self.assertRaisesRegex(ValueError, "copied ADC source"):
                self.classify()

    def test_controls_system_requires_exact_relocated_vendor_owner(self):
        relocated = self.text.replace('n2m_adc_backend:u_adc|',
            'n2m_controls_system:u_controls|n2m_adc_backend:u_adc|')
        result = fpga_adc.explained_diagnostics(relocated, self.folder, self.sources,
                                               'v05_controls_proof')
        self.assertEqual(len(result), 15)
        for bad in (self.text, relocated.replace('u_controls|', 'wrong_controls|')):
            with self.assertRaises(ValueError):
                fpga_adc.explained_diagnostics(bad, self.folder, self.sources,
                                              'v05_controls_proof')
        with self.assertRaises(ValueError):
            self.classify(relocated)

    def test_no_global_warning_code_waiver(self):
        with self.assertRaisesRegex(ValueError, "unexplained"):
            fpga.diagnostics(self.text)


if __name__ == '__main__':
    unittest.main()
