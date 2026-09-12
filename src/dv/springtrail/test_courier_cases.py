"""Literal composition anchors independent of an executing DUT."""
import unittest
from courier_cases import cases, parts, expected, operands


class CourierCases(unittest.TestCase):
    def test_matrix_and_complete_tail(self):
        rows = cases()
        self.assertEqual(len(rows), 50)
        self.assertEqual([len(x) for x in parts().values()], [18, 18, 14])
        self.assertEqual({(r['pose'], r['left']) for r in rows[:36]},
                         {(p, f) for p in range(18) for f in (False, True)})
        for row in rows:
            self.assertEqual(len(operands(row)), 10)
            output = expected(row)
            self.assertEqual(len(output), 160)
            self.assertEqual(output[24:], bytes(136))

    def test_literal_order_and_reflection(self):
        self.assertEqual(expected(cases()[0])[:16], bytes(
            [48,32,42,0,48,40,43,0,56,32,44,0,56,40,45,0]))
        self.assertEqual(expected(cases()[1])[:16], bytes(
            [48,40,42,32,48,32,43,32,56,40,44,32,56,32,45,32]))
        self.assertEqual(expected(cases()[34])[:24], bytes(
            [40,32,42,0,40,40,43,0,48,32,58,0,48,40,106,0,
             56,32,60,0,56,40,61,0]))

    def test_clipping_projection_and_hidden_literals(self):
        rows = cases()
        self.assertEqual(expected(rows[36])[::4], bytes(40))
        self.assertEqual(list(expected(rows[37])[:8]), [40,1,54,32,0,249,55,32])
        self.assertEqual(expected(rows[44])[:8], bytes([15,7,42,0,15,15,43,0]))
        self.assertEqual(expected(rows[46])[:4], bytes([47,9,42,0]))
        self.assertEqual(expected(rows[47])[::4], bytes(40))
        for row in rows[-2:]:
            self.assertEqual(expected(row)[::4], bytes(40))
            visible = expected(dict(row, hidden=False))
            for offset in range(160):
                if offset % 4:
                    self.assertEqual(expected(row)[offset], visible[offset])
