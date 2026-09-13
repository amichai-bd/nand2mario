"""Real Git impact and omission witnesses; no simulator is invoked."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from n2m import affected, catalogue

ROOT=Path(__file__).resolve().parents[3]


class Impact(unittest.TestCase):
    def setUp(self):
        base=ROOT/'workdir/builds/affected-unit-tests';base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='git space ',dir=base);self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.write('.gitignore','workdir/\n')
        for p in ('tools/build.py','tools/n2m/runtime.py','tools/n2m/dependencies.json',
                  'src/dv/python/requirements.txt','src/dv/python/THIRD_PARTY.md'):
            self.write(p,'# fixture\n')
        self.write('src/dv/springtrail/model.py','VALUE=1\n')
        self.write('src/dv/springtrail/other.py','VALUE=2\n')
        self.write('src/dv/springtrail/test_a.py','from model import VALUE\ndef contract():pass\n')
        self.write('src/dv/springtrail/test_b.py','from other import VALUE\ndef contract():pass\n')
        self.write('tools/test_host.py','import unittest\n')
        self.write('src/rtl/tb.sv','module tb; endmodule\n')
        self.targets={}
        for name,model in (('a','model'),('b','other')):
            self.targets[name]=dict(signature='PASS',expected_exit='zero',top='tb',testbench='python',
                sources=['src/rtl/tb.sv'],python=dict(module='test_'+name,test='contract',
                inputs=['src/dv/springtrail/test_'+name+'.py','src/dv/springtrail/'+model+'.py']))
        self.registry()
        entry=dict(kind='sim',level=0,labels=['test'],duration_seconds=None)
        doc=dict(version=1,labels={'test':'fixture'},units={'a':entry,'b':entry,
            'tools/test_host.py':dict(entry,kind='unit')},not_runnable={})
        self.write(catalogue.CATALOGUE,catalogue.format_document(doc))
        self.git('init','-q');self.git('config','core.autocrlf','false')
        self.git('config','user.email','fixture@example.invalid');self.git('config','user.name','Fixture')
        self.commit();self.base=self.git('rev-parse','HEAD').strip()

    def write(self,p,text):
        path=self.root/p;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
    def git(self,*args):return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.PIPE,text=True)
    def commit(self):self.git('add','.');self.git('commit','-qm','fixture')
    def registry(self):self.write('src/dv/builder/targets.json',json.dumps(self.targets))
    def result(self):return affected.report(self.root,self.base)

    def test_changed_transitive_model_selects_only_qualified_simulation(self):
        self.write('src/dv/springtrail/model.py','VALUE=9\n')
        report=self.result()
        self.assertEqual(report['units']['a']['decision'],'selected')
        self.assertEqual(report['units']['b']['decision'],'review_candidate')
        self.assertEqual(report['units']['tools/test_host.py']['decision'],'selected')
        self.assertIn('no tests executed',report['scope'])
        self.assertIn('not accepted reuse',report['units']['b']['limitation'])

    def test_real_added_deleted_and_renamed_paths_force_fallback(self):
        for mode in ('add','delete','rename'):
            with self.subTest(mode=mode):
                path=self.root/'src/dv/springtrail/model.py'
                if mode=='add':self.write('new.dat','payload')
                elif mode=='delete':path.unlink()
                else:self.git('mv','src/dv/springtrail/model.py','src/dv/springtrail/renamed.py')
                report=self.result()
                self.assertTrue(report['fallback']);self.assertEqual(report['review_candidates'],0)
                self.git('reset','--hard',self.base)
                if (self.root/'new.dat').exists():(self.root/'new.dat').unlink()

    def test_unmapped_modified_file_cannot_be_input_equal(self):
        self.write('notes.md','one');self.commit();self.base=self.git('rev-parse','HEAD').strip()
        self.write('notes.md','two')
        self.assertEqual(self.result()['review_candidates'],0)

    def test_omitted_transitive_input_is_refused_even_without_changed_paths(self):
        self.targets['a']['python']['inputs'].remove('src/dv/springtrail/model.py');self.registry();self.commit()
        self.base=self.git('rev-parse','HEAD').strip()
        row=self.result()['units']['a']
        self.assertEqual(row['decision'],'selected');self.assertIn('undeclared transitive',row['reasons'][0])

    def test_dynamic_import_alias_is_uncertain_at_equal_inputs(self):
        self.write('src/dv/springtrail/test_a.py','from importlib import import_module as load\nload("model")\ndef contract():pass\n')
        self.commit();self.base=self.git('rev-parse','HEAD').strip()
        row=self.result()['units']['a']
        self.assertEqual(row['decision'],'selected');self.assertIn('dynamic',row['reasons'][0])

    def test_unresolved_import_cannot_be_an_equal_input_candidate(self):
        self.write('src/dv/springtrail/test_a.py','import missing_dependency\ndef contract():pass\n')
        self.commit();self.base=self.git('rev-parse','HEAD').strip()
        row=self.result()['units']['a']
        self.assertEqual(row['decision'],'selected');self.assertIn('unresolved',row['reasons'][0])

    def test_changed_implicit_tool_configuration_and_test(self):
        for path in ('tools/n2m/runtime.py','tools/n2m/dependencies.json','src/dv/builder/targets.json',
                     'src/dv/springtrail/test_a.py'):
            with self.subTest(path=path):
                original=(self.root/path).read_text(encoding='utf-8');self.write(path,original+'\n')
                report=self.result();self.assertEqual(report['units']['a']['decision'],'selected')
                if path.startswith('tools/') or path.endswith('targets.json'):self.assertEqual(report['review_candidates'],0)
                self.write(path,original)

    def test_missing_catalogue_test_is_a_validation_failure(self):
        self.write('tools/test_missing.py','import unittest\n')
        with self.assertRaisesRegex(ValueError,'missing from'):self.result()

    def test_bad_base_ref_is_refused(self):
        with self.assertRaises(subprocess.CalledProcessError):affected.report(self.root,'--help')


if __name__=='__main__':unittest.main()
