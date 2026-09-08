"""Literal boundaries and actual-observation mutations for the online checker."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src/dv/v05'))
from online import Online
from reference import input_window, pixel_shade, bounded_pixel_count, Reference


class OnlineTests(unittest.TestCase):
    def test_first_retirement_and_changed_pc(self):
        record = dict(version=1, kind=0, epoch=2, seq=0, dot=8,
                      pc_before=0x100, pc_after=0x101, opcode=0, opcode_length=1,
                      a=0, f=0, b=0, c=0, d=0, e=0, h=0, l=0, sp=0xfffe,
                      ime=0, ime_delay=0, halted=0, stopped=0, halt_bug=0,
                      ie=0, iflags=0, buttons=0)
        Online().retirement(record)
        with self.assertRaisesRegex(ValueError, 'V05_RETIRE.*pc_after'):
            Online().retirement(dict(record, pc_after=0x102))

    def test_pixel_mutation_and_gap(self):
        monitor = Online()
        monitor.pixel(0, 0, 0, 42077, 0)
        with self.assertRaisesRegex(ValueError, 'V05_PIXEL .*expected=0 actual=1'):
            monitor.pixel(0, 1, 0, 42078, 1)
        with self.assertRaisesRegex(ValueError, 'V05_PIXEL_ORDER'):
            monitor.pixel(0, 2, 0, 42079, 0)

    def test_blank_cadence_literal_boundaries(self):
        for index, dot in ((0,42077),(159,42236),(160,42532),(23039,107443)):
            monitor = Online()
            monitor.pixels = index
            monitor.pixel(0, index % 160, index // 160, dot, 0)
            monitor = Online()
            monitor.pixels = index
            with self.assertRaisesRegex(ValueError, 'V05_PIXEL_DOT'):
                monitor.pixel(0, index % 160, index // 160, dot + 1, 0)
        monitor = Online()
        monitor.pixel(0,0,0,42077,0)
        with self.assertRaisesRegex(ValueError, 'V05_PIXEL_ORDER'):
            monitor.pixel(0,2,0,42079,0)

    def test_input_window_and_pending_event(self):
        monitor = Online()
        monitor.input(1602147, 1)
        self.assertEqual(monitor.reference.next_input, (1602147, 1))
        with self.assertRaisesRegex(ValueError, 'V05_INPUT_ORDER'):
            monitor.input(3006627, 0)
        with self.assertRaisesRegex(ValueError, 'V05_INPUT_WINDOW'):
            Online().input(1602146, 1)

    def test_reset_pause_fault_and_missing_tail(self):
        for flags in [dict(reset=True, paused=False, fault=False),
                      dict(reset=False, paused=True, fault=False),
                      dict(reset=False, paused=False, fault=True)]:
            with self.assertRaisesRegex(ValueError, 'V05_CONTINUITY'):
                Online().running(100, **flags)
        with self.assertRaisesRegex(ValueError, 'V05_INPUT_COUNT'):
            Online().finish(42312067)


    def test_short_literal_schedule_and_full_default(self):
        self.assertEqual(input_window(1, short=True), (267891,269891))
        self.assertEqual(input_window(2, short=True), (338115,340115))
        with self.assertRaises(ValueError):
            input_window(3, short=True)
        self.assertEqual([pixel_shade(f,0,64,short=True) for f in (3,4,5)], [0,1,0])
        self.assertEqual((Online(short=True).end, Online(short=True).frame_count), (458563,6))
        self.assertEqual((Online().end, Online().frame_count), (42312067,602))
        self.assertEqual(len(Online().input_masks),18)

    def test_short_finish_missing_and_extra_observations(self):
        m = Online(short=True)
        with self.assertRaisesRegex(ValueError, 'V05_PAUSE_WINDOW'):
            m.finish(458562)
        with self.assertRaisesRegex(ValueError, 'V05_INPUT_COUNT'):
            m.finish(458563)
        m.inputs = [(267891,1),(338115,0)]
        with self.assertRaisesRegex(ValueError, 'V05_PIXEL_MISSING'):
            m.finish(458563)
        m.pixels = 138240
        with self.assertRaisesRegex(ValueError, 'V05_RETIRE_MISSING'):
            m.finish(458563)
        m.reference.step = lambda _: None
        m.write(1,0xc000,0)
        with self.assertRaisesRegex(ValueError, 'V05_WRITE_EXTRA'):
            m.finish(458563)
        m.writes.clear()
        self.assertEqual(m.finish(458563)['pixels'],138240)
        m.inputs.append((338116,0))
        with self.assertRaisesRegex(ValueError, 'V05_INPUT_COUNT'):
            m.finish(458563)

    def test_bounded_literal_input_and_program_tail(self):
        self.assertEqual(input_window(1, bounded=True), (50000,52000))
        with self.assertRaises(ValueError):
            input_window(2, bounded=True)
        for dot in (50000,52000):
            reference = Reference([(dot,0x11)])
            records = list(reference.records(147132))
            self.assertEqual(len(records),6357)
            self.assertEqual((records[-1]['dot'],records[-1]['halted'],records[-1]['buttons']),
                             (108156,1,0x11))
        self.assertEqual([pixel_shade(1,x,64,bounded=True) for x in (0,8,32,40)], [1,0,1,0])
        with self.assertRaisesRegex(ValueError,'V05_INPUT_WINDOW'):
            Online(bounded=True).input(49999,0x11)

    def test_bounded_partial_last_pixel_and_order(self):
        self.assertEqual(bounded_pixel_count(145132),34561)
        self.assertEqual(bounded_pixel_count(145333),34720)
        self.assertEqual(bounded_pixel_count(147132),35360)
        m=Online(bounded=True)
        m.pixels=34560
        m.pixel(1,0,72,145132,0)
        with self.assertRaisesRegex(ValueError,'V05_PIXEL_ORDER'):
            m.pixel(1,2,72,145134,0)
        with self.assertRaisesRegex(ValueError,'V05_PIXEL_DOT'):
            m.pixel(1,1,72,145134,0)

    def test_bounded_finish_requires_every_postbound_pixel_and_record(self):
        m=Online(bounded=True)
        m.input(50000,0x11)
        m.pixels=34561
        with self.assertRaisesRegex(ValueError,'V05_PIXEL_MISSING'):
            m.finish(145333)  # Checking only through the requested bound misses159.
        m.pixels=34719
        with self.assertRaisesRegex(ValueError,'V05_PIXEL_MISSING'):
            m.finish(145333)
        m.pixels=34721
        with self.assertRaisesRegex(ValueError,'V05_PIXEL_MISSING'):
            m.finish(145333)
        m.pixels=34720
        with self.assertRaisesRegex(ValueError,'V05_RETIRE_MISSING'):
            m.finish(145333)
        m.reference.step=lambda _: None
        m.write(145300,0xc000,1)
        with self.assertRaisesRegex(ValueError,'V05_WRITE_EXTRA'):
            m.finish(145333)
        m.writes.clear()
        self.assertEqual(m.finish(145333)['pixels'],34720)


if __name__ == '__main__':
    unittest.main()
