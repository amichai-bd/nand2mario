"""Synthetic capture/frontier faults, not device or game reference evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from n2m import generated_interfaces as abi
from n2m.records import file_hash
from paused_capture import acquire, public_state, BASELINE_ROM

IDENTITY = dict(rom_sha256=BASELINE_ROM, build_id='cd'*16, epoch=4)
PLAN = dict(captures=[dict(seq=f, pause_dot=151284+f*70224,
    reference_offset=(f+2)*23040, input_after=(None,129,1,1,1,0,0,None)[f]) for f in range(8)],
    inputs=[dict(dot=221508+i*70224, buttons=v) for i,v in enumerate((129,1,1,1,0,0))],
    normal_frames=8, end_dot=642852, scripted_updates=4)
REFERENCE = bytes(46080)+b''.join(bytes((f+i)%4 for i in range(23040)) for f in range(8))


class Client:
    def __init__(self):
        self.sequence=100; self.uncertain=False; self.dot=0; self.mask=0
        self.calls=[]; self.record=lambda entry: None; self.fault=None

    def call(self, name):
        self.record(dict(command=name, sequence=self.sequence))
        self.calls.append(name); self.sequence+=1

    def identify(self):
        self.call('identify')
        return dict(build_id=IDENTITY['build_id'])

    def read_host(self, address):
        self.call('read')
        return {abi.HOST_REG_DOT_LO:self.dot,abi.HOST_REG_DOT_HI:0,
            abi.HOST_REG_RETIRE_LO:self.dot//4,abi.HOST_REG_RETIRE_HI:0,
            abi.HOST_REG_STATE:0,abi.HOST_REG_IMAGE_VALID:1,
            abi.HOST_REG_INPUT_SOURCE:0,abi.HOST_REG_INPUT:self.mask,
            abi.HOST_REG_INPUT_EFFECTIVE:self.mask}[address]

    def run_dots(self,count):
        self.call('run_dots');self.dot+=count
        if self.fault=='uncertain':
            self.uncertain=True;raise RuntimeError('lost reply')
        return dict(dot=self.dot, executed=count-(self.fault=='count'), reason=0)

    def snapshot(self):
        self.call('snapshot')
        f=(self.dot-76964)//70224-1
        data=bytes([0xe4,0x39,0x4e,0x93][f%4] for _ in range(5760))
        metadata=dict(epoch=4,seq=f,dot=76964+f*70224+65663,size=5760)
        if self.fault=='pixel':data=data[:-1]+bytes([data[-1]^64])
        if self.fault=='short':data=data[:-1]
        if self.fault=='epoch':metadata['epoch']=5
        if self.fault=='duplicate':metadata['seq']=max(0,f-1)
        if self.fault=='missing':metadata['seq']=f+1
        if self.fault=='dot':metadata['dot']-=456
        return metadata,data

    def control(self,action,value):
        assert action=='INPUT'
        self.call('input');self.mask=value
        return dict(dot=self.dot+(self.fault=='input'))


class CaptureTests(unittest.TestCase):
    def test_new_rom_cannot_use_historical_schedule(self):
        with tempfile.TemporaryDirectory() as temp:
            client=Client()
            with self.assertRaisesRegex(AssertionError,'CAPTURE_BASELINE_ROM'):
                acquire(client,Path(temp),PLAN,REFERENCE,
                        dict(IDENTITY,rom_sha256='00'*32),4,origin={})
            self.assertEqual(client.calls,[])

    def origin(self, client):
        frontier=public_state(client)
        return dict(binding=IDENTITY,frontier=frontier,next_sequence=client.sequence)

    def first(self, client, root):
        return acquire(client,root,PLAN,REFERENCE,IDENTITY,4,origin=self.origin(client))

    def resume(self, client, root):
        path=root/'batch-0000/checkpoint.json'
        return acquire(client,root,PLAN,REFERENCE,IDENTITY,8,
                       previous=path,previous_sha256=file_hash(path))

    def test_complete_two_batches_preserve_mask_and_all_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);client=Client();original=client.record
            first=self.first(client,root)
            self.assertEqual((first['next_frame'],first['next_input'],client.dot,client.mask),(4,3,361956,1))
            calls=len(client.calls)
            final=self.resume(client,root)
            self.assertEqual((final['next_frame'],final['next_input'],client.dot,client.mask),(8,6,642852,0))
            self.assertEqual([f['metadata']['seq'] for f in final['frames']],list(range(8)))
            self.assertEqual(sum((root/f['packed_file']).stat().st_size for f in final['frames']),46080)
            self.assertEqual(client.calls.count('run_dots'),10)
            self.assertEqual(client.calls[calls:].count('snapshot'),5) # retained frontier + four new frames
            self.assertIs(client.record,original)
            self.assertEqual([dict(dot=i['dot'],buttons=i['buttons']) for i in final['inputs']],PLAN['inputs'])

    def test_actual_frame_and_count_faults_leave_no_checkpoint(self):
        for fault in ('pixel','short','epoch','duplicate','missing','dot','count','input','uncertain'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as temp:
                client=Client();client.fault=fault;root=Path(temp)
                with self.assertRaises((AssertionError,RuntimeError)):self.first(client,root)
                self.assertFalse((root/'batch-0000/checkpoint.json').exists())
                self.assertEqual(json.loads((root/'batch-0000/failure.json').read_text())['status'],'FAIL')
                if fault=='uncertain':self.assertTrue(client.uncertain)

    def test_resume_rejects_session_and_public_changes(self):
        for fault in ('sequence','uncertain','dot','mask'):
            with self.subTest(fault=fault),tempfile.TemporaryDirectory() as temp:
                client=Client();root=Path(temp);self.first(client,root)
                if fault=='sequence':client.sequence+=1
                elif fault=='uncertain':client.uncertain=True
                elif fault=='dot':client.dot+=1
                else:client.mask=0
                runs=client.calls.count('run_dots')
                with self.assertRaises(AssertionError):self.resume(client,root)
                self.assertEqual(client.calls.count('run_dots'),runs)

    def test_artifact_and_checkpoint_edits_are_rejected_before_uart(self):
        for which in ('frame','checkpoint','reference','plan'):
            with self.subTest(which=which),tempfile.TemporaryDirectory() as temp:
                client=Client();root=Path(temp);self.first(client,root)
                path=root/'batch-0000/checkpoint.json';bound=file_hash(path)
                plan=copy.deepcopy(PLAN);reference=REFERENCE
                if which=='frame':(root/'batch-0000/frame-0000.2bpp').write_bytes(b'bad')
                elif which=='checkpoint':path.write_text(path.read_text()+' ')
                elif which=='reference':reference=bytes([1])+reference[1:]
                else:plan['captures'][2]['input_after']=2
                calls=len(client.calls)
                with self.assertRaises(AssertionError):
                    acquire(client,root,plan,reference,IDENTITY,8,previous=path,previous_sha256=bound)
                self.assertEqual(len(client.calls),calls)


if __name__=='__main__':unittest.main()
