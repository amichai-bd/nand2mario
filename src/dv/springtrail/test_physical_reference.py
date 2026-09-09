import unittest
from physical_reference import LCD,PERIOD,VISIBLE,predict,expected_snapshot


class AppliedInputFrames(unittest.TestCase):
    def test_fixed_title_start_and_walk(self):
        events=[(LCD+PERIOD+1000,129)]
        first,playing=predict(1,events)
        self.assertFalse(playing);self.assertEqual(first.x,384)
        world,playing=predict(2,events)
        self.assertTrue(playing);self.assertEqual(world.x,400)
        moved,_=predict(3,events);self.assertEqual(moved.x,416)

    def test_snapshot_and_ambiguous_input(self):
        metadata=dict(epoch=2,seq=2,dot=LCD+2*PERIOD+65459)
        state,pixels=expected_snapshot(metadata,[(LCD+PERIOD+1000,129)],2)
        self.assertEqual((state.x,len(pixels)),(400,23040))
        with self.assertRaisesRegex(AssertionError,'INPUT_WINDOW'):
            predict(2,[(LCD+VISIBLE,129)])
        with self.assertRaisesRegex(AssertionError,'IDENTITY'):
            expected_snapshot({**metadata,'seq':1},[],2)


if __name__=='__main__':unittest.main()
