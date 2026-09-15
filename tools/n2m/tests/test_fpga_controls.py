"""Reject unidentified or mismatched physical controls bitstreams."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m.fpga_controls import verify_identity


class IdentityTests(unittest.TestCase):
    def test_compiled_identity_and_mutations(self):
        parent = Path(__file__).resolve().parents[3] / 'workdir' / 'controls-unit-tests'
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as name:
            folder = Path(name)
            (folder / 'output').mkdir()
            identity = '123456789abcdef00123456789abcdef'
            qsf = f'set_global_assignment -name VERILOG_MACRO "N2M_CONTROLS_BUILD_ID=128\'h{identity}"\n'
            mapped = f'; BUILD_ID ; {int(identity, 16):0128b} ; Unsigned Binary ;\n'
            (folder / 'design.qsf').write_text(qsf)
            (folder / 'output/design.map.rpt').write_text(mapped)
            self.assertEqual(verify_identity(folder, identity), identity)
            for invalid in (None, '0' * 32, identity[:-1], 'f' * 32):
                with self.assertRaises(ValueError):
                    verify_identity(folder, invalid)
            for changed in ('', mapped * 2, mapped.replace('Unsigned Binary', 'Signed Binary'),
                            mapped.replace('00010010', '00010011', 1)):
                (folder / 'output/design.map.rpt').write_text(changed)
                with self.assertRaises(ValueError):
                    verify_identity(folder, identity)
            (folder / 'output/design.map.rpt').write_text(mapped)
            (folder / 'design.qsf').write_text(qsf * 2)
            with self.assertRaises(ValueError):
                verify_identity(folder, identity)


class UnaryChainTests(unittest.TestCase):
    """The fitter may pack an inverter behind a feeder LUT; longer or wider logic fails."""
    def lut(self, cells, params, name, mask, **inputs):
        ports = {'dataa': 'gnd', 'datab': 'gnd', 'datac': 'gnd', 'datad': 'gnd', 'cin': 'gnd', 'cout': '',
                 'combout': '\\' + name + '_combout'}
        ports.update(inputs)
        cells[name] = ('fiftyfivenm_lcell_comb', ports)
        params[name] = {'lut_mask': mask, 'sum_lutc_input': '"datac"'}
        return ports['combout']

    def test_one_or_two_unary_luts_compose_polarity(self):
        from n2m.fpga_controls import unary_chain
        cells, params = {}, {}
        source = '\\buttons_n[0]~input_o'
        inverted = self.lut(cells, params, 'meta~1', "16'h00FF", datad=source)
        fed = self.lut(cells, params, 'meta~feeder', "16'hFF00", datad=inverted)
        self.assertEqual(unary_chain(cells, params, source, inverted), [('meta~1', True, source)])
        self.assertEqual(unary_chain(cells, params, source, fed), [('meta~1', True, source), ('meta~feeder', False, inverted)])
        duplicated = self.lut(cells, params, 'sync~feeder', "16'hF0F0", dataa=source, datac=source)
        self.assertEqual(unary_chain(cells, params, source, duplicated), [('sync~feeder', False, source)])

    def test_wide_long_ambiguous_and_constant_logic_fail(self):
        from n2m.fpga_controls import unary_chain
        source, other = '\\buttons_n[0]~input_o', '\\other'
        cells, params = {}, {}
        first = self.lut(cells, params, 'a', "16'h00FF", datad=source)
        second = self.lut(cells, params, 'b', "16'hFF00", datad=first)
        third = self.lut(cells, params, 'c', "16'hFF00", datad=second)
        with self.assertRaisesRegex(ValueError, 'bounded unary LUT chain'):
            unary_chain(cells, params, source, third)
        cells, params = {}, {}
        wide = self.lut(cells, params, 'wide', "16'hFF00", datac=other, datad=source)
        with self.assertRaisesRegex(ValueError, 'unrelated inputs'):
            unary_chain(cells, params, source, wide)
        cells, params = {}, {}
        constant = self.lut(cells, params, 'constant', "16'h0000", datad=source)
        with self.assertRaisesRegex(ValueError, 'polarity differs'):
            unary_chain(cells, params, source, constant)
        cells, params = {}, {}
        shared = self.lut(cells, params, 'one', "16'hFF00", datad=source)
        self.lut(cells, params, 'two', "16'hFF00", datad=source, combout=shared)
        with self.assertRaisesRegex(ValueError, 'one unary LUT'):
            unary_chain(cells, params, source, shared)
        cells, params = {}, {}
        carry = self.lut(cells, params, 'carry', "16'hFF00", datad=source, cin='\\carry_in')
        with self.assertRaisesRegex(ValueError, 'LUT mode differs'):
            unary_chain(cells, params, source, carry)
        with self.assertRaisesRegex(ValueError, 'one unary LUT'):
            unary_chain(cells, params, source, '\\undriven')
