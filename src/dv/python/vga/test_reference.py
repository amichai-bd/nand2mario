"""Small host checks for the independent canonical format and failure paths."""
import unittest
from reference import EXPECTED_CRC, Raster, crc, frame


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


if __name__ == '__main__':
    unittest.main()
