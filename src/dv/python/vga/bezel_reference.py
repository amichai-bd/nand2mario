"""Independent border model for the handheld shell bezel; no DUT or ROM imports.

This computes the expected border colour of every active pixel outside the
scaled image straight from the shell rules of `wiki/src/rtl/vga/BEZEL.md` and
the editable colours in `tools/sw/vga_bezel/directions.json`. It never reads the
generated tile ROM, map or palette the RTL uses, so an encoding mistake in
`tools/n2m/vga_bezel_sources.py` fails the comparison. A host test checks this
model against the published preview renderer as well.
"""
import json
from pathlib import Path

WIDTH, HEIGHT = 640, 480
# Geometry authority: wiki/src/clocks-resets-cdc.md.
LEFT, TOP, RIGHT, BOTTOM = 80, 24, 560, 456
SOURCE = Path(__file__).resolve().parents[4] / 'tools/sw/vga_bezel/directions.json'


def rgb12(channels):
    """Three 4-bit VGA DAC codes as the 12-bit value the output register holds."""
    red, green, blue = channels
    for value in channels:
        if type(value) is not int or not 0 <= value <= 15:
            raise ValueError('a bezel colour is three 4-bit VGA codes')
    return (red << 8) | (green << 4) | blue


class Shell:
    """The shell border: one colour per active pixel outside the scaled image."""

    def __init__(self, path=SOURCE):
        spec = json.loads(Path(path).read_text(encoding='utf-8'))['shell']
        self.radius = spec['corner_radius']
        self.well, self.well_edge = spec['bands']['well'], spec['bands']['well_edge']
        self.colour = {name: rgb12(spec[name]) for name in
                       ('surround', 'body', 'body_high', 'body_low', 'well',
                        'well_edge', 'led', 'led_ring', 'grille')}
        self.stripe = [rgb12(value) for value in spec['stripe']]

    @staticmethod
    def image(x, y):
        return LEFT <= x < RIGHT and TOP <= y < BOTTOM

    @staticmethod
    def distance(x, y):
        """Outward Chebyshev distance in screen pixels from the scaled image."""
        return max(LEFT - x, x - (RIGHT - 1), TOP - y, y - (BOTTOM - 1), 0)

    def cut(self, x, y):
        """True on the four corner arcs the rounded outer rectangle removes."""
        radius = self.radius
        inset_x = min(x, WIDTH - 1 - x)
        inset_y = min(y, HEIGHT - 1 - y)
        if inset_x >= radius or inset_y >= radius:
            return False
        return inset_x ** 2 + inset_y ** 2 > (radius - 1) ** 2

    def pixel(self, x, y):
        """The shell's 12-bit colour at one border pixel, in rule order."""
        distance = self.distance(x, y)
        if not distance:
            raise ValueError(f'pixel {x},{y} is inside the scaled image')
        if self.cut(x, y):
            return self.colour['surround']
        if distance <= self.well:
            return self.colour['well']
        if distance <= self.well_edge:
            return self.colour['well_edge']
        # Bevelled outer rim: lit above and left, shaded below and right.
        rim = min(x, y, WIDTH - 1 - x, HEIGHT - 1 - y)
        if rim < 3:
            horizontal = rim in (x, WIDTH - 1 - x)
            lit = x < WIDTH // 2 if horizontal else y < HEIGHT // 2
            return self.colour['body_high' if lit else 'body_low']
        # Accent stripe: three bars of six lit columns on a seven-column pitch.
        if 12 <= x < 32 and 300 <= y < 452:
            bar, offset = divmod(x - 12, 7)
            if bar < 3 and offset < 6:
                return self.stripe[bar]
        # Power dot: a ringed disc above the left band.
        radius_squared = (x - 36) ** 2 + (y - 60) ** 2
        if radius_squared <= 36:
            return self.colour['led' if radius_squared <= 16 else 'led_ring']
        # Slanted speaker grille: three lit diagonals on a twelve-pixel pitch.
        if 592 <= x < 632 and 300 <= y < 452 and (x + y) % 12 < 3:
            return self.colour['grille']
        return self.colour['body']

    def frame(self):
        """Every active pixel's border colour, row-major, and None inside the image."""
        return [None if self.image(x, y) else self.pixel(x, y)
                for y in range(HEIGHT) for x in range(WIDTH)]
