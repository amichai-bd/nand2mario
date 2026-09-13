"""Actual-byte viewer boundaries with a fake client; no board or tunnel."""
import base64
from http.client import HTTPConnection
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from n2m import generated_interfaces as abi
from n2m.host.client import RejectedCommand
from n2m.live_viewer import Latest, capture_loop, server, PAGE
from fpga_viewer import png_writer, Stop
from n2m.viewer_buttons import Buttons, enqueue

BUILD = 'ab'*16

class Clock:
    value = 0
    def __call__(self): return self.value
    def wait(self, seconds): self.value += seconds
    def is_set(self): return False

class Fake:
    def __init__(self, clock, fault=None):
        self.clock,self.fault = clock,fault
        self.uncertain = False
        self.sequence = 0
        self.state = abi.STATE_PAUSED
        self.events = []
        self.count = 0
        self.mask = 0
    def identify(self):
        self.events.append('identify')
        return {'abi':1,'build_id':BUILD if self.fault!='identity' else '00'*16}
    def read_host(self, address):
        self.events.append(('read',address))
        return {abi.HOST_REG_IMAGE_VALID:1,abi.HOST_REG_INPUT_SOURCE:abi.INPUT_SOURCE_UART,
                abi.HOST_REG_INPUT_EFFECTIVE:self.mask,abi.HOST_REG_STATE:self.state}[address]
    def write_host(self, address, value):
        self.events.append(('write',address,value))
        if address==abi.HOST_REG_INPUT:self.mask=value
    def control(self, action):
        self.events.append(action)
        assert action in ('RUN','HALT')
        self.state = abi.STATE_RUNNING if action=='RUN' else abi.STATE_PAUSED
    def snapshot(self):
        self.events.append('snapshot')
        assert self.state==abi.STATE_RUNNING
        self.count += 1
        self.clock.value += .25
        if self.fault=='uncertain':
            self.uncertain=True
            raise RuntimeError('fake uncertainty')
        if self.fault=='rejected': raise RejectedCommand('SNAPSHOT',1)
        seq = 1 if self.fault=='duplicate' else self.count
        self.events.append('READ_FRAME_COMPLETE')
        return {'size':5760,'epoch':3,'seq':seq,'dot':seq*70224},bytes([0xe4])*5760


