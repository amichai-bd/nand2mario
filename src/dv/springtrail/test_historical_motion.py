"""Reject incompatible current physics before legacy execution or traffic."""
import hashlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]


class HistoricalMotion(unittest.TestCase):
    def test_old_hud_fixtures_reject_before_output(self):
        import hud_program, hud_render_program
        with tempfile.TemporaryDirectory(dir=ROOT/'workdir') as folder:
            for module in (hud_program, hud_render_program):
                out = Path(folder)/module.__name__
                with self.assertRaisesRegex(ValueError, 'HISTORICAL_HUD_SOURCE'):
                    module.build(ROOT, out)
                self.assertFalse(out.exists())

    def test_old_units_reject_before_assembly(self):
        prior = sys.path[:]
        try:
            sys.path.insert(0, str(ROOT/'tools'))
            from sw.rom_build import build_target
            with tempfile.TemporaryDirectory(dir=ROOT/'workdir') as folder:
                with patch('sw.rom_build.assemble_target') as assembler:
                    for target in ('flow', 'flow-s', 'springtrail-unit'):
                        result = build_target(ROOT, Path(folder),
                            SimpleNamespace(target=target, rebuild=True), {})
                        self.assertEqual(result['status'], 'FAIL')
                        self.assertIn('fixed-physics unit requires old movement', result['error'])
                    assembler.assert_not_called()
        finally:
            sys.path[:] = prior

    def test_rom_guards_precede_traffic(self):
        from hud_game_reference import require_baseline_rom, BASELINE_ROM_SHA256
        self.assertEqual(BASELINE_ROM_SHA256,
            'adbef6b04b5ca7c3896beace71b1735b6dd49115feda0c6ebe20f11ae109f369')
        with self.assertRaisesRegex(AssertionError, 'HISTORICAL_HUD_ROM'):
            require_baseline_rom(bytes(32768))
        prior = sys.path[:]
        try:
            sys.path.insert(0, str(ROOT/'tools'))
            import physical_driver, flow_physical_driver
            client = Mock()
            with self.assertRaisesRegex(AssertionError, 'HISTORICAL_PHYSICAL_ROM'):
                physical_driver.run(client, bytes(32768), Path('unused'), None, None)
            with self.assertRaisesRegex(AssertionError, 'HISTORICAL_PHYSICAL_ROM'):
                flow_physical_driver.run(client, bytes(32768), Path('unused'),
                                         None, None, None, 0, 'success')
            self.assertFalse(client.mock_calls)
        finally:
            sys.path[:] = prior
