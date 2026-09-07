"""Incremental v0.5 checks; expectations come from the fixed program contract."""
from reference import (FIRST_IMAGE_END, FRAME_DOTS, INPUT_MASKS, WINDOW_END,
                       Reference, compare_record, input_window, pixel_shade)


class Online:
    def __init__(self):
        self.reference = Reference()
        self.inputs = []
        self.retirements = 0
        self.pixels = 0
        self.last_dot = 0

    def input(self, dot, buttons):
        index = len(self.inputs) + 1
        low, high = input_window(index)
        if type(dot) is not int or not low <= dot <= high or buttons != INPUT_MASKS[index - 1]:
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
        self.retirements += 1

    def pixel(self, frame, x, y, dot, shade):
        expected_frame, index = divmod(self.pixels, 23040)
        if expected_frame >= 602 or (frame, x, y) != (expected_frame, index % 160, index // 160):
            raise ValueError(f"V05_PIXEL_ORDER count={self.pixels} frame={frame} x={x} y={y}")
        expected = pixel_shade(frame, x, y)
        if shade != expected:
            raise ValueError(f"V05_PIXEL frame={frame} index={index} expected={expected} actual={shade}")
        if frame:
            expected_dot = FIRST_IMAGE_END - 143 * 456 - 159 + (frame - 1) * FRAME_DOTS + y * 456 + x
            if dot != expected_dot:
                raise ValueError(f"V05_PIXEL_DOT expected={expected_dot} actual={dot}")
        self.pixels += 1

    def running(self, dot, *, reset, paused, fault):
        if reset or fault or (paused and dot < WINDOW_END) or dot < self.last_dot:
            raise ValueError(f"V05_CONTINUITY dot={dot} reset={reset} paused={paused} fault={fault}")
        self.last_dot = dot

    def finish(self, pause_dot):
        if not WINDOW_END <= pause_dot <= WINDOW_END + 2000:
            raise ValueError("V05_PAUSE_WINDOW")
        if len(self.inputs) != 18:
            raise ValueError("V05_INPUT_COUNT")
        if self.pixels != 602 * 23040:
            raise ValueError(f"V05_PIXEL_MISSING count={self.pixels}")
        if self.reference.step(pause_dot) is not None:
            raise ValueError(f"V05_RETIRE_MISSING seq={self.retirements}")
        return dict(retirements=self.retirements, pixels=self.pixels,
                    inputs=len(self.inputs), pause_dot=pause_dot)
