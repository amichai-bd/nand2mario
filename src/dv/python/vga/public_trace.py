"""Strict ordered transport for passive public-pin samples, not an oracle."""
import re

SAMPLES = 1260027  # 26 reset samples, then edge 1 through 1260001.
HALF_PERIOD_PS = 19841


class Trace:
    def __init__(self):
        self.count = 0
        self.pending = ''
        self.ended = False

    def feed(self, text):
        self.pending += text
        lines = self.pending.split('\n')
        self.pending = lines.pop()
        for line in lines:
            line = line.rstrip('\r')
            assert not self.ended, 'VGA_CRC_TRACE_AFTER_END'
            if line == 'END':
                assert self.count == SAMPLES, 'VGA_CRC_TRACE_SHORT'
                self.ended = True
                continue
            assert re.fullmatch(r'[0-9a-fA-F]{8},[0-9a-fA-F]{16},[0-9a-fA-F]{4}', line), 'VGA_CRC_TRACE_FORMAT_UNKNOWN'
            count, timestamp, public = (int(value, 16) for value in line.split(','))
            assert count == self.count + 1 and count <= SAMPLES, 'VGA_CRC_TRACE_ORDER'
            assert timestamp == (2 * count - 1) * HALF_PERIOD_PS + 1000, 'VGA_CRC_TRACE_TIME'
            assert public < (1 << 15), 'VGA_CRC_TRACE_WIDTH'
            self.count = count
            yield timestamp, public

    def finish(self):
        assert self.ended and not self.pending and self.count == SAMPLES, 'VGA_CRC_TRACE_INCOMPLETE'
