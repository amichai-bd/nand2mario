"""Host runner sensitivity; synthetic results are not physical evidence."""
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
import hashlib
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from n2m import generated_interfaces as abi
from interactions_reference import Game, PLAYING, PAUSED, RETRY, update
from flow_frames import image
from endurance import run, expected, check_pixels, LCD, PERIOD, DOT_HZ


def packed(pixels):
    return bytes(sum(pixels[i+j] << (2*j) for j in range(4)) for i in range(0, 23040, 4))


class Fake:
    def __init__(self, fault=None):
        self.wall=0.; self.dot=0; self.epoch=6; self.mask=0; self.running=False
        self.sequence=177017; self.uncertain=False; self.fault=fault
        self.game=Game(); self.next_vb=0; self.frames={}; self.calls=[]
        self.run_origin=0; self.terminal_clock=0

    def clock(self):
        if self.terminal_clock:
            self.terminal_clock-=1
            if self.terminal_clock==0:return self.wall-5
        return self.wall

    def tick(self, seconds):
        self.wall += seconds
        if self.running:
            self.advance(self.dot+round(seconds*DOT_HZ))

    def advance(self, target):
        if self.running and self.fault=='dot-duration':
            target=min(target,self.run_origin+19*DOT_HZ)
        while LCD+self.next_vb*PERIOD+65664 <= target:
            self.game=update(self.game,self.mask)
            self.frames[self.next_vb+2]=self.game
            self.next_vb+=1
        self.dot=target

    def call(self, name):
        self.calls.append(name); self.sequence+=1; self.tick(.001)

    def load(self, rom):
        self.call('load'); self.tick(1)
        if self.fault=='lifecycle' and self.calls.count('load')==4:
            raise RuntimeError('incomplete final load')
        self.dot=0; self.epoch+=2; self.running=False; self.mask=0
        self.game=Game(); self.next_vb=0; self.frames={}
        return {'verified_bytes':len(rom)}

    def read_host(self, addr):
        self.call('read')
        retired=(self.run_origin if self.running and self.fault=='progress' else self.dot)//8
        return {abi.HOST_REG_DOT_LO:self.dot&0xffffffff,
            abi.HOST_REG_DOT_HI:self.dot>>32,abi.HOST_REG_RETIRE_LO:retired&0xffffffff,
            abi.HOST_REG_RETIRE_HI:retired>>32,
            abi.HOST_REG_STATE:int(self.running),abi.HOST_REG_IMAGE_VALID:1,
            abi.HOST_REG_INPUT_SOURCE:0,abi.HOST_REG_INPUT:self.mask,
            abi.HOST_REG_INPUT_EFFECTIVE:self.mask}[addr]

    def control(self, name, value=None):
        self.call(name)
        if name=='HALT' and self.calls.count('load')==4 and self.fault=='cleanup':
            self.uncertain=True
            raise RuntimeError('final HALT reply lost')
        if name=='RUN':self.running=True;self.run_origin=self.dot
        if name=='HALT':self.running=False
        if name=='RESET':self.epoch+=1;self.dot=0
        if name=='INPUT':
            self.mask=value
            if self.fault=='input':return {'dot':self.dot+999999}
        return {'dot':self.dot}

    def run_dots(self,count):
        self.call('RUN_DOTS'); self.advance(self.dot+count)
        return dict(dot=self.dot,executed=count,reason=0)

    def snapshot(self):
        self.call('snapshot')
        if self.fault=='stopped' and self.running:self.running=False
        seq=(self.dot-LCD-65664)//PERIOD
        game=self.frames.get(seq,Game())
        data=packed(image(game))
        meta=dict(epoch=self.epoch,seq=seq,dot=LCD+seq*PERIOD+65663,size=5760)
        if self.fault=='epoch':meta['epoch']+=1
        if self.fault=='pixel':data=data[:-1]+bytes([data[-1]^64])
        if self.fault=='stale':meta['dot']-=5*PERIOD;meta['seq']-=5
        if self.fault=='uncertain':self.uncertain=True;raise RuntimeError('lost reply')
        self.tick(1.6)
        if self.fault=='duration' and self.calls.count('snapshot')==7:
            # The final valid sample is logged, then the elapsed-time source
            # reports a duration shorter than the frozen minimum.
            self.terminal_clock=2
        return meta,data


