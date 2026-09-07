"""Physical board configuration checks; no physical execution is implied."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga, fpga_v05, fpga_controls


class BoardTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[3]
        self.target = fpga.target_definition(self.root, 'v05-board')
        base = self.root / 'workdir/builds/board-host-tests'
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def test_physical_inputs_and_generated_assignments(self):
        fpga.prepare(self.root, self.folder, self.target, build_id='1234567890abcdef' * 2)
        qsf = (self.folder / 'design.qsf').read_text()
        self.assertIn('N2M_V05_BUILD_ID=128\'h1234567890abcdef1234567890abcdef', qsf)
        self.assertIn('RESERVE_ALL_UNUSED_PINS "AS INPUT TRI-STATED"', qsf)
        self.assertIn('IO_STANDARD "3.3 V SCHMITT TRIGGER" -to board_reset_n', qsf)
        self.assertIn('CURRENT_STRENGTH_NEW "8MA" -to "uart_tx"', qsf)
        for port in fpga_v05.BOARD_PINS:
            self.assertNotIn(f'VIRTUAL_PIN ON -to "{port}"', qsf)
        sdc = (self.folder / 'checked.sdc').read_text()
        self.assertIn('u_system|u_uart|u_serial_rx|rx_meta', sdc)
        self.assertNotIn('rx_sync', sdc)
        self.assertEqual(len(fpga_controls.required_reports(chains=fpga_v05.UART_CHAINS)), 6)

    def test_invalid_board_mapping_and_identity_rejected(self):
        for port in fpga_v05.BOARD_PINS:
            with self.subTest(port=port):
                target = copy.deepcopy(self.target)
                target['pins'][port] = 'PIN_A1'
                with self.assertRaises(ValueError):
                    fpga_v05.validate_board(target)
        for identity in (None, '0' * 32, 'bad'):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                fpga.prepare(self.root, self.folder, self.target, build_id=identity)

    def test_placement_proof_remains_distinct(self):
        target = fpga.target_definition(self.root, 'v05')
        self.assertFalse(fpga_v05.board_target(target))
        self.assertIn('uart_rx', target['virtual_pins'])
        self.assertTrue(fpga_v05.board_target(self.target))

    def test_both_compiled_identities_must_match(self):
        identity = '1234567890abcdef' * 2
        fpga.prepare(self.root, self.folder, self.target, build_id=identity)
        output = self.folder / 'output'
        output.mkdir()
        row = f'; BUILD_ID ; {int(identity, 16):0128b} ; Unsigned Binary ;\n'
        report = output / 'design.map.rpt'
        report.write_text(row * 2)
        self.assertEqual(fpga_controls.verify_identity(self.folder, identity,
            macro='N2M_V05_BUILD_ID', instances=2), identity)
        for bad in ('', row, row * 3, row + row.replace('0001', '0011', 1)):
            report.write_text(bad)
            with self.assertRaises(ValueError):
                fpga_controls.verify_identity(self.folder, identity,
                    macro='N2M_V05_BUILD_ID', instances=2)


if __name__ == '__main__':
    unittest.main()
