"""The controls profile preserves exact pins, crossings and proof identities."""
import copy
from pathlib import Path
import tempfile
import unittest
from tools.n2m import fpga, fpga_v05

class ControlsSystemTests(unittest.TestCase):
    def setUp(self):
        self.root=Path(__file__).resolve().parents[3]
        self.target=fpga.target_definition(self.root,'v05-controls-board')

    def test_exact_physical_union_and_no_virtual_controls(self):
        fpga_v05.validate_board(self.target)
        self.assertEqual(len(self.target['pins']),33)
        for mutate in ('pin','virtual','top'):
            bad=copy.deepcopy(self.target)
            if mutate=='pin':bad['pins']['buttons_n[0]']='PIN_AB5'
            elif mutate=='virtual':bad['virtual_pins'].append('buttons_n[*]')
            else:bad['top']='controls_proof'
            with self.assertRaises(ValueError):fpga_v05.validate_board(bad)

    def test_exact_external_and_bridge_exceptions(self):
        text=fpga.checked_constraints(self.target)
        self.assertEqual(text.count('set_false_path -from $controls_'),5)
        self.assertEqual(text.count('set_false_path -from $launch_'),6)
        self.assertIn('u_system|u_uart|u_serial_rx|rx_meta',text)
        self.assertIn('u_physical|u_buttons|button_meta',text)
        self.assertNotIn('set_clock_groups',text)
        audit=fpga_v05.audit(fpga.tcl_word,board=True,controls=True)
        for name in ('button0','button1','button2','button3','uart'):
            self.assertIn('controls_launch_'+name,audit)

    def test_build_identity_and_output_drive(self):
        parent=self.root/'workdir/fpga-unit-tests';parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as d:
            folder=Path(d)
            for bad in (None,'0'*32,'bad'):
                with self.assertRaises(ValueError):fpga.prepare(self.root,folder,self.target,build_id=bad)
            fpga.prepare(self.root,folder,self.target,build_id='12'*16)
            qsf=(folder/'design.qsf').read_text()
            self.assertEqual(qsf.count('CURRENT_STRENGTH_NEW "8MA"'),25)
            self.assertIn('N2M_V05_BUILD_ID',qsf)
            self.assertIn('n2m_adc_pll.v',qsf)
            self.assertIn('n2m_system_pll.v',qsf)
            self.assertIn('n2m_pixel_pll.v',qsf)
