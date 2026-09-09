"""Historical fixture rejection, without assembling or running the new game."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'tools'))
from sw.rom_build import require_legacy_scene,build_target
from sw.expressions import AssemblyError
from types import SimpleNamespace


class LegacyRenderer(unittest.TestCase):
    def test_changed_scene_rejected_before_assembly(self):
        root=Path(__file__).resolve().parents[3]
        (root/'workdir').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root/'workdir') as folder:
            with patch('sw.rom_build.assemble_target') as assemble:
                for target in ('render','render-s'):
                    result=build_target(root,Path(folder),SimpleNamespace(target=target,rebuild=True),{})
                    self.assertEqual(result['status'],'FAIL')
                    self.assertIn('old renderer fixture requires',result['error'])
                assemble.assert_not_called()

    def test_unrelated_interaction_unit_not_guarded(self):
        for target in ('flow','flow-s','courier-unit','springtrail'):
            require_legacy_scene(Path('nonexistent'),target)

    def test_normalized_source_and_wrong_source(self):
        class Digest:
            def hexdigest(self):return '148686f9b770a167dc3e0597659f9bb20d8c75783009ffba730e14966cdc8e75'
        with patch.object(Path,'read_bytes',return_value=b'line\r\n'),patch('sw.rom_build.hashlib.sha256',return_value=Digest()) as digest:
            require_legacy_scene(Path('unused'),'render')
            digest.assert_called_once_with(b'line\n')
        with patch.object(Path,'read_bytes',return_value=b'changed'):
            with self.assertRaises(AssemblyError):require_legacy_scene(Path('unused'),'render')
