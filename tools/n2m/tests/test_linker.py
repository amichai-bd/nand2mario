"""Independent placement, relocation and cartridge checks from owned fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import json
import shutil
from types import SimpleNamespace
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sw.assembler import assemble
from sw.expressions import AssemblyError
from sw.linker import link
from sw.package import package, validate_image
from sw.rom_build import build_target
ROOT = Path(__file__).resolve().parents[3]

class LinkerTests(unittest.TestCase):
    def setUp(self):
        parent = ROOT / 'workdir/builds/linker-unit'; parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='space ', dir=parent)
        self.addCleanup(self.temp.cleanup); self.tree = Path(self.temp.name)
    def obj(self, name, source):
        path = self.tree / name; path.write_text(source, encoding='utf-8')
        return (name, assemble(path, self.tree, ROOT / 'src/sw/generated/interfaces.inc'))
    def fixture(self):
        objects = [self.obj('main.asm', 'IMPORT Other\nSECTION "code",ROM\nStart: LD HL,Other\nJR After\nDB $ff\nAfter: CALL Other\nEXPORT Start\nSECTION "work",RAM\nBuffer: DS 16\n'),
                   self.obj('other.asm', 'SECTION "code",ROM\nOther: RET\nEXPORT Other\n')]
        layout = {'schema_version': 1, 'sections': [
            {'unit': 'main.asm', 'section': 'code', 'region': 'ROM0', 'address': 512},
            {'unit': 'main.asm', 'section': 'work', 'region': 'WRAM', 'alignment': 16},
            {'unit': 'other.asm', 'section': 'code', 'region': 'ROM1'}]}
        return objects, layout, {'unit': 'main.asm', 'symbol': 'Start'}
    def test_cross_unit_and_header_independent_arithmetic(self):
        objects, layout, entry = self.fixture(); linked = link(objects, layout, entry)
        self.assertEqual(linked['image'][512:521], bytes([0x21,0,0x40,0x18,1,0xff,0xcd,0,0x40]))
        self.assertEqual(linked['image'][0x4000], 0xc9)
        self.assertEqual(next(s for s in linked['map']['sections'] if s['kind']=='RAM')['file_offset'], None)
        rom = package(linked, 'OWNED DEMO', 7)
        self.assertEqual(len(rom),32768)
        self.assertEqual(rom[256:260],bytes([0,0xc3,0,2]))
        self.assertEqual(rom[260:308],bytes(48))
        self.assertEqual(rom[308:324],b'OWNED DEMO'+bytes(6))
        checksum=0
        for value in rom[308:333]: checksum=(checksum-value-1)%256
        self.assertEqual(rom[333],checksum)
        total=0
        for offset,value in enumerate(rom):
            if offset not in (334,335): total=(total+value)%65536
        self.assertEqual(rom[334]*256+rom[335],total)
        for offset,code in [(333,'HEADER_CHECKSUM'),(600,'GLOBAL_CHECKSUM'),(260,'METADATA')]:
            damaged=bytearray(rom);damaged[offset]^=1
            with self.subTest(code=code),self.assertRaises(AssemblyError) as raised: validate_image(damaged,512,'OWNED DEMO',7)
            self.assertEqual(raised.exception.diagnostic['code'],code)
    def test_reservations_fixed_first_and_empty(self):
        objects=[self.obj('main.asm','SECTION "float",ROM\nStart: NOP\nSECTION "fixed",ROM\nNOP\nSECTION "empty",ROM\n')]
        rows=[{'unit':'main.asm','section':'float','region':'ROM0'},
              {'unit':'main.asm','section':'fixed','region':'ROM0','address':104},
              {'unit':'main.asm','section':'empty','region':'ROM0','address':256}]
        result=link(objects,{'schema_version':1,'sections':rows},{'unit':'main.asm','symbol':'Start'})
        values={s['section']:s['address'] for s in result['map']['sections']}
        self.assertEqual(values,{'fixed':104,'float':105,'empty':256})
    def test_entry_data_and_reservations_fail(self):
        for source,address in [('Data: DB 0',512),('Data: NOP',0),('Data: NOP',256)]:
            obj=self.obj('main.asm','SECTION "code",ROM\n'+source+'\n')
            with self.subTest(source=source,address=address),self.assertRaises(AssemblyError):
                link([obj],{'schema_version':1,'sections':[{'unit':'main.asm','section':'code','region':'ROM0','address':address}]},{'unit':'main.asm','symbol':'Data'})
    def test_import_duplicate_cycle_overlap_and_boundary_fail(self):
        objects,layout,entry=self.fixture()
        for mutate,code in [
            (lambda o,l:o[1][1]['exports'].clear(),'UNDEFINED_SYMBOL'),
            (lambda o,l:l['sections'][0].update(address=0x3ffc),'OVERFLOW'),
            (lambda o,l:l['sections'][2].update(region='ROM0',address=512),'OVERLAP'),
            (lambda o,l:l['sections'][0].update(alignment=3),'ALIGNMENT'),
            (lambda o,l:l['sections'].pop(),'LAYOUT_SECTION')]:
            a,b=deepcopy(objects),deepcopy(layout);mutate(a,b)
            with self.subTest(code=code),self.assertRaises(AssemblyError) as raised:link(a,b,entry)
            self.assertEqual(raised.exception.diagnostic['code'],code)
        a=self.obj('a.asm','IMPORT Bee\nAye EQU Bee\nEXPORT Aye\nSECTION "c",ROM\nStart: NOP\n')
        b=self.obj('b.asm','IMPORT Aye\nBee EQU Aye\nEXPORT Bee\n')
        with self.assertRaises(AssemblyError) as raised:
            link([a,b],{'schema_version':1,'sections':[{'unit':'a.asm','section':'c','region':'ROM0','address':512}]},{'unit':'a.asm','symbol':'Start'})
        self.assertEqual(raised.exception.diagnostic['code'],'CYCLIC_SYMBOL')

    def test_relative_limits_and_unresolved_operand_constraints(self):
        for distance in [-129,-128,127,128]:
            text=f'IMPORT Destination\nSECTION "code",ROM\nStart: JR Destination\n'
            a=self.obj('a.asm',text)
            b=self.obj('b.asm',f'Destination EQU {514+distance}\nEXPORT Destination\n')
            layout={'schema_version':1,'sections':[{'unit':'a.asm','section':'code','region':'ROM0','address':512}]}
            if distance in [-128,127]:
                result=link([a,b],layout,{'unit':'a.asm','symbol':'Start'})
                self.assertEqual(result['image'][513],distance%256)
            else:
                with self.assertRaises(AssemblyError) as raised:link([a,b],layout,{'unit':'a.asm','symbol':'Start'})
                self.assertEqual(raised.exception.diagnostic['code'],'RANGE')
        for instruction,values in [('BIT Value,A',[-1,0,7,8]),('RST Value',[-1,0,8,56,57]),('LDH A,[Value]',[65279,65280,65535,65536])]:
            for value in values:
                a=self.obj('a.asm','IMPORT Value\nSECTION "code",ROM\nStart: '+instruction+'\n')
                b=self.obj('b.asm',f'Value EQU {value}\nEXPORT Value\n')
                valid=(0<=value<=7 if instruction.startswith('BIT') else value in range(0,57,8) if instruction.startswith('RST') else 65280<=value<=65535)
                if valid:link([a,b],layout,{'unit':'a.asm','symbol':'Start'})
                else:
                    with self.subTest(instruction=instruction,value=value),self.assertRaises(AssemblyError) as raised:link([a,b],layout,{'unit':'a.asm','symbol':'Start'})
                    self.assertEqual(raised.exception.diagnostic['code'],'RANGE')

    def test_named_vector_bank_exhaustion_and_unit_local_symbols(self):
        a=self.obj('a.asm','SECTION "vector",ROM\nNOP\nSECTION "code",ROM\nLocal: NOP\n')
        b=self.obj('b.asm','SECTION "code",ROM\nLocal: RET\n')
        rows=[{'unit':'a.asm','section':'vector','region':'ROM0','vector':'RST_00'},
              {'unit':'a.asm','section':'code','region':'ROM0','address':512},
              {'unit':'b.asm','section':'code','region':'ROM1','address':32767}]
        result=link([a,b],{'schema_version':1,'sections':rows},{'unit':'a.asm','symbol':'Local'})
        self.assertEqual(result['image'][0],0);self.assertEqual(result['image'][32767],201)
        symbols={s['name']:s['value'] for s in result['symbols']['symbols']}
        self.assertEqual(symbols['a.asm::Local'],512);self.assertEqual(symbols['b.asm::Local'],32767)
        a[1]['exports']=['Local'];b[1]['exports']=['Local']
        with self.assertRaises(AssemblyError) as raised:link([a,b],{'schema_version':1,'sections':rows},{'unit':'a.asm','symbol':'Local'})
        self.assertEqual(raised.exception.diagnostic['code'],'DUPLICATE_SYMBOL')
        huge=self.obj('huge.asm','SECTION "full",ROM\nStart: NOP\nDB '+','.join(['0']*16383)+'\nSECTION "extra",ROM\nNOP\n')
        rows=[{'unit':'huge.asm','section':name,'region':'ROM1'} for name in ['full','extra']]
        with self.assertRaises(AssemblyError) as raised:link([huge],{'schema_version':1,'sections':rows},{'unit':'huge.asm','symbol':'Start'})
        self.assertEqual(raised.exception.diagnostic['code'],'EXHAUSTION')

    def test_malformed_object_layout_and_profile_metadata(self):
        objects,layout,entry=self.fixture()
        broken=deepcopy(objects);broken[0][1]['schema_version']=2
        with self.assertRaises(AssemblyError) as raised:link(broken,layout,entry)
        self.assertEqual(raised.exception.diagnostic['code'],'SCHEMA_MISMATCH')
        for field,value in [('extra',1),('schema_version',True)]:
            bad={**layout,field:value}
            with self.assertRaises(AssemblyError):link(objects,bad,entry)
        with self.assertRaises(AssemblyError) as raised:link(objects,layout,entry,'stock-boot')
        self.assertEqual(raised.exception.diagnostic['code'],'PROFILE_MISMATCH')
        linked=link(objects,layout,entry)
        for title,version in [('',0),('lower',0),('TOO LONG FOR TITLE',0),('OK',True),('OK',256),('OK',-1)]:
            with self.subTest(title=title,version=version),self.assertRaises(AssemblyError):package(linked,title,version)
        with self.assertRaises(AssemblyError):package(linked,'OK',0,'unknown')

    def checkout(self,name):
        root=self.tree/name
        for part in ['tools','src/sw','cfg']:
            shutil.copytree(ROOT/part,root/part,ignore=shutil.ignore_patterns('__pycache__'))
        return root

    def test_stage_determinism_cache_inventory_and_failure_diagnostics(self):
        first=self.checkout('checkout one');second=self.checkout('checkout two')
        args=SimpleNamespace(target='linker-basic',rebuild=False)
        results=[]
        for root,tag in [(first,'fresh-a'),(first,'fresh-b'),(second,'other-path')]:
            build=root/'workdir/builds'/tag;build.mkdir(parents=True)
            report=build_target(root,build,args,{'commit':'test'})
            self.assertEqual(report['status'],'PASS',report)
            results.append({Path(name).name:(root/name).read_bytes() for name in report['artifacts']})
            self.assertEqual(build_target(root,build,args,{'commit':'test'})['cache'],'HIT')
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0],results[2])
        build=first/'workdir/builds/fresh-a';stage=build/'sw/build/linker-basic';current=stage/'result.json'
        prior=json.loads(current.read_text());rom=first/prior['rom'];rom.write_bytes(b'corrupt')
        self.assertEqual(build_target(first,build,args,{})['cache'],'MISS')
        prior=json.loads(current.read_text());prior['artifacts'].pop(prior['rom']);current.write_text(json.dumps(prior))
        self.assertEqual(build_target(first,build,args,{})['cache'],'MISS')
        source=first/'src/sw/linker/basic/main.asm';source.write_text('SECTION "code",ROM\nLD A,256\n')
        failed=build_target(first,build,args,{})
        self.assertEqual(failed['status'],'FAIL');self.assertNotIn('rom',failed)
        diagnostic=json.loads((first/next(iter(failed['artifacts']))).read_text())[0]
        self.assertEqual((diagnostic['code'],diagnostic['stage'],diagnostic['span']['file'],diagnostic['span']['line']),('RANGE','assemble','main.asm',2))
        self.assertEqual(json.loads(current.read_text())['status'],'FAIL')

    def test_changed_layout_include_and_generated_inputs(self):
        root=self.checkout('dependencies');build=root/'workdir/builds/a';build.mkdir(parents=True)
        args=SimpleNamespace(target='linker-basic',rebuild=False)
        first=build_target(root,build,args,{})
        source=root/'src/sw/linker/basic/main.asm';source.write_text('INCLUDE "constant.inc"\n'+source.read_text())
        include=source.with_name('constant.inc');include.write_text('Owned EQU 1\n')
        changed=build_target(root,build,args,{})
        self.assertEqual(changed['cache'],'MISS');self.assertNotEqual(first['fingerprint'],changed['fingerprint'])
        include.write_text('Owned EQU 2\n');self.assertEqual(build_target(root,build,args,{})['cache'],'MISS')
        layout=source.with_name('layout.json');data=json.loads(layout.read_text());data['sections'][0]['address']=768;layout.write_text(json.dumps(data))
        changed=build_target(root,build,args,{});self.assertEqual(changed['cache'],'MISS');self.assertEqual(changed['entry'],768)
        prelude=root/'src/sw/generated/interfaces.inc';prelude.write_text(prelude.read_text()+'Stale EQU 1\n')
        failed=build_target(root,build,args,{});self.assertEqual(failed['status'],'FAIL');self.assertIn('stale',failed['error'])

if __name__ == '__main__': unittest.main()
