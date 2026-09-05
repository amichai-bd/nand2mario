"""Assembler syntax/object/cache contracts; real opcode coverage is conformance.py."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sw.assembler import assemble
from sw.build import assemble_target
from sw.conformance import matrix
from sw.expressions import AssemblyError, evaluate, parse
from sw.objects import validate

ROOT = Path(__file__).resolve().parents[3]


class AssemblerTests(unittest.TestCase):
    def setUp(self):
        base=ROOT/'workdir/builds/assembler-unit-tests'
        base.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='space ',dir=base)
        self.addCleanup(self.temp.cleanup)
        self.tree=Path(self.temp.name)
        self.prelude=ROOT/'src/sw/generated/interfaces.inc'

    def assemble(self, text, assets=None):
        path=self.tree/'main.asm'
        path.write_text(text,encoding='utf-8',newline='')
        return assemble(path,self.tree,self.prelude,assets)

    def test_expressions_exact_arithmetic_and_precedence(self):
        cases={'1+2*3':7,'(1+2)*3':9,'-7/3':-2,'7/-3':-2,'-7/-3':2,
               '-8>>2':-2,'1<<3+1':16,'1|2^3&4':3,'LOW($1234)':52,'HIGH(65535)':255,
               '%1010 + $0f':25,'~0':-1}
        for source,value in cases.items():
            with self.subTest(source=source):self.assertEqual(evaluate(parse(source),{}),value)
        for source in ['1/0','1<<64','1>>-1','LOW(-1)','HIGH(65536)','1**2','0x10','1_000','LOW(1','']:
            with self.subTest(source=source),self.assertRaises(AssemblyError):evaluate(parse(source),{})

    def test_directives_forward_constants_and_ascii_escapes(self):
        obj=self.assemble('Count EQU Later\nLater EQU 3\nSECTION "bytes",ROM\nStart: DB "a;\\n",-128,255\nDW -32768,65535\nEXPORT Start\nSECTION "ram",RAM\nBuffer: DS Count\n')
        self.assertEqual(obj['sections'][0]['data'],[97,59,10,128,255,0,128,255,255])
        self.assertEqual(obj['sections'][1]['size'],3)
        self.assertEqual(obj['sections'][1]['data'],[])
        self.assertEqual(obj['listing'][0]['span']['column'],8)

    def test_original_matrix_includes_every_family(self):
        cases=matrix()
        obj=self.assemble('SECTION "code",ROM\n'+'\n'.join(case['text'] for case in cases)+'\n')
        self.assertEqual(len(obj['listing']),569)
        self.assertEqual(obj['sections'][0]['data'][:3],[0,16,0])
        self.assertTrue(all(r['kind']=='REL8' for r in obj['relocations']))

    def test_relocation_constraints_and_imports(self):
        obj=self.assemble('IMPORT External\nSECTION "code",ROM\nLD A,LOW(External)\nLD BC,External\nCALL External\nJR External\nBIT External,A\nRST External\nLDH [External],A\nADD SP,External\n')
        rel=obj['relocations']
        self.assertEqual([r['kind'] for r in rel],['LOW8','U16LE','ADDR16LE','REL8','U8','U8','U8','U8'])
        self.assertEqual((rel[4]['mask'],rel[4]['shift'],rel[4]['maximum']),(56,3,7))
        self.assertEqual(rel[5]['allowed'],list(range(0,57,8)))
        self.assertEqual((rel[6]['minimum'],rel[6]['maximum'],rel[6]['bias']),(65280,65535,-65280))
        self.assertEqual((rel[7]['minimum'],rel[7]['maximum']),(-128,127))
        self.assertTrue(all(r['span']['file']=='main.asm' for r in rel))

    def test_invalid_syntax_operands_ranges_and_symbols(self):
        cases=['LD A,256','LD A,-129','LD BC,65536','LD BC,-32769','CALL -1','JP 65536',
               'ADD SP,128','LD HL,SP-129','BIT 8,A','BIT -1,A','RST 1','RST 64',
               'LDH [255],A','LDH A,[65536]','ADD B','SUB A','XOR [HL]','LD A,[HLI]',
               'LDI [HL],A','STOP 0','IM 1','DB "é"','DB "\\q"','DW LOW(65536)',
               'DS 1','DB Missing','EXPORT Missing','IMPORT Item\nItem: NOP',
               'Item: NOP\nItem: NOP','SECTION "code",ROM','A EQU 1',
               'One EQU Two+@\nTwo EQU One','DB 1/0','DB 1<<64']
        for statement in cases:
            with self.subTest(statement=statement),self.assertRaises(AssemblyError) as caught:
                self.assemble('SECTION "code",ROM\n'+statement+'\n')
            self.assertIn('code',caught.exception.diagnostic)
        for statement in ['DB 1','NOP','DW 1','ASSET "tile"']:
            with self.assertRaises(AssemblyError):self.assemble('SECTION "ram",RAM\n'+statement)

    def test_include_escape_cycles_and_duplicate_sites(self):
        (self.tree/'one.asm').write_text('INCLUDE "two.asm"')
        (self.tree/'two.asm').write_text('INCLUDE "one.asm"')
        with self.assertRaisesRegex(AssemblyError,'include cycle') as caught:self.assemble('INCLUDE "one.asm"')
        self.assertIn('include_stack',caught.exception.diagnostic)
        for spelling in ['../outside.asm','/outside.asm','C:/outside.asm']:
            with self.assertRaises(AssemblyError):self.assemble('INCLUDE "'+spelling+'"')
        (self.tree/'one.asm').write_text('Name EQU 1')
        with self.assertRaises(AssemblyError) as caught:self.assemble('INCLUDE "one.asm"\nINCLUDE "one.asm"')
        self.assertIn('previous',caught.exception.diagnostic)

    def test_label_before_include_and_first_pass_equate_diagnostics(self):
        (self.tree/'body.asm').write_text('NOP')
        obj=self.assemble('SECTION "code",ROM\nHere: INCLUDE "body.asm"')
        self.assertEqual(obj['symbols']['Here']['expression'],{'op':'address','section':'code','offset':0})
        self.assertEqual(obj['sections'][0]['data'],[0])
        self.assertEqual(obj['listing'][0]['span']['file'],'body.asm')
        for source in ['Count EQU (1+', 'A EQU 1', 'Count EQU LOW(65536)',
                       'Count EQU 1/0', 'Count EQU 1<<64']:
            with self.subTest(source=source),self.assertRaises(AssemblyError) as caught:self.assemble(source)
            self.assertEqual(caught.exception.diagnostic['span'],{'file':'main.asm','line':1,'column':1})

    def test_bare_include_has_structured_source_diagnostic(self):
        with self.assertRaises(AssemblyError) as caught:self.assemble('INCLUDE')
        self.assertEqual(caught.exception.diagnostic['code'],'SYNTAX')
        self.assertEqual(caught.exception.diagnostic['span'],{'file':'main.asm','line':1,'column':1})

    def test_assets_and_no_section_errors(self):
        obj=self.assemble('SECTION "code",ROM\nASSET "tile"',{'tile':bytes([1,2,3])})
        self.assertEqual(obj['sections'][0]['data'],[1,2,3])
        self.assertIn('__assets__/tile',obj['sources'])
        for source in ['NOP','DB 1','Label:','SECTION "code",ROM\nASSET "missing"']:
            with self.assertRaises(AssemblyError):self.assemble(source)

    def test_object_rejects_structural_and_semantic_corruption(self):
        original=self.assemble('IMPORT External\nSECTION "code",ROM\nLD A,External')
        changes=[lambda o:o.update(extra=1),lambda o:o.update(schema_version=2),
                 lambda o:o.update(schema_version=True),lambda o:o['sections'][0]['data'].__setitem__(0,True),
                 lambda o:o['sections'][0].update(size=100),lambda o:o['relocations'][0].update(section='missing'),
                 lambda o:o['relocations'][0].update(offset=2),lambda o:o['relocations'][0].update(mask=0),
                 lambda o:o['relocations'].append(copy.deepcopy(o['relocations'][0])),
                 lambda o:o['relocations'][0]['expression'].update(op='eval'),
                 lambda o:o['relocations'][0]['span'].update(file='../private'),lambda o:o.update(imports=[]),
                 lambda o:o['listing'][0].update(size=0),lambda o:o['listing'].append(copy.deepcopy(o['listing'][0])),
                 lambda o:o['listing'][0]['span'].update(file='unhashed.asm'),
                 lambda o:o['relocations'][0].update(minimum=0,maximum=255,bias=0)]
        for change in changes:
            obj=copy.deepcopy(original);change(obj)
            with self.assertRaises(AssemblyError):validate(obj)
        for obj in [None,[],{'schema_version':1}]:
            with self.assertRaises(AssemblyError):validate(obj)

    def test_committed_schema_fixtures(self):
        fixture=ROOT/'src/sw/assembler/objects'
        validate(json.loads((fixture/'minimal.object.json').read_text()))
        with self.assertRaises(AssemblyError) as caught:
            validate(json.loads((fixture/'wrong-version.object.json').read_text()))
        self.assertEqual(caught.exception.diagnostic['code'],'SCHEMA_MISMATCH')

    def test_identical_object_bytes_across_roots(self):
        source='SECTION "code",ROM\nHere: NOP\nJR Here\n'
        first=self.assemble(source)
        other=self.tree/'other space';other.mkdir();(other/'main.asm').write_text(source)
        second=assemble(other/'main.asm',other,self.prelude)
        self.assertEqual(first,second)

    def test_builder_cache_revalidates_include_and_failure(self):
        root=self.tree/'repo space';(root/'src/sw').mkdir(parents=True)
        shutil.copytree(ROOT/'src/sw/assembler',root/'src/sw/assembler')
        shutil.copytree(ROOT/'src/sw/generated',root/'src/sw/generated')
        shutil.copytree(ROOT/'tools/sw',root/'tools/sw')
        shutil.copytree(ROOT/'tools/n2m',root/'tools/n2m')
        shutil.copytree(ROOT/'cfg',root/'cfg')
        shutil.copy2(ROOT/'src/sw/targets.json',root/'src/sw/targets.json')
        args=SimpleNamespace(target='assembler-basic',rebuild=False)
        build=root/'workdir/builds/test'
        first=assemble_target(root,build,args,{})
        self.assertEqual(first['status'],'PASS')
        second=assemble_target(root,build,args,{})
        self.assertEqual(second['cache'],'HIT')
        current=build/'sw/assemble/assembler-basic/result.json'
        tampered=json.loads(current.read_text())
        missing=root/tampered['objects'][0]
        missing.unlink()
        del tampered['artifacts'][tampered['objects'][0]]
        tampered['objects']=[]
        current.write_text(json.dumps(tampered))
        repaired=assemble_target(root,build,args,{})
        self.assertEqual((repaired['status'],repaired['cache'],len(repaired['objects'])),('PASS','MISS',1))
        registry=root/'src/sw/targets.json'
        original_registry=registry.read_text()
        changed=json.loads(original_registry)
        changed['targets']['assembler-basic']['sources']=['../outside.asm']
        registry.write_text(json.dumps(changed))
        rejected=assemble_target(root,build,args,{})
        self.assertEqual(rejected['status'],'FAIL')
        self.assertEqual(json.loads(current.read_text())['status'],'FAIL')
        registry.write_text(original_registry)
        include=root/'src/sw/assembler/basic/constants.asm'
        include.write_text(include.read_text().replace('$42','$43'))
        third=assemble_target(root,build,args,{})
        self.assertEqual(third['cache'],'MISS')
        include.write_text('MessageByte EQU 256\nBufferSize EQU 16')
        failed=assemble_target(root,build,args,{})
        self.assertEqual(failed['status'],'FAIL')
        self.assertNotIn('objects',failed)
        self.assertTrue((root/repaired['objects'][0]).exists())


if __name__=='__main__':unittest.main()
