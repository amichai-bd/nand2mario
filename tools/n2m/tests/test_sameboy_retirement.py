import copy
import unittest
from src.dv.sameboy.retirement import compare, project

RAW = '''read step=0 dot=4 address=0100 data=00
fetch step=0 kind=0 native_dot=4 pending=4
event=0 before=0100 after=0101 dot=8 af=0000 bc=0000 de=0000 hl=0000 sp=fffe ime=0 delay=0 halt=0 stop=0 bug=0 ie=00 if=00 buttons=0
read step=1 dot=8 address=0101 data=76
fetch step=1 kind=0 native_dot=8 pending=4
read step=1 dot=12 address=0102 data=00
fetch step=1 kind=2 native_dot=12 pending=4
event=1 before=0101 after=0102 dot=12 af=0000 bc=0000 de=0000 hl=0000 sp=fffe ime=0 delay=0 halt=1 stop=0 bug=0 ie=00 if=00 buttons=0
'''


class RetirementProjection(unittest.TestCase):
    def test_nop_halt_actual_fetch_boundaries(self):
        records=project(RAW)
        self.assertEqual([(r['pc_before'],r['pc_after'],r['dot'],r['opcode'],r['halted']) for r in records],[(0x100,0x101,8,0,0),(0x101,0x102,12,0x76,1)])

    def test_duplicate_unknown_or_orphan_hook_fails(self):
        mutations=[RAW.replace('kind=0','kind=3',1),
                   RAW.replace('fetch step=0 kind=0 native_dot=4 pending=4\n','fetch step=0 kind=0 native_dot=4 pending=4\n'*2),
                   RAW+'fetch step=9 kind=0 native_dot=20 pending=4\n']
        for raw in mutations:
            with self.subTest(raw=raw),self.assertRaises(ValueError): project(raw)

    def test_missing_reordered_or_early_event_fails(self):
        first=RAW.splitlines()[2]+'\n'
        mutations=[RAW.replace(first,''),
                   RAW.replace('read step=0 dot=4 address=0100 data=00\n','')+'read step=0 dot=4 address=0100 data=00\n',
                   RAW.replace('after=0101 dot=8','after=0101 dot=4')]
        for raw in mutations:
            with self.subTest(raw=raw),self.assertRaises(ValueError): project(raw)

    def test_actual_post_event_interrupt_state_is_used(self):
        record=project(RAW.replace('ie=00 if=00','ie=01 if=04',1))[0]
        self.assertEqual((record['ie'],record['iflags']),(1,4))

    def test_missing_initial_fetch_latency_fails(self):
        raw=RAW.replace('native_dot=4 pending=4','native_dot=0 pending=4',1)
        with self.assertRaisesRegex(ValueError,'invalid initial fetch'): project(raw)

    def test_exact_first_field_missing_and_reorder_context(self):
        expected=project(RAW)
        actual=copy.deepcopy(expected);actual[0]['a']=1
        with self.assertRaisesRegex(ValueError,'event 0 a: expected=0 actual=1'):compare(expected,actual)
        with self.assertRaisesRegex(ValueError,'event count at 1'):compare(expected,expected[:1])
        with self.assertRaisesRegex(ValueError,'event 0 seq: expected=0 actual=1'):compare(expected,list(reversed(expected)))

    def test_obsolete_future_snapshot_fails(self):
        with self.assertRaisesRegex(ValueError,'obsolete future closing'):
            project(RAW+'closing step=1 native_dot=16 ie=00 if=00 buttons=0\n')
