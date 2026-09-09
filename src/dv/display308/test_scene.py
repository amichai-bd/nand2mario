"""Literal boundary/priority anchors independent of generated assembly."""
import unittest
from scene import image, shade


class Scene(unittest.TestCase):
    def test_split(self):
        self.assertEqual([shade(0,y) for y in (0,7,8,15,16,19,28,31)],
                         [0,0,1,1,0,0,1,1])
        self.assertEqual([shade(x,16) for x in (0,7,8,15,16,159)],
                         [0,0,1,1,2,3])
        self.assertEqual(len(image()),5120)

    def test_objects(self):
        # Lower X wins its opaque stripes; transparent stripes reveal object1.
        self.assertEqual([shade(x,20) for x in range(20,28)],
                         [1,2,1,2,2,2,2,2])
        # Object1 wins equal-X over object2's corner color3.
        self.assertEqual(shade(20,20),1)
        self.assertEqual(shade(24,24),2)
        # Behind-BG applies only after selecting the object color.
        self.assertEqual([shade(x,20) for x in (32,39)], [2,2])
        self.assertEqual([shade(x,24) for x in (32,39)], [1,1])
        self.assertEqual([shade(56,y) for y in (20,21,27,28)], [2,2,2,0])
        self.assertEqual([shade(63,y) for y in (24,25,27)], [2,3,3])


if __name__ == '__main__':
    unittest.main()
