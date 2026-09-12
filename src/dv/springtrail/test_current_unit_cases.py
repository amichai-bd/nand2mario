"""The current adapter preserves older proof operands and extends observation."""
import unittest
import motion_cases, power_cases, blocks_cases, progress_cases
from current_unit_cases import adapt
from entities_cases import ADDRESSES

class CurrentCases(unittest.TestCase):
    def test_all_names_and_direct_literals_survive(self):
        for old in (motion_cases,power_cases,blocks_cases,progress_cases):
            rows=adapt(old).cases()
            self.assertEqual([r['name'] for r in rows],[r['name'] for r in old.cases()])
            for prior,current in zip(old.cases(),rows):
                self.assertEqual(len(current['before']),123)
                self.assertEqual(bytes(dict(zip(ADDRESSES,current['before']))[a] for a in old.ADDRESSES),prior['before'])
                after=dict(zip(ADDRESSES,current['after']))
                self.assertEqual(bytes(after[a] for a in old.ADDRESSES),prior['after'])
                if prior['kind'] not in ('game','reset'):
                    self.assertEqual(current['after'][-56:],current['before'][-56:])
    def test_game_updates_use_current_entity_animation(self):
        row=next(r for r in adapt(power_cases).cases() if r['name']=='stomp')
        b=dict(zip(ADDRESSES,row['after']))
        self.assertEqual((b[0xc06f],b[0xc331]),(0,16))
        self.assertEqual((b[0xc304],b[0xc314],b[0xc324]),(2,3,3))
    def test_current_reset_repopulates_slots_and_reserved_zeros(self):
        row=next(r for r in adapt(progress_cases).cases() if r['kind']=='reset')
        b=dict(zip(ADDRESSES,row['after']))
        self.assertEqual((b[0xc304],b[0xc314],b[0xc324]),(0,1,0))
        self.assertEqual(b[0xc02e],1)
        self.assertTrue(all(b[a]==0 for base in (0xc300,0xc310,0xc320) for a in range(base+7,base+16)))
    def test_named_existing_behavior_literals(self):
        # Frozen pre-entity fixtures: these values must survive the new profile.
        anchors=((power_cases,'grow-end',{0xc06a:1,0xc06b:0,0xc06c:0}),
                 (power_cases,'star-count',{0xc06d:246}),
                 (power_cases,'hurt-to-safe',{0xc06b:3,0xc06c:96}),
                 (power_cases,'shot-move',{0xc071:192,0xc072:1,0xc077:62}),
                 (blocks_cases,'effect-rise',{0xc07d:132,0xc080:240,0xc081:4,0xc082:15}),
                 (progress_cases,'timer-zero',{0xc093:0,0xc094:0,0xc095:3}),
                 (progress_cases,'clear-final',{0xc000:1,0xc096:0}))
        for old,name,wants in anchors:
            row=next(r for r in adapt(old).cases() if r['name']==name)
            actual=dict(zip(ADDRESSES,row['after']))
            self.assertEqual({a:actual[a] for a in wants},wants,name)

    def test_compact_defaults_are_constant_and_adapter_is_idempotent(self):
        for old in (motion_cases,power_cases,blocks_cases,progress_cases):
            suite=adapt(old)
            self.assertIs(adapt(suite),suite)
            missing=[a for start,n in suite.EXTRA_RANGES for a in range(start,start+n)]
            for row in suite.cases():
                before=dict(zip(ADDRESSES,row['before']))
                self.assertEqual(bytes(before[a] for a in missing),suite.EXTRA_VALUES)
            self.assertEqual(set(missing)|set(suite.SEED_ADDRESSES),set(ADDRESSES))

    def test_split_names_preserved(self):
        for old in (power_cases,blocks_cases,progress_cases):
            current=adapt(old)
            self.assertEqual({k:[r['name'] for r in rows] for k,rows in current.parts().items()},
                             {k:[r['name'] for r in rows] for k,rows in old.parts().items()})
if __name__=='__main__':unittest.main()
