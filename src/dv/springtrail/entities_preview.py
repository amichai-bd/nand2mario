"""Reproduce the two approved-source entity reference scenes."""
import argparse
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from tools.sw.preview import PALETTE,svg
from entities_render_program import SCENES
from entities_frames import image

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    args=parser.parse_args()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',args.tag):parser.error('invalid tag')
    out=ROOT/'workdir/builds'/args.tag/'entity-preview';out.mkdir(parents=True,exist_ok=False)
    for name,world in SCENES.items():
        pixels=image(world)
        canvas=[[PALETTE[v] for v in pixels[y*160:(y+1)*160]] for y in range(144)]
        (out/(name+'.svg')).write_bytes(svg(canvas,4))
    print(out)
if __name__=='__main__':main()