class EnduranceTests(unittest.TestCase):
    def test_route_terminal_independent_of_enemy_phase(self):
        for x in range(240*16,296*16+1,8):
            for vx in (-8,8):
                g=replace(Game(),mode=PLAYING,enemy_x=x,enemy_vx=vx)
                for _ in range(91):g=update(g,49)
                self.assertEqual((g.mode,g.player.x,g.player.y,g.player.camera,g.collected,g.score),
                                 (RETRY,3200,2336,128,1,1))
                self.assertEqual(check_pixels(packed(image(g)),RETRY),22656)
                for mode in (PLAYING,PAUSED):
                    stationary=replace(Game(),mode=mode,enemy_x=x,enemy_vx=vx)
                    self.assertEqual(check_pixels(packed(image(stationary)),mode),23040)

    def test_all_checked_pixels_and_exclusion(self):
        for mode in (0,PLAYING,PAUSED,RETRY):
            data=bytearray(packed(expected(mode)))
            self.assertEqual(check_pixels(data,mode),22656 if mode==RETRY else 23040)
            data[-1]^=64
            with self.assertRaisesRegex(AssertionError,'ENDURANCE_PIXELS'):check_pixels(data,mode)

    @patch('flow_reference.BASELINE_ROM_SHA256',hashlib.sha256(bytes(32768)).hexdigest())
    def test_complete_short_and_three_lifecycles(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Fake()
            result=run(client,bytes(32768),Path(directory)/'run',epoch=6,cycles=1,
                       clock=lambda:client.wall,sleep=client.tick)
            self.assertEqual(result['status'],'PASS')
            self.assertEqual((len(result['lifecycles']),client.calls.count('load'),result['epoch']),(3,4,17))
            self.assertGreaterEqual(result['continuous_seconds'],20)
            self.assertFalse(client.running);self.assertEqual(client.mask,0)
            start=client.calls.index('RUN');end=client.calls.index('HALT',start)
            self.assertFalse(set(client.calls[start+1:end]) & {'RUN_DOTS','load','RESET'})

    @patch('flow_reference.BASELINE_ROM_SHA256',hashlib.sha256(bytes(32768)).hexdigest())
    def test_failures_never_pass(self):
        for fault in ('pixel','epoch','stale','input','uncertain','stopped','lifecycle','cleanup'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                client=Fake(fault)
                with self.assertRaises((AssertionError,RuntimeError)):
                    run(client,bytes(32768),Path(directory)/'run',epoch=6,cycles=1,
                        clock=lambda:client.wall,sleep=client.tick)
                self.assertFalse((Path(directory)/'run/result.json').read_text().find('"status": "PASS"')>=0)
                if fault=='uncertain':self.assertTrue(client.uncertain)

    @patch('flow_reference.BASELINE_ROM_SHA256',hashlib.sha256(bytes(32768)).hexdigest())
    def test_progress_and_both_duration_guards(self):
        import json
        for fault,guard in (('progress','ENDURANCE_PROGRESS'),
                            ('duration','ENDURANCE_DURATION'),
                            ('dot-duration','ENDURANCE_DOT_DURATION')):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as directory:
                client=Fake(fault);root=Path(directory)/'run'
                with self.assertRaisesRegex(AssertionError,guard):
                    run(client,bytes(32768),root,epoch=6,cycles=1,
                        clock=client.clock,sleep=client.tick)
                result=json.loads((root/'result.json').read_text())
                self.assertEqual(result['status'],'FAIL')
                self.assertIn(guard,result['error'])
                self.assertFalse(result['uncertain'])
                self.assertFalse(client.running);self.assertEqual(client.mask,0)
                self.assertIn('final',result)


    def test_wrong_rom_before_any_side_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            client=Fake();root=Path(directory)/'run'
            with self.assertRaisesRegex(AssertionError,'HISTORICAL_SPRINGTRAIL_ROM'):
                run(client,bytes(32768),root,epoch=6,cycles=1)
            self.assertEqual(client.calls,[])
            self.assertFalse(root.exists())


if __name__=='__main__':unittest.main()
