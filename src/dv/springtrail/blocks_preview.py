"""Render fixed block/item source-reference views; not FPGA photographs."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.sw.preview import PALETTE, png, svg, render
import blocks_reference as B
from blocks_frames import TERRAIN, atlas, image
from blocks_cases import playing, under
from power_reference import update

# The eight 16 by 16 designs the block layer loads, in VRAM order.
VIEWS = ((B.SEALED, 'SEALED'), (B.USED_TILE, 'USED'), (B.CRACK, 'CRACK'),
         (B.REVEAL, 'REVEAL'), (B.SHARDS, 'SHARDS'), (B.COIN_TILE, 'COIN'),
         (B.LEAF, 'LEAF'), (B.GEM, 'GEM'))


def sheet():
    """One row of eight 16 by 16 designs, composed from the approved atlas."""
    width = 16 * len(VIEWS)
    pixels = [[0] * width for _ in range(16)]
    for index, (base, _label) in enumerate(VIEWS):
        for piece, tile in enumerate(atlas(base)):
            ox, oy = 16 * index + 8 * (piece & 1), 8 * (piece >> 1)
            for y in range(8):
                pixels[oy + y][ox:ox + 8] = TERRAIN[y][tile * 8:tile * 8 + 8]
    return dict(width=width, height=16, pixels=pixels)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', args.tag):
        parser.error('tag must use lowercase letters, digits, underscore or hyphen')
    output = ROOT / 'workdir/builds' / args.tag / 'blocks-preview'
    output.mkdir(parents=True, exist_ok=False)
    canvas = render(sheet(), width=16, height=16, scale=4,
                    labels=[label for _base, label in VIEWS])
    (output / 'block-states.svg').write_bytes(svg(canvas, 4))
    (output / 'block-states.png').write_bytes(png(canvas, 4))
    # One in-world view: block 0 used, with its released leaf part way up.
    world = update(under(8), 16)
    for _ in range(10):
        world = update(world, 0)
    pixels = image(world)
    frame = [[PALETTE[v] for v in pixels[y * 160:(y + 1) * 160]] for y in range(144)]
    (output / 'release.svg').write_bytes(svg(frame, 4))
    (output / 'release.png').write_bytes(png(frame, 4))
    print(output)


if __name__ == '__main__':
    main()
