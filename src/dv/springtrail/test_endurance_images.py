"""Synthetic export/protocol fixtures, never labelled as board acceptance."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from types import SimpleNamespace
from endurance_images import export, publish, verify_publication, SELECTED

class Images(unittest.TestCase):
    def fixture(self, out):
        (out/'run').mkdir()
        rows=[]
        for n,name in enumerate(SELECTED):
            packed=bytes((i+n)%256 for i in range(5760))
            (out/'run'/(name+'.2bpp')).write_bytes(packed)
            rows.append(dict(name=name,file=name+'.2bpp',sha256=hashlib.sha256(packed).hexdigest(),
                             checked_pixels=23040,metadata=dict(seq=n+1,dot=123+n,epoch=9)))
        (out/'run/result.json').write_text(json.dumps(dict(status='PASS',rom_sha256='a'*64,samples=rows)),encoding='utf-8')

    def test_native_palette_pixels_and_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);self.fixture(out);manifest=export(out)
            self.assertEqual(len(manifest['images']),3)
            for row in manifest['images']:
                data=(out/row['file']).read_bytes();self.assertEqual(data[:8],b'\x89PNG\r\n\x1a\n')
                chunks={};i=8
                while i<len(data):
                    size=int.from_bytes(data[i:i+4],'big');kind=data[i+4:i+8];body=data[i+8:i+8+size]
                    self.assertEqual(int.from_bytes(data[i+8+size:i+12+size],'big'),zlib.crc32(kind+body)&0xffffffff)
                    chunks[kind]=body;i+=12+size
                self.assertEqual(struct.unpack('>IIBBBBB',chunks[b'IHDR']),(160,144,2,3,0,0,0))
                self.assertEqual(chunks[b'PLTE'],bytes.fromhex('ffffffd0d0d0686868181818'))
                raw=zlib.decompress(chunks[b'IDAT']);pixels=[]
                for y in range(144):
                    self.assertEqual(raw[y*41],0)
                    for value in raw[y*41+1:(y+1)*41]:
                        pixels.extend((value>>shift)&3 for shift in (6,4,2,0))
                packed=(out/'run'/(row['name']+'.2bpp')).read_bytes()
                self.assertEqual(pixels,[(v>>shift)&3 for v in packed for shift in (0,2,4,6)])
                self.assertEqual(row['sha256'],hashlib.sha256(data).hexdigest())
                self.assertNotIn('port',json.dumps(row))

    def test_corruption_and_failed_run_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);self.fixture(out)
            path=out/'run/origin-title.2bpp';path.write_bytes(bytes(5760))
            with self.assertRaisesRegex(AssertionError,'ENDURANCE_IMAGE_HASH'):export(out)
            r=out/'run/result.json';result=json.loads(r.read_text());result['status']='FAIL';r.write_text(json.dumps(result))
            with self.assertRaisesRegex(AssertionError,'ENDURANCE_IMAGE_RUN'):export(out)

    def test_publication_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);self.fixture(out);export(out)
            calls=[]
            def fail(command,**kwargs):
                calls.append(command);return SimpleNamespace(returncode=1,stdout='',stderr='upload refused')
            with self.assertRaisesRegex(RuntimeError,'ENDURANCE_ATTACHMENT_UPLOAD'):
                publish(out,'gh',525,execute=fail)
            self.assertEqual(calls[0].count('--attach'),3)
            self.assertEqual(json.loads((out/'publication.json').read_text())['status'],'FAIL')
            def okay(*args,**kwargs):return SimpleNamespace(returncode=0,stdout='https://github.com/o/r/pull/1#issuecomment-2',stderr='')
            self.assertEqual(publish(out,'gh',525,execute=okay)['status'],'UPLOADED_UNVERIFIED')
            # Upload alone cannot claim verified durable attachment content.

    def test_durable_downloaded_attachments_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);self.fixture(out);manifest=export(out)
            okay=lambda *a,**k:SimpleNamespace(returncode=0,stdout='comment',stderr='')
            publish(out,'gh',525,execute=okay)
            urls=['https://github.com/user-attachments/assets/'+str(i) for i in range(3)]
            data=[(out/r['file']).read_bytes() for r in manifest['images']]
            with self.assertRaisesRegex(AssertionError,'ENDURANCE_ATTACHMENT_HASH'):
                verify_publication(out,urls,[b'bad',*data[1:]])
            self.assertEqual(json.loads((out/'publication.json').read_text())['status'],'UPLOADED_UNVERIFIED')
            with self.assertRaisesRegex(AssertionError,'ENDURANCE_ATTACHMENT_URL'):
                verify_publication(out,[urls[0]+'?expires=1',*urls[1:]],data)
            self.assertEqual(verify_publication(out,urls,data)['status'],'PASS')


class WholeBudget(unittest.TestCase):
    def test_parent_supervises_build_and_export_in_worker(self):
        from unittest.mock import patch
        import endurance
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(endurance,'ROOT',Path(directory)), patch.object(endurance.sys,'argv',
                    ['endurance.py','routine','--uart-port','unit','--expected-build-id','0'*32]), \
                 patch.object(endurance,'build_rom',side_effect=AssertionError('build escaped worker')), \
                 patch.object(endurance,'decode',side_effect=AssertionError('export escaped worker')), \
                 patch.object(endurance,'supervise',return_value=0) as supervisor:
                self.assertEqual(endurance.main(),0)
            command,cap,out=supervisor.call_args.args
            self.assertEqual(cap,780)
            self.assertIn('--worker',command)
            self.assertEqual(command[command.index('--deadline')+1],'756')
            self.assertNotIn('--rom',command)

    def test_exhausted_build_budget_never_opens_hardware(self):
        from unittest.mock import patch
        import endurance
        import ci.storage
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);rom=out/'game.gb';rom.write_bytes(bytes(32768))
            args=SimpleNamespace(out=str(out),tag='unit-budget479-'+out.name,plan='routine',
                                 uart_port='unit',deadline=756)
            with patch.object(endurance,'build_rom',return_value=(rom,hashlib.sha256(rom.read_bytes()).hexdigest(),'unit')), \
                 patch.object(endurance.time,'monotonic',side_effect=[0,800,801]), \
                 patch.object(ci.storage,'machine_lock') as lock:
                self.assertEqual(endurance.worker(args),1)
                lock.assert_not_called()
            record=json.loads((out/'session.json').read_text())
            self.assertEqual(record['status'],'FAIL')
            self.assertIn('ENDURANCE_WALL_CAP build',record['error'])
