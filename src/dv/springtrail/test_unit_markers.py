import unittest
from unit_cases import timing_marker,timing_report


class CallMarkers(unittest.TestCase):
    def test_complete_call(self):
        state=timing_marker(None,None,0xc0ee,100,33,33)
        state=timing_marker(*state,0xc0ef,4100,0,33)
        self.assertEqual(timing_report(*state),4000)

    def test_missing_or_duplicate_pair(self):
        with self.assertRaisesRegex(AssertionError,'REPORT_TIMING'):
            timing_report(None,None)
        state=timing_marker(None,None,0xc0ee,100,33,33)
        with self.assertRaisesRegex(AssertionError,'REPORT_TIMING'):
            timing_report(*state)
        with self.assertRaisesRegex(AssertionError,'MOVEMENT_BEGIN'):
            timing_marker(*state,0xc0ee,101,33,33)
        state=timing_marker(*state,0xc0ef,200,0,33)
        with self.assertRaisesRegex(AssertionError,'MOVEMENT_BEGIN'):
            timing_marker(*state,0xc0ee,300,33,33)

    def test_marker_values_and_budget(self):
        with self.assertRaisesRegex(AssertionError,'MOVEMENT_BEGIN'):
            timing_marker(None,None,0xc0ee,100,1,33)
        with self.assertRaisesRegex(AssertionError,'MOVEMENT_END'):
            timing_marker(100,None,0xc0ef,200,1,33)
        with self.assertRaisesRegex(AssertionError,'VBLANK_BUDGET'):
            timing_marker(100,None,0xc0ef,4660,0,33)


if __name__=='__main__':unittest.main()
