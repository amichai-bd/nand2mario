"""Host control-flow checks only; synthetic frames are not DUT evidence."""
import sys,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from n2m import generated_interfaces as abi
import physical_driver as driver
from physical_reference import LCD,PERIOD,expected_snapshot


class Endpoint:
    def __init__(self,fault=False):
        self.dot=0;self.running=False;self.mask=0;self.events=[]
        self.uncertain=False;self.fault=fault
    def sleep(self,seconds):
        if self.running:self.dot+=round(seconds*driver.DOT_HZ)
    def identify(self):return dict(build_id='original')
    def load(self,rom):
        assert len(rom)==32768
        return dict(verified_bytes=32768)
    def control(self,name,value=None):
        if self.running:self.dot+=1000
        if name=='RUN':self.running=True;return None
        if name=='HALT':self.running=False;return dict(dot=self.dot)
        assert name=='INPUT'
        self.mask=value;self.events.append((self.dot,value));return dict(dot=self.dot)
    def read_host(self,address):
        return {abi.HOST_REG_STATE:int(self.running),abi.HOST_REG_INPUT_SOURCE:0,
                abi.HOST_REG_INPUT:self.mask,abi.HOST_REG_INPUT_EFFECTIVE:self.mask}[address]
    def snapshot(self):
        number=(self.dot-LCD-65459)//PERIOD
        metadata=dict(epoch=2,seq=number,dot=LCD+number*PERIOD+65459,size=5760)
        _,pixels=expected_snapshot(metadata,self.events,2)
        packed=bytearray(sum(pixels[n+i]<<(2*i) for i in range(4)) for n in range(0,23040,4))
        if self.fault:packed[0]^=1
        return metadata,bytes(packed)


@patch('physical_driver.BASELINE_ROM_SHA256',hashlib.sha256(bytes(32768)).hexdigest())
class PhysicalControlFlow(unittest.TestCase):
    def test_complete_route_and_cleanup(self):
        endpoint=Endpoint()
        with tempfile.TemporaryDirectory() as folder,patch.object(driver.time,'sleep',endpoint.sleep):
            result=driver.run(endpoint,bytes(32768),folder,lambda entry:None,'original')
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(len(result['checkpoints']),22)
        self.assertFalse(endpoint.running);self.assertEqual(endpoint.mask,0)

    def test_bad_frame_stops_and_cleans_up(self):
        endpoint=Endpoint(fault=True)
        with tempfile.TemporaryDirectory() as folder,patch.object(driver.time,'sleep',endpoint.sleep):
            with self.assertRaisesRegex(AssertionError,'FRAME_PIXELS'):
                driver.run(endpoint,bytes(32768),folder,lambda entry:None,'original')
        self.assertFalse(endpoint.running);self.assertEqual(endpoint.mask,0)


if __name__=='__main__':unittest.main()
