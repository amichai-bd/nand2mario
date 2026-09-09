"""Small host checks for the independent canonical format and failure paths."""
import unittest
from reference import EXPECTED_CRC, Raster, crc, frame
from public_trace import Trace


class ReferenceTests(unittest.TestCase):
    def test_crc_anchor_and_distinct_frames(self):
        self.assertEqual(crc(b'123456789'), 0xCBF43926)
        for number in (0, 1):
            data = frame(number)
            self.assertEqual(len(data), 23040)
            self.assertEqual(set(data), {0, 1, 2, 3})
            self.assertEqual(crc(data), EXPECTED_CRC[number])
        self.assertNotEqual(frame(0), frame(1))

    def test_empty_and_one_frame_rejected(self):
        for completed in ([], [0]):
            model = Raster()
            model.completed = completed
            with self.assertRaisesRegex(AssertionError, 'VGA_CRC_INCOMPLETE'):
                model.finish()

    def test_first_pixel_rgb_fault(self):
        model = Raster()
        model.edge = 420000 + 24 * 800 + 80 + 1
        with self.assertRaisesRegex(AssertionError, 'VGA_CRC_RGB raster=1 x=80 y=24'):
            model.sample(0x03ff)  # red forced zero; other channels remain white

    def test_first_pixel_and_replica(self):
        model = Raster()
        model.edge = 420000 + 24 * 800 + 80 + 1
        model.sample(0x3fff)
        self.assertEqual(model.canonical[0], bytes([0]))
        self.assertEqual(model.replicas[0], 1)
        with self.assertRaisesRegex(AssertionError, 'x=81 y=24'):
            model.sample(3)

    def test_sync_error_rejected(self):
        model = Raster()
        model.edge = 656 + 1
        with self.assertRaisesRegex(AssertionError, 'VGA_CRC_RGB'):
            model.sample(3)  # hsync must already be low at x=656

    def test_partial_trace_and_incomplete_end(self):
        trace = Trace()
        self.assertEqual(list(trace.feed('00000001,000000000000')), [])
        self.assertEqual(list(trace.feed('5169,4003\n')), [(20841, 0x4003)])
        with self.assertRaisesRegex(AssertionError, 'INCOMPLETE'):
            trace.finish()
        with self.assertRaisesRegex(AssertionError, 'SHORT'):
            list(trace.feed('END\n'))

    def test_bad_trace_records(self):
        records = [('00000002,0000000000005169,4003\n', 'ORDER'),
                   ('00000001,0000000000005168,4003\n', 'TIME'),
                   ('00000001,0000000000005169,4x03\n', 'FORMAT_UNKNOWN')]
        for record, failure in records:
            with self.assertRaisesRegex(AssertionError, failure):
                list(Trace().feed(record))
        trace = Trace()
        record = '00000001,0000000000005169,4003\n'
        list(trace.feed(record))
        with self.assertRaisesRegex(AssertionError, 'ORDER'):
            list(trace.feed(record))


if __name__ == '__main__':
    unittest.main()
