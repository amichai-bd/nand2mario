"""Real Git impact and omission witnesses; no simulator is invoked."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from n2m import affected, catalogue
from n2m.cli import main

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
        self.write('src/dv/springtrail/test_a.py','import cocotb\nfrom model import VALUE\n@cocotb.test()\nasync def contract(dut):assert VALUE==1\n')
        self.write('src/dv/springtrail/test_b.py','import cocotb\nfrom other import VALUE\n@cocotb.test()\nasync def contract(dut):assert VALUE==2\n')
        self.write('tools/test_host.py','import unittest\n')
        self.write('src/rtl/tb.sv','module tb; endmodule\n')
        self.targets={}
        for name,model in (('a','model'),('b','other')):
            self.targets[name]=dict(signature='PASS',expected_exit='zero',top='tb',testbench='python',simulators=['verilator'],
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
        self.assertEqual(row['decision'],'selected');self.assertIn('unqualified',row['reasons'][0])

    def test_unresolved_import_cannot_be_an_equal_input_candidate(self):
        self.write('src/dv/springtrail/test_a.py','import missing_dependency\ndef contract():pass\n')
        self.commit();self.base=self.git('rev-parse','HEAD').strip()
        row=self.result()['units']['a']
        self.assertEqual(row['decision'],'selected');self.assertIn('unresolved',row['reasons'][0])

    def test_dynamic_loaders_and_io_cannot_hide_behind_another_targets_declaration(self):
        loaders=(
            'import importlib.util\ns=importlib.util.spec_from_file_location("other", "src/dv/springtrail/other.py")\nm=importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\n',
            'from importlib.util import spec_from_file_location as spec, module_from_spec as module\ns=spec("other", "src/dv/springtrail/other.py")\ns.loader.exec_module(module(s))\n',
            'import io\nDATA=io.FileIO("src/dv/springtrail/other.py").read()\n',
            'from io import FileIO as read_file\nDATA=read_file("src/dv/springtrail/other.py").read()\n')
        for source in loaders:
            with self.subTest(source=source):
                self.write('src/dv/springtrail/test_a.py',source+'def contract():pass\n')
                self.commit();self.base=self.git('rev-parse','HEAD').strip()
                self.write('src/dv/springtrail/other.py','VALUE=99\n')
                report=self.result()
                self.assertEqual(report['units']['a']['decision'],'selected')
                self.assertIn('unqualified',report['units']['a']['reasons'][0])
                self.assertEqual(report['units']['b']['decision'],'selected')
                self.write('src/dv/springtrail/other.py','VALUE=2\n')

    def test_changed_implicit_tool_configuration_and_test(self):
        for path in ('tools/n2m/runtime.py','tools/n2m/dependencies.json','src/dv/builder/targets.json',
                     'src/dv/springtrail/test_a.py'):
            with self.subTest(path=path):
                original=(self.root/path).read_text(encoding='utf-8');self.write(path,original+'\n')
                report=self.result();self.assertEqual(report['units']['a']['decision'],'selected')
                if path.startswith('tools/') or path.endswith('targets.json'):self.assertEqual(report['review_candidates'],0)
                self.write(path,original)

    def test_implicit_and_nested_execution_shapes_are_not_static_candidates(self):
        for source in ('def contract(value=load()):pass\n',
                       'def contract(value: load()):pass\n',
                       'VALUE=lambda: 1\ndef contract():pass\n',
                       'VALUES=[x for x in values]\ndef contract():pass\n',
                       '@marker\ndef contract():pass\n',
                       'class Dynamic:pass\ndef contract():pass\n',
                       'with context:pass\ndef contract():pass\n'):
            with self.subTest(source=source):
                self.write('src/dv/springtrail/test_a.py',source)
                self.commit();self.base=self.git('rev-parse','HEAD').strip()
                self.assertEqual(self.result()['units']['a']['decision'],'selected')

    def test_declared_imported_model_must_also_have_supported_shape(self):
        self.write('src/dv/springtrail/model.py','VALUE=load()\n')
        self.commit();self.base=self.git('rev-parse','HEAD').strip()
        row=self.result()['units']['a']
        self.assertEqual(row['decision'],'selected')
        self.assertIn('model.py',row['reasons'][0])

    def test_missing_catalogue_test_is_a_validation_failure(self):
        self.write('tools/test_missing.py','import unittest\n')
        with self.assertRaisesRegex(ValueError,'missing from'):self.result()

    def test_bad_base_ref_is_refused(self):
        with self.assertRaises(subprocess.CalledProcessError):affected.report(self.root,'--help')


    def cli(self,*argv):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):code=main(['tests','affected','--base',self.base,*argv],root=self.root)
        return code,output.getvalue()

    def test_text_output_lists_every_unit_decision_and_the_json_summary(self):
        self.write('src/dv/springtrail/model.py','VALUE=9\n')
        code,text=self.cli('--json');self.assertEqual(code,0);report=json.loads(text)
        self.assertEqual((report['status'],report['selected'],report['review_candidates']),('PASS',2,1))
        code,text=self.cli();self.assertEqual(code,0);lines=text.splitlines()
        self.assertEqual(lines[0],'PASS: tests tag=-')
        self.assertIn(f"Base: {report['base']}  head: {report['head']}  1 changed paths",lines)
        self.assertIn('a: selected changed inputs: src/dv/springtrail/model.py',lines)
        self.assertIn('b: review_candidate validated declared repository inputs equal base',lines)
        self.assertIn('tools/test_host.py: selected standalone host dependency closure is unknown',lines)
        self.assertIn('2 selected, 1 review candidates of 3 units',lines)
        self.assertNotIn('Fallback:',text);self.assertIn('Scope: advisory only',text);self.assertIn('Elapsed: ',text)

    def test_text_output_names_each_fallback_reason(self):
        self.write('new.dat','payload')
        code,text=self.cli();self.assertEqual(code,0)
        self.assertIn('Fallback: new, deleted or renamed paths require full impact review',text.splitlines())
        self.assertIn('0 review candidates',text)


if __name__=='__main__':unittest.main()
