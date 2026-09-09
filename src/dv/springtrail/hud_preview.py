"""Render fixed source-reference HUD views; these are not FPGA photographs."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.sw.preview import PALETTE, png, svg, render
from hud_reference import CHARS, glyph, image
from interactions_reference import Game, Player


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', args.tag):
        parser.error('tag must use lowercase letters, digits, underscore or hyphen')
    output = ROOT/'workdir/builds'/args.tag/'hud-preview'
    output.mkdir(parents=True, exist_ok=False)
    for name, game in (('title', Game()),
                       ('play', Game(mode=1, player=Player(x=120*16, y=12*16, camera=97)))):
        pixels = image(game)
        canvas = [[PALETTE[v] for v in pixels[y*160:(y+1)*160]] for y in range(144)]
        (output/f'{name}.svg').write_bytes(svg(canvas, 4))
        (output/f'{name}.png').write_bytes(png(canvas, 4))
    data = dict(width=8*len(CHARS), height=8,
                pixels=[[glyph(c)[y*8+x] for c in CHARS for x in range(8)] for y in range(8)])
    canvas = render(data, width=8, height=8, scale=4,
                    labels=[str(74+i) for i in range(len(CHARS))])
    (output/'glyphs.svg').write_bytes(svg(canvas, 4))
    (output/'glyphs.png').write_bytes(png(canvas, 4))
    print(output)


if __name__ == '__main__':
    main()
