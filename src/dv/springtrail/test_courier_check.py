"""Checker rejection seams; actual CPU evidence is a separate required run."""
import unittest
from courier_check import Check, INITIALIZED
from courier_cases import operands, expected


def begin():
    check = Check(short=True)
    for address in INITIALIZED:
        check.write(0,address,0x5a)
    case = check.selected[0]
    fields = (0xc041,0xc040,0xc03b,0xc0f3,0xc042,0xc043,0xc044,0xc045,0xc01b,0xc01c)
    for address,value in zip(fields,operands(case)):
        check.write(1,address,value)
    for src,dst in ((0xc042,0xc034),(0xc043,0xc035),(0xc044,0xc036),(0xc045,0xc037)):
        check.write(2,dst,check.memory[src])
    check.write(100,0xc0fc,1)
    return check


class CourierCheck(unittest.TestCase):
    def test_complete_ordered_bytes(self):
        check=begin()
        for i,value in enumerate(expected(check.selected[0])):
            check.write(200+i,0xc100+i,value)
        check.write(1000,0xc0fd,1)
        self.assertEqual(check.reports[0]['bytes'],160)
        self.assertEqual(check.durations,[900])

    def test_wrong_missing_duplicate_and_tail_fail(self):
        for defect in ('tile','missing','duplicate','tail'):
            check=begin(); rows=list(enumerate(expected(check.selected[0])))
            if defect=='tile': rows[2]=(2,0)
            if defect=='missing': rows.pop()
            if defect=='duplicate': rows.insert(1,rows[0])
            if defect=='tail': rows[-1]=(159,0xa5)
            for i,value in rows:check.write(200+i,0xc100+i,value)
            with self.assertRaisesRegex(AssertionError,'COURIER_OAM'):
                check.write(1000,0xc0fd,1)

    def test_unrelated_write_and_incomplete_end_fail(self):
        for address in (0xc064, 0xc300, 0xc337):
            check=begin()
            with self.assertRaisesRegex(AssertionError,'COURIER_UNRELATED_WRITE'):
                check.write(200,address,0)
        with self.assertRaisesRegex(AssertionError,'MOTION_END'):
            begin().line('END 0')
        with self.assertRaisesRegex(AssertionError,'MOTION_INCOMPLETE'):
            begin().finish(1000)