class ViewerTests(unittest.TestCase):
    def run_loop(self,fault=None,seconds=4):
        clock=Clock();clock.value=0
        client=Fake(clock,fault);latest=Latest(clock=clock)
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder)
            result=capture_loop(client,latest,out,png_writer,expected_build=BUILD,stop=clock,
                                clock=clock,wait=clock.wait,seconds=seconds,interval=2)
            png=(out/'capture-1.png').read_bytes() if (out/'capture-1.png').exists() else None
        return result,client,latest,png

    def test_actual_native_pixels_running_captures_and_cleanup(self):
        result,client,latest,png=self.run_loop()
        self.assertEqual((result['status'],result['capture_count']),('PASS',2))
        self.assertEqual(result['cleanup'],{'verified':True,'state':abi.STATE_PAUSED,'input_effective':0})
        self.assertEqual(client.events.count('RUN'),1)
        self.assertEqual(client.events.count('HALT'),1)
        self.assertEqual([x for x in client.events if isinstance(x,tuple) and x[0]=='write'],[('write',abi.HOST_REG_INPUT,0)])
        self.assertEqual(struct.unpack('>IIBBBBB',png[16:29]),(160,144,8,2,0,0,0))
        offset=8;compressed=b''
        while offset<len(png):
            count=int.from_bytes(png[offset:offset+4],'big');kind=png[offset+4:offset+8]
            if kind==b'IDAT':compressed+=png[offset+8:offset+8+count]
            offset+=12+count
        raw=zlib.decompress(compressed)
        expected=b'\0'+bytes([255]*3+[170]*3+[85]*3+[0]*3)*40
        self.assertEqual(raw,expected*144)
        self.assertEqual(latest.read()[0]['state'],'STOPPED')
        self.assertEqual(latest.read()[0]['core_state'],'PAUSED')

    def test_uncertainty_no_cleanup_traffic_and_identity_no_control(self):
        result,client,_,_=self.run_loop('uncertain')
        self.assertFalse(result['cleanup']['verified'])
        self.assertEqual(client.events[-1],'snapshot')
        result,client,_,_=self.run_loop('identity')
        self.assertEqual(client.events,['identify'])
        self.assertEqual(result['status'],'FAIL')

    def test_rejections_bounded_duplicate_never_refreshes(self):
        result,client,latest,_=self.run_loop('rejected',10)
        self.assertEqual(client.count,2)
        self.assertEqual(result['capture_count'],0)
        self.assertEqual(result['status'],'FAIL')
        result,client,latest,_=self.run_loop('duplicate')
        self.assertEqual(result['status'],'FAIL')
        self.assertEqual(result['capture_count'],1)
        self.assertEqual(latest.read()[0]['sequence'],1)

    def test_freshness_ages_and_history_is_bounded(self):
        clock=Clock();clock.value=0
        latest=Latest(clock=clock)
        latest.publish(b'png',{'epoch':1,'seq':1,'dot':1},.1)
        clock.value=6
        self.assertEqual(latest.read()[0]['state'],'STALE')
        latest.mark('ERROR','capture rejected')
        self.assertEqual(latest.read()[0]['age_seconds'],6)
        result,*_=self.run_loop(seconds=100)
        self.assertEqual(result['capture_count'],50)
        self.assertEqual(len(result['captures']),32)
        self.assertIn(b'age_seconds',PAGE)
        self.assertIn(b'OFFLINE / STALE',PAGE)

    def test_auth_every_read_no_control_and_loopback_only(self):
        latest=Latest();latest.publish(b'actualpng',{'epoch':1,'seq':1,'dot':1},.1)
        http=server(latest,'testuser','x'*40)
        thread=threading.Thread(target=http.serve_forever);thread.start()
        auth={'Authorization':'Basic '+base64.b64encode(b'testuser:'+b'x'*40).decode()}
        def request(path,headers=None,method='GET'):
            client=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
            client.request(method,path,headers=headers or {})
            response=client.getresponse();data=response.read();code=response.status;headers=dict(response.getheaders());client.close()
            return code,data,headers
        try:
            self.assertEqual(http.server_address[0],'127.0.0.1')
            for path in ('/','/status.json','/frame.png','/file','/control'):
                self.assertEqual(request(path)[0],401)
            self.assertEqual(request('/frame.png',auth)[:2],(200,b'actualpng'))
            old=json.loads(request('/status.json',auth)[1])
            latest.publish(b'newpng',{'epoch':1,'seq':2,'dot':2},.1)
            self.assertEqual(request('/frame.png?v='+str(old['sequence']),auth)[0],409)
            self.assertEqual(request('/frame.png?v=2',auth)[:2],(200,b'newpng'))
            self.assertEqual(request('/file',auth)[0],404)
            self.assertEqual(request('/control',auth,'POST')[0],405)
            self.assertEqual(request('/frame.png',auth)[2]['Cache-Control'],'no-store, max-age=0')
        finally:
            http.shutdown();http.server_close();thread.join()

    def test_phone_input_auth_origin_body_and_queue(self):
        with tempfile.TemporaryDirectory() as folder:
            out=Path(folder);(out/'service.json').write_text('{}')
            origin='https://example.test'
            http=server(Latest(),'testuser','x'*40,input_origin=origin,
                        submit=lambda mask,ms:enqueue(out,mask,ms))
            thread=threading.Thread(target=http.serve_forever);thread.start()
            headers={'Authorization':'Basic '+base64.b64encode(b'testuser:'+b'x'*40).decode(),
                     'Origin':origin,'Content-Type':'application/json','X-Viewer-Input':'tap'}
            def request(body=b'{"button":"Right"}',override=None,method='POST'):
                h=dict(headers);h.update(override or {})
                h={k:v for k,v in h.items() if v is not None}
                client=HTTPConnection('127.0.0.1',http.server_port,timeout=2)
                client.request(method,'/input',body=body,headers=h)
                r=client.getresponse();data=r.read();code=r.status;client.close();return code,data
            try:
                self.assertEqual(request(override={'Authorization':None})[0],401)
                for h in ({'Origin':None},{'Origin':'https://evil.test'},{'X-Viewer-Input':None}):
                    self.assertEqual(request(override=h)[0],403)
                self.assertEqual(request(override={'Content-Type':'text/plain'})[0],415)
                self.assertEqual(request(b'x'*65)[0],413)
                for body in (b'{}',b'bad',b'{"button":"RESET"}',b'{"button":"Right","mask":255}'):
                    self.assertEqual(request(body)[0],400)
                self.assertEqual(request(method='GET')[0],404)
                self.assertFalse((out/'inbox').exists())
                for index in range(1,17):
                    code,data=request();self.assertEqual(code,202)
                    self.assertEqual(json.loads(data)['id'],index)
                self.assertEqual(request()[0],409)
                records=[json.loads(p.read_text()) for p in (out/'inbox').glob('*.json')]
                self.assertTrue(all(r['mask']==abi.BUTTON_RIGHT and r['milliseconds']==134 for r in records))
                self.assertIn(b"['Up','Left','Right','Down','A','B','Start','Select']",PAGE)
            finally:
                http.shutdown();http.server_close();thread.join()

