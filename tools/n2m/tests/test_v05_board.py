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
        for port in ('uart_rx', 'uart_tx', 'board_reset_n'):
            self.assertNotIn(f'VIRTUAL_PIN ON -to "{port}"', qsf)
        sdc = (self.folder / 'checked.sdc').read_text()
        self.assertIn('u_system|u_uart|u_serial_rx|rx_meta', sdc)
        self.assertNotIn('rx_sync', sdc)
        self.assertEqual(len(fpga_controls.required_reports(chains=fpga_v05.UART_CHAINS)), 6)

    def test_invalid_board_mapping_and_identity_rejected(self):
        for port in ('uart_rx', 'uart_tx', 'board_reset_n'):
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


if __name__ == '__main__':
    unittest.main()
