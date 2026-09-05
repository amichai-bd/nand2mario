"""Independent placement, relocation and cartridge checks from owned fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sw.assembler import assemble
from sw.expressions import AssemblyError
from sw.linker import link
from sw.package import package, validate_image
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

if __name__ == '__main__': unittest.main()