class ButtonQueueTests(unittest.TestCase):
    def runtime(self, folder):
        out=Path(folder);(out/'service.json').write_text('{}')
        return out

    def test_fifo_capacity_invalid_and_claimed_never_replayed(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder)
            for value in (0,256,True):
                with self.assertRaises(ValueError):enqueue(out,value,134)
            for duration in (0,1001,True):
                with self.assertRaises(ValueError):enqueue(out,1,duration)
            ids=[enqueue(out,1,134) for _ in range(16)]
            self.assertEqual(ids,list(range(1,17)))
            with self.assertRaises(ValueError):enqueue(out,1,134)
            first=out/'inbox'/f'{1:020d}.json'
            first.rename(first.with_suffix('.claimed'))
            clock=Clock();clock.value=0;client=Fake(clock)
            receipt=Buttons(out).one(client,clock,clock=clock,wait=clock.wait)
            self.assertEqual(receipt['id'],2)
            self.assertTrue(first.with_suffix('.claimed').exists())
            self.assertTrue(receipt['released'])
            self.assertEqual(client.mask,0)

    def test_frozen_batch_before_capture_and_release_each(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);enqueue(out,2,1000)
            clock=Clock();clock.value=0;client=Fake(clock)
            r=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                           stop=clock,seconds=4,interval=2,clock=clock,wait=clock.wait,buttons=Buttons(out))
            self.assertEqual(r['status'],'PASS')
            self.assertEqual([x['id'] for x in r['inputs']],[1,2])
            relevant=[x for x in client.events if x in ('snapshot','READ_FRAME_COMPLETE') or isinstance(x,tuple) and x[0]=='write']
            self.assertEqual(relevant,[
                ('write',abi.HOST_REG_INPUT,1),('write',abi.HOST_REG_INPUT,0),
                ('write',abi.HOST_REG_INPUT,2),('write',abi.HOST_REG_INPUT,0),
                'snapshot','READ_FRAME_COMPLETE','snapshot','READ_FRAME_COMPLETE',
                ('write',abi.HOST_REG_INPUT,0)])

    def test_invalid_record_no_input_and_stop_releases(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            path=next((out/'inbox').glob('*.json'));path.write_text('{"opcode":"RESET"}')
            clock=Clock();clock.value=0;client=Fake(clock)
            receipt=Buttons(out).one(client,clock,clock=clock,wait=clock.wait)
            self.assertEqual(receipt['status'],'REJECTED');self.assertEqual(client.events,[])
            enqueue(out,1,134)
            stop=threading.Event()
            receipt=Buttons(out).one(client,stop,clock=clock,wait=lambda _:stop.set())
            self.assertEqual(receipt['status'],'CANCELLED');self.assertTrue(receipt['released']);self.assertEqual(client.mask,0)
            (out/'STOP').write_text('stop')
            with self.assertRaises(ValueError):enqueue(out,1,134)

    def test_arrival_during_batch_waits_until_next_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            clock=Clock();clock.value=0;client=Fake(clock);published=False
            def wait(seconds):
                nonlocal published
                if not published:
                    enqueue(out,2,134);published=True
                clock.wait(seconds)
            capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                         stop=clock,seconds=4,interval=2,clock=clock,wait=wait,buttons=Buttons(out))
            events=client.events
            self.assertLess(events.index(('write',abi.HOST_REG_INPUT,1)),events.index('snapshot'))
            self.assertGreater(events.index(('write',abi.HOST_REG_INPUT,2)),events.index('READ_FRAME_COMPLETE'))

    def test_batch_enumeration_holds_producer_lock(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            original=Path.glob
            def checked(path,pattern):
                if path==out/'inbox':
                    self.assertTrue((path/'producer.lock').exists())
                    with self.assertRaises(FileExistsError):enqueue(out,2,134)
                return original(path,pattern)
            with patch.object(Path,'glob',checked):
                self.assertEqual(len(Buttons(out).batch()),1)
            self.assertEqual(enqueue(out,2,134),2)

    def test_shutdown_closes_admission_and_cancels_pending(self):
        from unittest.mock import patch
        import n2m.viewer_buttons as module
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134);enqueue(out,2,134)
            cancelled=Buttons(out).close()
            self.assertEqual([r['id'] for r in cancelled],[1,2])
            self.assertTrue(all(r['status']=='CANCELLED' for r in cancelled))
            self.assertFalse(list((out/'inbox').glob('*.json')))
            with self.assertRaises(ValueError):enqueue(out,1,134)
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);real_open=module.os.open
            def stop_before_lock(*args,**kwargs):
                (out/'STOP').write_text('stop')
                return real_open(*args,**kwargs)
            with patch.object(module.os,'open',stop_before_lock):
                with self.assertRaises(ValueError):enqueue(out,1,134)
            self.assertFalse(list((out/'inbox').glob('*.json')))

    def test_stop_file_interrupts_wait(self):
        import time
        with tempfile.TemporaryDirectory() as folder:
            stop=Stop(Path(folder)/'STOP')
            timer=threading.Timer(.03,stop.path.touch);timer.start()
            started=time.monotonic()
            self.assertTrue(stop.wait(1))
            self.assertLess(time.monotonic()-started,.3)
            timer.join()

    def test_uncertain_press_stops_capture_without_further_traffic(self):
        class Broken(Fake):
            def write_host(self,address,value):
                super().write_host(address,value)
                if value:
                    self.uncertain=True
                    raise RuntimeError('uncertain input')
        with tempfile.TemporaryDirectory() as folder:
            out=self.runtime(folder);enqueue(out,1,134)
            clock=Clock();clock.value=0;client=Broken(clock)
            r=capture_loop(client,Latest(clock=clock),out,png_writer,expected_build=BUILD,
                           stop=clock,seconds=4,clock=clock,wait=clock.wait,buttons=Buttons(out))
            self.assertEqual(r['status'],'FAIL');self.assertFalse(r['cleanup']['verified'])
            self.assertEqual(client.events[-1],('write',abi.HOST_REG_INPUT,1))
            self.assertEqual(client.count,0)
            self.assertFalse(list((out/'inbox').glob('*.json')))

if __name__=='__main__':unittest.main()
