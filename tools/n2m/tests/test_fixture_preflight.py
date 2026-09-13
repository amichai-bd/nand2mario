"""Real host preparations and mutated contracts; no simulator or board access."""
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools'))

from n2m import catalogue, fixture_preflight as preflight, python_tb
from n2m.cli import main
from n2m.simulation import load_target


class FixturePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.imports = preflight.fixture_imports(ROOT)
        cls.imports.__enter__()
        cls.addClassCleanup(cls.imports.__exit__, None, None, None)
        parent = ROOT/'workdir'
        parent.mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(prefix='preflight with spaces ', dir=parent)
        cls.folder = Path(cls.temp.name)
        cls.oam_target = load_target(ROOT, 'python-entities-oam-short')[0]
        cls.render_target = load_target(ROOT, 'python-entity-render-normal')[0]
        cls.oam = cls.folder/'oam'; cls.oam.mkdir()
        cls.render = cls.folder/'render'; cls.render.mkdir()
        python_tb.prepare(cls.oam_target, cls.oam, ROOT)
        python_tb.prepare(cls.render_target, cls.render, ROOT)
        cls.model = importlib.import_module('startup_anchor').Model
        cls.oam_checker = importlib.import_module('entities_oam_check')
        cls.render_checker = importlib.import_module('entities_render_check')

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_real_preparation_has_complete_bank_and_current_sections(self):
        record = json.loads((self.render/'fixture-preflight.json').read_text())
        self.assertEqual(record['banks']['bytes'], 174*16)
        self.assertEqual(record['shared_sections']['count'], 21)
        self.assertEqual(record['scratch'], 'not applicable')
        oam = json.loads((self.oam/'fixture-preflight.json').read_text())
        self.assertEqual(oam['scratch']['cases'], 1)
        self.assertEqual(oam['banks'], 'not applicable')

    def test_actual_missing_dispatch_output_fails_closed(self):
        missing = self.folder/'missing'; missing.mkdir(exist_ok=True)
        with self.assertRaisesRegex(ValueError, 'prepare dispatch produced no preload.json'):
            preflight.verify_prepared(ROOT, self.oam_target, missing)

    def test_missing_input_and_transitive_import_stop_before_prepare(self):
        for path, message in [('src/sw/springtrail/entities.asm', 'software image inputs'),
                              ('src/dv/springtrail/entities_reference.py', 'undeclared')]:
            target = copy.deepcopy(self.oam_target)
            target['python']['inputs'].remove(path)
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, message):
                python_tb.validate(ROOT, target, 'python-entities-oam-short')

    def test_missing_catalogue_entry_stops_before_prepare(self):
        model, path = catalogue.load(ROOT)
        del model['units']['python-entities-oam-short']
        with patch('n2m.catalogue.load', return_value=(model,path)), patch('n2m.python_tb.prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'missing simulation entry'):
                preflight.run(ROOT, self.folder, 'python-entities-oam-short')
            prepare.assert_not_called()

    def test_incomplete_and_wrong_upload_oracle_rejected(self):
        image = (self.render/'program.gb').read_bytes()
        bank = self.render_checker.expected_tiles()
        damaged = bytearray(bank); damaged[16:32] = bytes(16)
        for expected in (bank[:-16], bytes(damaged)):
            with self.subTest(length=len(expected)), self.assertRaisesRegex(ValueError, 'upload bank mismatch'):
                preflight.upload_bank(self.model, image, expected)

    def test_undeclared_actual_entity_scratch_rejected(self):
        image = (self.oam/'program.gb').read_bytes()
        with patch.object(self.oam_checker, 'SCRATCH_RANGES', ((0xc034,0xc04c),)):
            with self.assertRaisesRegex(ValueError, 'source write C339: ENTITY_OAM_UNRELATED_WRITE'):
                preflight.scratch_writes(self.model, image, self.oam_checker.Check(True))

    def test_changed_preload_and_missing_source_section_rejected(self):
        from n2m.preload import verify
        mif = self.oam/'preload-rom.mif'; original = mif.read_bytes()
        try:
            mif.write_bytes(original.replace(b'WIDTH = 8;', b'WIDTH = 7;', 1))
            with self.assertRaisesRegex(ValueError, 'preload file changed'):
                verify(self.oam)
        finally:
            mif.write_bytes(original)
        fixture = json.loads((self.oam/'entities_oam-unit.json').read_text())
        source = next((self.oam/'source').rglob('image.gb'))
        source_map = json.loads(source.with_name('map.json').read_text())
        removed = fixture['sections'].pop()
        del fixture['shared_sections'][removed['name']]
        with self.assertRaisesRegex(ValueError, 'complete shared-section'):
            preflight.shared_sections((self.oam/'program.gb').read_bytes(), source.read_bytes(), fixture, source_map)

    def test_actual_wrapper_import_rejects_missing_module_symbol_and_test(self):
        folder = self.folder/'wrapper'; folder.mkdir(exist_ok=True)
        wrapper = folder/'fixture_wrapper.py'
        dependency = folder/'fixture_dependency.py'; dependency.write_text('value = 1\n')
        target = {'python': {'module':'fixture_wrapper', 'test':'test_case',
                            'inputs':[wrapper.relative_to(ROOT).as_posix()]}}
        wrapper.write_text('from fixture_dependency import value\ndef test_case(): pass\n')
        self.assertEqual(preflight.import_target(ROOT,target,folder)['status'],'PASS')
        for body,reason in [('from fixture_dependency import absent','cannot import name'),
                            ('import nonexistent_fixture_module','No module named'),
                            ('value = 1','missing selected test')]:
            wrapper.write_text(body+'\n')
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError,reason):
                preflight.import_target(ROOT,target,folder)

    def test_prepare_restores_prior_v05_reference_and_unrelated_modules(self):
        import importlib.util
        prior_path = sys.path[:]
        sentinel = object()
        spec = importlib.util.spec_from_file_location('reference', ROOT/'src/dv/v05/reference.py')
        old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
        folder = self.folder/'after-v05'; folder.mkdir(exist_ok=True)
        with patch.dict(sys.modules, {'reference': old, 'unrelated_fixture_sentinel': sentinel}):
            python_tb.prepare(self.oam_target, folder, ROOT)
            self.assertIs(sys.modules['reference'], old)
            self.assertIs(sys.modules['unrelated_fixture_sentinel'], sentinel)
            self.assertEqual(sys.path, prior_path)
            with self.assertRaisesRegex(ValueError, 'prepare dispatch'):
                with preflight.fixture_imports(ROOT):
                    preflight.verify_prepared(ROOT, self.oam_target, self.folder/'no-image')
            self.assertIs(sys.modules['reference'], old)
            self.assertIs(sys.modules['unrelated_fixture_sentinel'], sentinel)
            self.assertEqual(sys.path, prior_path)

    def test_public_preflight_has_fixed_whole_wall_cap(self):
        from n2m.test_budget import main as supervised
        from contextlib import redirect_stdout
        import io
        with patch('sys.argv',['tools/build.py','sim','preflight','python-entity-render-normal','--tag','budget']), \
             patch('n2m.test_budget.supervise',return_value=(0,'{}')) as run, redirect_stdout(io.StringIO()):
            self.assertEqual(supervised(),0)
        self.assertEqual(run.call_args.kwargs,{'ceiling':300})

    def test_cli_never_discovers_questa(self):
        from contextlib import redirect_stdout
        import io
        with patch('n2m.fixture_preflight.import_target', return_value={'status':'tested separately'}), patch('n2m.cli.Simulator') as simulator, redirect_stdout(io.StringIO()) as output:
            code = main(['sim','preflight','python-joypad','--tag','preflight-cli-'+self.folder.name.split()[-1],'--json'], root=ROOT)
        self.assertEqual(code, 0, output.getvalue())
        simulator.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['checks']['banks'], 'not applicable')
