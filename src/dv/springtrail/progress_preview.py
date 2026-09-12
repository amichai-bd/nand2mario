"""Render fixed source-reference progression views; not FPGA photographs."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.sw.preview import PALETTE, png, svg, render
from hud_reference import EXTRA, art, image
from motion_reference import Player
from progress_reference import World, PLAYING, TIMEUP, OVER, WON


# The published views; the test reproduces exactly these from the same sources.
VIEWS = (
    ('stage-two', World(mode=PLAYING, stage=1, lives=0x03, timer_high=0x02,
                        timer_low=0x68, player=Player(x=200 * 16, camera=128))),
    ('time-up', World(mode=TIMEUP, stage=1, lives=0x01, timer_high=0x00,
                      timer_low=0x00, expiring=0xFF, player=Player(x=200 * 16, camera=128))),
    ('game-over', World(mode=OVER, stage=2, lives=0x00, timer_high=0x00,
                        timer_low=0x47, player=Player(x=200 * 16, camera=128))),
    ('stage-clear', World(mode=WON, stage=2, lives=0x09, timer_high=0x01,
                          timer_low=0x25, player=Player(x=200 * 16, camera=128))),
)


def canvas_of(pixels):
    return [[PALETTE[v] for v in pixels[y * 160:(y + 1) * 160]] for y in range(144)]


def tile_sheet():
    data = dict(width=8 * len(EXTRA), height=8,
                pixels=[[art(name)[y * 8 + x] for name in EXTRA for x in range(8)]
                        for y in range(8)])
    return render(data, width=8, height=8, scale=4,
                  labels=[str(140 + index) for index in range(len(EXTRA))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', args.tag):
        parser.error('tag must use lowercase letters, digits, underscore or hyphen')
    output = ROOT / 'workdir/builds' / args.tag / 'progress-preview'
    output.mkdir(parents=True, exist_ok=False)
    for name, world in VIEWS:
        pixels = canvas_of(image(world))
        (output / f'{name}.svg').write_bytes(svg(pixels, 4))
        (output / f'{name}.png').write_bytes(png(pixels, 4))
    sheet = tile_sheet()
    (output / 'tiles.svg').write_bytes(svg(sheet, 4))
    (output / 'tiles.png').write_bytes(png(sheet, 4))
    print(output)


if __name__ == '__main__':
    main()
