"""Original shade validation, independent decoding and full stage failure contracts."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sw.assets import encode_shades, load_shades, validate_shades
from sw.asset_conformance import decode_tiles, compare_pixels, proof
from sw.expressions import AssemblyError
from sw.build import assemble_target
from sw.rom_build import build_target
ROOT=Path(__file__).resolve().parents[3]

class AssetTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'workdir/builds/asset-unit';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='space ',dir=parent);self.addCleanup(self.temp.cleanup)
        self.tree=Path(self.temp.name)
        self.fixture=json.loads((ROOT/'src/sw/assets/original-pattern/shades.json').read_text())
    def checkout(self,name):
        root=self.tree/name
        for part in ['tools','src/sw','cfg']:shutil.copytree(ROOT/part,root/part,ignore=shutil.ignore_patterns('__pycache__'))
        return root
    def test_every_shade_position_tile_and_duplicate(self):
        encoded=encode_shades(self.fixture)
        self.assertEqual(encoded[:4],bytes([0x55,0x33,0x55,0xcc]))
        self.assertEqual(encoded[16:18],bytes([0xaa,0x66]))
        self.assertEqual(encoded[:64],encoded[64:]);self.assertEqual(len(encoded),128)
        decoded=decode_tiles(encoded,32,16);self.assertEqual(decoded,self.fixture['pixels'])
        coverage={(x%8,y%8,v) for y,row in enumerate(decoded) for x,v in enumerate(row)}
        self.assertEqual(len(coverage),256)
        for width,height in [(8,8),(8,24),(24,8),(16,24)]:
            value={'schema_version':1,'width':width,'height':height,'pixels':[[(x+3*y)%4 for x in range(width)] for y in range(height)]}
            self.assertEqual(decode_tiles(encode_shades(value),width,height),value['pixels'])
    def test_strict_shape_dimension_and_pixel_rejections(self):
        cases=[]
        for field in ['width','height']:
            for value in [0,-8,1,7,9,True,False,8.0,'8',None]:cases.append(({**self.fixture,field:value},'ASSET_DIMENSIONS'))
        for value in [True,1.0,2,None]:cases.append(({**self.fixture,'schema_version':value},'ASSET_SCHEMA'))
        cases.extend([(None,'ASSET_SCHEMA'),([], 'ASSET_SCHEMA'),({**self.fixture,'extra':0},'ASSET_SCHEMA')])
        for rows in [[],[[]],self.fixture['pixels'][:-1],None]:cases.append(({**self.fixture,'pixels':rows},'ASSET_PIXELS'))
        for value in [True,False,0.0,-1,4,'0',None]:
            data=deepcopy(self.fixture);data['pixels'][0][0]=value;cases.append((data,'ASSET_PIXELS'))
        for data,code in cases:
            with self.subTest(code=code),self.assertRaises(AssemblyError) as raised:validate_shades(data,'shades.json')
            self.assertEqual(raised.exception.diagnostic['code'],code)
            self.assertEqual(raised.exception.diagnostic['span']['file'],'shades.json')
        path=self.tree/'invalid.json'
        for source in ['{','{"width":8,"width":16}','\ufeff{}']:
            path.write_text(source,encoding='utf-8')
            with self.assertRaises(AssemblyError) as raised:load_shades(path,'invalid.json')
            self.assertEqual(raised.exception.diagnostic['code'],'ASSET_JSON')
    def test_actual_proof_mutations_and_undeclared_asset(self):
        root=self.checkout('proof');build=root/'workdir/builds/a';build.mkdir(parents=True)
        good=proof(root,build,SimpleNamespace(mutate=None),{})
        self.assertEqual(good['status'],'PASS',good);self.assertEqual(good['local_pixel_shade_bins'],256)
        for mutation in ['planes','bitorder']:
            failed=proof(root,build,SimpleNamespace(mutate=mutation),{})
            self.assertEqual(failed['status'],'FAIL');self.assertTrue(failed['error'].startswith('asset pixel mismatch'))
            self.assertTrue(any(n.endswith('actual.2bpp') for n in failed['artifacts']))
        source=root/'src/sw/assets/original-pattern/main.asm';source.write_text(source.read_text().replace('"Pattern"','"Undeclared"'))
        failed=build_target(root,build,SimpleNamespace(target='assets-basic',rebuild=False),{})
        self.assertEqual(failed['status'],'FAIL');self.assertNotIn('rom',failed)
        diagnostic=json.loads((root/next(iter(failed['artifacts']))).read_text())[0]
        self.assertEqual(diagnostic['span']['file'],'main.asm');self.assertEqual(diagnostic['span']['line'],4)
    def test_asset_cache_inventory_missing_corrupt_and_changed_source(self):
        root=self.checkout('cache');build=root/'workdir/builds/a';build.mkdir(parents=True)
        args=SimpleNamespace(target='assets-basic',rebuild=False)
        first=build_target(root,build,args,{})
        self.assertEqual(first['status'],'PASS');self.assertEqual(build_target(root,build,args,{})['cache'],'HIT')
        assembly=build/'sw/assemble/assets-basic/result.json'
        record=json.loads(assembly.read_text());binary=root/record['asset_outputs']['asset-Pattern.2bpp'];binary.write_bytes(b'bad')
        rebuilt=assemble_target(root,build,args,{})
        self.assertEqual(rebuilt['cache'],'MISS');self.assertEqual((root/rebuilt['asset_outputs']['asset-Pattern.2bpp']).read_bytes(),encode_shades(self.fixture))
        (root/rebuilt['asset_outputs']['asset-Pattern.2bpp']).unlink()
        self.assertEqual(assemble_target(root,build,args,{})['cache'],'MISS')
        asset=root/'src/sw/assets/original-pattern/shades.json';data=json.loads(asset.read_text());data['pixels'][0][0]=3;asset.write_text(json.dumps(data))
        changed=build_target(root,build,args,{})
        self.assertEqual(changed['cache'],'MISS');self.assertNotEqual(changed['fingerprint'],first['fingerprint'])
        self.assertNotEqual((root/changed['rom']).read_bytes(),(root/first['rom']).read_bytes())
        data['width']=True;asset.write_text(json.dumps(data));failed=build_target(root,build,args,{})
        self.assertEqual(failed['status'],'FAIL');self.assertNotIn('rom',failed)
        self.assertEqual(json.loads((build/'sw/assemble/assets-basic/result.json').read_text())['status'],'FAIL')
        self.assertEqual(json.loads((build/'sw/build/assets-basic/result.json').read_text())['status'],'FAIL')
    def test_registry_migration_authorship_and_deterministic_clean_builds(self):
        first=self.checkout('first');second=self.checkout('second');outputs=[]
        args=SimpleNamespace(target='assets-basic',rebuild=False)
        for root,tag in [(first,'a'),(first,'b'),(second,'c')]:
            build=root/'workdir/builds'/tag;build.mkdir(parents=True)
            report=build_target(root,build,args,{});self.assertEqual(report['status'],'PASS',report)
            outputs.append({Path(n).name:(root/n).read_bytes() for n in report['artifacts']})
        self.assertEqual(outputs[0],outputs[1]);self.assertEqual(outputs[0],outputs[2])
        registry=first/'src/sw/targets.json';data=json.loads(registry.read_text());original=deepcopy(data)
        build=first/'workdir/builds/a'
        data['schema_version']=1;registry.write_text(json.dumps(data))
        self.assertEqual(build_target(first,build,args,{})['status'],'FAIL')
        self.assertEqual(assemble_target(first,build,args,{})['status'],'FAIL')
        for declaration in ['old/generated.bin',{'source':'shades.json','author':''},{'source':'../escape.json','author':'Original'},{'source':'shades.json','author':'Original','extra':1}]:
            data=deepcopy(original);data['targets']['assets-basic']['assets']['Pattern']=declaration;registry.write_text(json.dumps(data))
            self.assertEqual(build_target(first,build,args,{})['status'],'FAIL')

if __name__=='__main__':unittest.main()
