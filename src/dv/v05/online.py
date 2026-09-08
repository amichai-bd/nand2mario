"""Incremental v0.5 checks; expectations come from the fixed program contract."""
from reference import (FIRST_IMAGE_END, FRAME_DOTS, INPUT_MASKS, WINDOW_END, LCD_COMMIT,
                       Reference, compare_record, input_window, pixel_shade,
                       BOUNDED_END, bounded_pixel_count)
from collections import deque


class Online:
    def __init__(self, *, short=False, bounded=False):
        if short and bounded:
            raise ValueError('conflicting v05 schedules')
        self.short = short
        self.bounded = bounded
        self.input_masks = (0x11,) if bounded else INPUT_MASKS[:2] if short else INPUT_MASKS
        self.end = BOUNDED_END if bounded else FIRST_IMAGE_END + 4 * FRAME_DOTS if short else WINDOW_END
        self.frame_count = 2 if bounded else 6 if short else 602
        self.reference = Reference()
        self.inputs = []
        self.retirements = 0
        self.pixels = 0
        self.last_dot = 0
        self.writes = deque()
        self.checked_writes = 0

    def write(self, dot, address, data):
        self.writes.append((dot, address, data))

    def input(self, dot, buttons):
        index = len(self.inputs) + 1
        low, high = input_window(index, short=self.short, bounded=self.bounded)
        if (type(dot) is not int or type(buttons) is not int
                or not low <= dot <= high or buttons != self.input_masks[index - 1]):
            raise ValueError(f"V05_INPUT_WINDOW transition={index} dot={dot} buttons={buttons}")
        # Windows fall in HALT. Queue only authentic, observed future events;
        # later register/pixel data never selects the expected input value.
        if self.reference.next_input is not None or dot < self.reference.dot:
            raise ValueError("V05_INPUT_ORDER")
        self.reference.next_input = (dot, buttons)
        self.inputs.append((dot, buttons))

    def retirement(self, actual):
        expected = self.reference.step(actual['dot'])
        if expected is None:
            raise ValueError(f"V05_RETIRE_EXTRA seq={self.retirements}")
        compare_record(expected, actual)
        for expected_write in self.reference.writes[self.checked_writes:]:
            observed = self.writes.popleft() if self.writes else None
            if observed != expected_write:
                raise ValueError(f"V05_WRITE expected={expected_write} actual={observed}")
            self.checked_writes += 1
        self.retirements += 1

    def pixel(self, frame, x, y, dot, shade):
        expected_frame, index = divmod(self.pixels, 23040)
        if expected_frame >= self.frame_count or (frame, x, y) != (expected_frame, index % 160, index // 160):
            raise ValueError(f"V05_PIXEL_ORDER count={self.pixels} frame={frame} x={x} y={y}")
        expected = pixel_shade(frame, x, y, short=self.short, bounded=self.bounded)
        if shade != expected:
            raise ValueError(f"V05_PIXEL frame={frame} index={index} expected={expected} actual={shade}")
        if not frame:
            expected_dot = LCD_COMMIT + (93 if y == 0 else 92 + y * 456) + x
            if dot != expected_dot:
                raise ValueError(f"V05_PIXEL_DOT expected={expected_dot} actual={dot}")
        else:
            expected_dot = FIRST_IMAGE_END - 143 * 456 - 159 + (frame - 1) * FRAME_DOTS + y * 456 + x
            if dot != expected_dot:
                raise ValueError(f"V05_PIXEL_DOT expected={expected_dot} actual={dot}")
        self.pixels += 1

    def running(self, dot, *, reset, paused, fault):
        if reset or fault or (paused and dot < self.end) or dot < self.last_dot:
            raise ValueError(f"V05_CONTINUITY dot={dot} reset={reset} paused={paused} fault={fault}")
        self.last_dot = dot

    def finish(self, pause_dot):
        if not self.end <= pause_dot <= self.end + 2000:
            raise ValueError("V05_PAUSE_WINDOW")
        if len(self.inputs) != len(self.input_masks):
            raise ValueError("V05_INPUT_COUNT")
        expected_pixels = bounded_pixel_count(pause_dot) if self.bounded else self.frame_count * 23040
        if self.pixels != expected_pixels:
            raise ValueError(f"V05_PIXEL_MISSING count={self.pixels}")
        if self.reference.step(pause_dot) is not None:
            raise ValueError(f"V05_RETIRE_MISSING seq={self.retirements}")
        if self.writes:
            raise ValueError("V05_WRITE_EXTRA")
        return dict(retirements=self.retirements, pixels=self.pixels,
                    inputs=len(self.inputs), pause_dot=pause_dot)
