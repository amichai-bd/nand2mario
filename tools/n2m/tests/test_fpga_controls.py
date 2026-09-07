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
