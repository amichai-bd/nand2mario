import unittest
from src.dv.sameboy.compare_diagnostic import compare_pixels


class VisiblePixels(unittest.TestCase):
    def setUp(self):
        self.reference=[{'frame':0,'x':0,'y':0,'rgb':0xffffff},
                        {'frame':0,'x':1,'y':0,'rgb':0xaaaaaa}]
        self.actual=[{'frame':0,'index':0,'shade':0,'dot':93},
                     {'frame':0,'index':1,'shade':1,'dot':94}]

    def test_values_ignore_only_separate_internal_action_timestamps(self):
        compare_pixels(self.reference,self.actual)
        self.actual[0]['dot']=999
        compare_pixels(self.reference,self.actual)

    def test_corrupt_pixel_first_context(self):
        self.actual[1]['shade']=2
        with self.assertRaisesRegex(ValueError,r'pixel 1: expected=\(0, 1, 1\) actual=\(0, 1, 2\)'):
            compare_pixels(self.reference,self.actual)

    def test_missing_extra_and_reordered_pixels(self):
        for actual,context in [(self.actual[:1],'pixel count at 1'),
                               (self.actual+self.actual[:1],'pixel count at 2'),
                               (list(reversed(self.actual)),'pixel 0: expected=')]:
            with self.subTest(context=context),self.assertRaisesRegex(ValueError,context):
                compare_pixels(self.reference,actual)
