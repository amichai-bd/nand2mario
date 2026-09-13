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
from fpga_viewer import png_writer

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
    def identify(self):
        self.events.append('identify')
        return {'abi':1,'build_id':BUILD if self.fault!='identity' else '00'*16}
    def read_host(self, address):
        self.events.append(('read',address))
        return {abi.HOST_REG_IMAGE_VALID:1,abi.HOST_REG_INPUT_SOURCE:abi.INPUT_SOURCE_UART,
                abi.HOST_REG_INPUT_EFFECTIVE:0,abi.HOST_REG_STATE:self.state}[address]
    def write_host(self, address, value):
        self.events.append(('write',address,value))
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

if __name__=='__main__':unittest.main()
