import unittest
from renderer_oracle import Check
from renderer_cases import cases, maps
from scene_reference import image


def events(count=3):
    result = [(0xff40, 0x17)] + [(0x9c00+i, 0) for i in range(576)]
    final, writes = maps(count)
    for i, case in enumerate(cases()[:count]):
        scene = image(case['game'])
        result += [(0xc0eb, i)] + list(enumerate(scene, 0xc100))
        result += [(0xc0ec, i), (0xc0ee, i)]
        if case['restart']:
            result += [(0xff43, 0), (0xff40, 0x17)]
        result += writes[i]
        if i == 17:
            result += [(0xff40, 0x1f)]
        result += list(enumerate(scene, 0xfe00)) + [(0xc0ef, i)]
        result += [(0xc0e0, b) for b in scene]
        result += [(0xc0e2, 0x1f if i == 17 else 0x17), (0xc0e3, 0), (0xc0fe, i)]
    return result + [(0xc0e1, b) for b in final] + [(0xc0ff, 165)]


def replay(rows, count=3):
    check = Check(count)
    for i, (address, data) in enumerate(rows):
        check.write((i+1)*8, address, data)
    return check


class Renderer(unittest.TestCase):
    def test_complete_partial_and_full(self):
        for count in (3, 18):
            self.assertTrue(replay(events(count), count).terminal)

    def test_missing_prepare(self):
        with self.assertRaisesRegex(AssertionError, 'RENDER_PREP_OUTSIDE'):
            replay([row for row in events() if row != (0xc0eb, 0)])

    def test_actual_object_readback(self):
        rows = events()
        i = next(i for i, row in enumerate(rows) if row[0] == 0xc0e0)
        rows[i] = (0xc0e0, rows[i][1] ^ 1)
        with self.assertRaisesRegex(AssertionError, 'RENDER_OAM_READBACK'):
            replay(rows)

    def test_truncated_map(self):
        rows = events()
        i = next(i for i, row in enumerate(rows) if row[0] == 0xc0e1)
        del rows[i]
        with self.assertRaisesRegex(AssertionError, 'RENDER_MAP_READBACK'):
            replay(rows)

    def test_duplicate_published_byte(self):
        rows = events()
        i = next(i for i, row in enumerate(rows) if row[0] == 0xfe00)
        rows.insert(i, rows[i])
        with self.assertRaisesRegex(AssertionError, 'RENDER_PUBLISH'):
            replay(rows)


if __name__ == '__main__':
    unittest.main()
