"""Literal tile mapping and complete independent source-canvas reflection."""
import unittest
from entities_art import FIRST_TILE, MAPS, POSES, SOURCE_TILES, pieces, pixels, tiles


class EntityArt(unittest.TestCase):
    def test_literal_runtime_maps(self):
        expected = ((149,150,151,152),(149,150,153,154),(155,155,156,157),
                    (155,155,158,159),(160,161,162,163),(164,165,166,167),
                    (168,169,170),(168,171,170),(172,173,170))
        self.assertEqual(tuple(tuple(p[2] for p in pieces(n)) for n in POSES), expected)
        self.assertEqual((FIRST_TILE, len(SOURCE_TILES), sum(map(len,tiles()))), (149,25,1600))

    def test_full_canvas_reflection(self):
        for name in POSES:
            w,h = MAPS[name]['width'], MAPS[name]['height']
            normal = pixels(name)
            expected = bytes(normal[y*w+w-1-x] for y in range(h) for x in range(w))
            self.assertEqual(pixels(name, True), expected, name)
            self.assertEqual(len(normal), w*h)
            self.assertLessEqual(set(normal), {0,1,2,3})

    def test_states_have_visible_differences(self):
        for a,b in ((POSES[0],POSES[1]),(POSES[2],POSES[3]),(POSES[4],POSES[5]),
                    (POSES[6],POSES[7]),(POSES[7],POSES[8])):
            self.assertNotEqual(pixels(a), pixels(b), (a,b))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            pieces('unowned')


if __name__ == '__main__':
    unittest.main()
