"""Old composition fixtures fail before creating output or starting control."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from composition_program import build,require_baseline_scene,BASELINE_SCENE_SHA256
from composition_game_reference import require_baseline_rom,BASELINE_ROM_SHA256

class HistoricalComposition(unittest.TestCase):
    def test_changed_scene_fails_before_build(self):
        root=Path(__file__).resolve().parents[3]
        with TemporaryDirectory(dir=root/'workdir') as folder:
            destination=Path(folder)/'unused'
            for short in (True,False):
                with self.assertRaisesRegex(ValueError,'HISTORICAL_COMPOSITION_SOURCE'):
                    build(root,destination,short)
            self.assertFalse(destination.exists())

    def test_source_normalizes_only_line_endings(self):
        class Digest:
            def hexdigest(self):return BASELINE_SCENE_SHA256
        with patch.object(Path,'read_bytes',return_value=b'line\r\n'),patch('composition_program.hashlib.sha256',return_value=Digest()) as digest:
            require_baseline_scene(Path('unused'))
            digest.assert_called_once_with(b'line\n')

    def test_rom_identity_guard(self):
        self.assertEqual(BASELINE_ROM_SHA256,'ec8dfb327d1650d2a206df9180cc56059abfeef956b55d3a0f9571170d9e785f')
        with self.assertRaisesRegex(AssertionError,'HISTORICAL_COMPOSITION_ROM'):
            require_baseline_rom(bytes(32768))
