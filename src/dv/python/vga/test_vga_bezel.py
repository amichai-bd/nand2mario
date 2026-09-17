"""One shell-bezel frame against an independent border model; no DUT imports.

The fixture runs two frame bridges on one stimulus and proves the image, sync,
observer stream and snapshot bytes are identical with and without the bezel.
This checker owns the border itself: every active pixel of one whole displayed
raster is compared against `bezel_reference`, which computes the shell from the
published direction and never reads the RTL's tile ROM, map or palette.
"""
import json
from pathlib import Path

import cocotb
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly, Timer
from cocotb.utils import get_sim_time

from bezel_reference import Shell

WIDTH, HEIGHT = 640, 480
LINE, FRAME_LINES = 800, 525
SAMPLES = 420000
GRAY = (15, 10, 5, 0)
ACTIVE_PIXELS = WIDTH * HEIGHT
IMAGE_PIXELS = 480 * 432


def frame():
    """One original asymmetric source frame; no shade is constant along a row or column."""
    return bytes(((x // 5) ^ (y // 3) ^ ((x * y) // 7) ^ (x + 2 * y) // 11) & 3
                 for y in range(144) for x in range(160))


def known(handle):
    value = handle.value
    assert value.is_resolvable, f'BEZEL_UNKNOWN {handle._name}={value}'
    return int(value)


class Model:
    """Expected public pins for every sample of one displayed raster."""

    def __init__(self, shades):
        self.shell = Shell()
        self.shades = shades
        self.border = 0
        self.image = 0
        self.seen = set()

    def expected(self, x, y):
        active = x < WIDTH and y < HEIGHT
        hsync = int(not 656 <= x < 752)
        vsync = int(not 490 <= y < 492)
        rgb = 0
        if active and self.shell.image(x, y):
            shade = GRAY[self.shades[(y - 24) // 3 * 160 + (x - 80) // 3]]
            rgb = (shade << 8) | (shade << 4) | shade
            self.image += 1
        elif active:
            rgb = self.shell.pixel(x, y)
            self.border += 1
        return (rgb << 2) | (hsync << 1) | vsync

    def sample(self, count, x, y, public):
        assert not public & (1 << 14), f'BEZEL_RESET_DURING_CAPTURE sample={count}'
        assert x < LINE and y < FRAME_LINES, f'BEZEL_COORDINATE x={x} y={y}'
        assert (x, y) not in self.seen, f'BEZEL_REPEATED_COORDINATE x={x} y={y}'
        self.seen.add((x, y))
        expected = self.expected(x, y)
        assert public == expected, (f'BEZEL_RGB sample={count} x={x} y={y} '
                                    f'expected={expected:04x} actual={public:04x}')

    def finish(self):
        assert len(self.seen) == SAMPLES, f'BEZEL_INCOMPLETE samples={len(self.seen)}'
        assert self.image == IMAGE_PIXELS and self.border == ACTIVE_PIXELS - IMAGE_PIXELS, (
            f'BEZEL_COVERAGE image={self.image} border={self.border}')


class Trace:
    """Strict ordered transport for the fixture's passive samples, not an oracle."""

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
            assert not self.ended, 'BEZEL_TRACE_AFTER_END'
            if line == 'END':
                assert self.count == SAMPLES, 'BEZEL_TRACE_SHORT'
                self.ended = True
                continue
            fields = line.split(',')
            assert len(fields) == 4, 'BEZEL_TRACE_FORMAT'
            count, x, y, public = (int(value, 16) for value in fields)
            assert count == self.count + 1 <= SAMPLES, 'BEZEL_TRACE_ORDER'
            self.count = count
            yield count, x, y, public

    def finish(self):
        assert self.ended and not self.pending and self.count == SAMPLES, 'BEZEL_TRACE_INCOMPLETE'


@cocotb.test()
async def vga_bezel(dut):
    shades = frame()
    journal = Path('transactions.jsonl').open('w', encoding='utf-8')

    def record(kind, **fields):
        journal.write(json.dumps({'kind': kind, 'time_ns': get_sim_time(unit='ns'), **fields}) + '\n')
        journal.flush()

    async def drive():
        await Timer(2000 - get_sim_time(unit='ns'), unit='ns')
        applied = bytearray()
        for index, shade in enumerate(shades):
            await FallingEdge(dut.clk_sys)
            dut.source_valid.value = 1
            dut.source_start.value = int(index == 0)
            dut.source_shade.value = shade
            dut.source_dot.value = index
            await RisingEdge(dut.clk_sys)
            await ReadOnly()
            assert known(dut.reset_sys) == 0
            actual = known(dut.source_shade)
            assert actual == shade, f'BEZEL_SOURCE index={index}'
            applied.append(actual)
        await FallingEdge(dut.clk_sys)
        dut.source_valid.value = 0
        dut.source_start.value = 0
        assert bytes(applied) == shades
        record('source_complete', count=len(applied))

    driver = cocotb.start_soon(drive())
    model = Model(shades)
    trace = Trace()
    stream = None
    try:
        # One continuous simulator run. Transfer the passive samples every 2 ms;
        # the fixture closes the trace after one whole displayed raster.
        for _ in range(22):
            await Timer(2, unit='ms')
            if stream is None:
                path = Path('public-raster.txt')
                if not path.exists():
                    continue
                stream = path.open(encoding='ascii')
            for count, x, y, public in trace.feed(stream.read()):
                try:
                    model.sample(count, x, y, public)
                except AssertionError as error:
                    record('mismatch', sample=count, x=x, y=y, actual=public, message=str(error))
                    raise
                if count % 105000 == 0:
                    record('raster_progress', sample=count, x=x, y=y)
            if trace.ended:
                break
        trace.finish()
        await driver
        model.finish()
        summary = {'status': 'PASS', 'samples': SAMPLES, 'image_pixels': model.image,
                   'border_pixels': model.border, 'border_colours': len(
                       {model.shell.pixel(x, y) for y in range(HEIGHT) for x in range(WIDTH)
                        if not model.shell.image(x, y)})}
        Path('summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        record('complete', **summary)
        dut._log.info('PASS vga-bezel shell border model image snapshot unchanged')
    finally:
        if stream is not None:
            stream.close()
        if not driver.done():
            driver.cancel()
        journal.close()
