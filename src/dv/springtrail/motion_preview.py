"""Reproduce approved-source motion previews, independent of DUT observations."""
import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from tools.sw.preview import PALETTE, svg, render
from composition_reference import approved, raster
from motion_frames import courier, tiles
from motion_render_reference import Check


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}', args.tag):
        parser.error('tag must use lowercase letters, digits, underscore or hyphen')
    output = ROOT/'workdir/builds'/args.tag/'motion-preview'
    output.mkdir(parents=True, exist_ok=False)
    pixels = Check().images[1]
    canvas = [[PALETTE[v] for v in pixels[y*160:(y+1)*160]] for y in range(144)]
    (output/'walk-skid.svg').write_bytes(svg(canvas, 4))
    # Thirteen source poses, each facing: padding aligns feet in 16x24 cells.
    frames, labels = [], []
    for pose in range(13):
        for left in (False, True):
            if pose == 12:
                values = bytes(128) + raster(courier(12,left),tiles(),16,16)
            else:
                values = approved(pose,left)
                if pose < 6:
                    values = bytes(128) + values
            frames.append(values)
            labels.append(f'{pose} {"L" if left else "R"}')
    data = dict(width=16*len(frames),height=24,
                pixels=[[v for frame in frames for v in frame[y*16:(y+1)*16]] for y in range(24)])
    canvas = render(data,width=16,height=24,scale=4,labels=labels)
    (output/'poses.svg').write_bytes(svg(canvas,4))
    print(output)


if __name__ == '__main__':
    main()
