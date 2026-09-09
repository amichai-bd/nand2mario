"""Render strict shade atlases as deterministic sprite review sheets (stdlib only)."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import struct
import subprocess
import sys
import zlib

from .assets import parse_shades, encode_shades
from .expressions import AssemblyError

# Tiny original 3x5 label glyphs. Both output formats use these exact pixels.
GLYPHS = dict(zip('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -', (
    '010101111101101','110101110101110','011100100100011','110101101101110',
    '111100110100111','111100110100100','011100101101011','101101111101101',
    '111010010010111','001001001101010','101101110101101','100100100100111',
    '101111111101101','101111111111101','010101101101010','110101110100100',
    '010101101111011','110101110101101','011100010001110','111010010010010',
    '101101101101111','101101101101010','101101111111101','101101010101101',
    '101101010010010','111001010100111','111101101101111','010110010010111',
    '110001010100111','110001010001110','101101111001001','111100110001110',
    '011100111101111','111001010010010','111101111101111','111101111001110',
    '000000000000000','000000111000000')))
PALETTE = ((255,255,255), (208,208,208), (104,104,104), (24,24,24))
CHECKER = ((228,228,240), (188,188,208))


def render(data, width=16, height=16, scale=8, mirror=False, labels=None):
    if any(type(n) is not int or n <= 0 or n % 8 for n in (width,height)):
        raise ValueError('frame dimensions must be positive multiples of 8')
    if type(scale) is not int or not 1 <= scale <= 32:
        raise ValueError('scale must be an integer from 1 to 32')
    if data['width'] % width or data['height'] % height:
        raise ValueError('frame dimensions must divide the atlas exactly')
    count = (data['width']//width)*(data['height']//height)
    if count > 64:
        raise ValueError('at most 64 frames per sheet')
    if labels is not None and (len(labels) != count or any(
            not re.fullmatch('[A-Z0-9 -]{1,20}', label) for label in labels)):
        raise ValueError('provide one 1..20 character uppercase ASCII label per frame')
    cell = max(width, max((4*len(s)-1 for s in labels), default=0) if labels else 0)
    stride = height + (7 if labels else 0) + 2
    w, h = 2 + count*(cell+2), 2 + stride*(2 if mirror else 1)
    if w*scale > 4096 or h*scale > 4096:
        raise ValueError('rendered dimensions must not exceed 4096 pixels')
    canvas = [[(250,250,250)]*w for _ in range(h)]
    columns = data['width']//width
    for facing in range(2 if mirror else 1):
        for frame in range(count):
            left, top = 2+frame*(cell+2), 2+facing*stride
            sx, sy = (frame%columns)*width, (frame//columns)*height
            for y in range(height):
                for x in range(width):
                    shade = data['pixels'][sy+y][sx+(width-1-x if facing else x)]
                    canvas[top+y][left+x] = PALETTE[shade] if shade else CHECKER[(x//2+y//2)%2]
            if labels:
                for i, char in enumerate(labels[frame]):
                    for j, bit in enumerate(GLYPHS[char]):
                        if bit == '1':
                            canvas[top+height+2+j//3][left+i*4+j%3] = PALETTE[3]
    return canvas


def png(canvas, scale):
    def chunk(name, data):
        return struct.pack('>I',len(data))+name+data+struct.pack('>I',zlib.crc32(name+data))
    rows = b''.join((b'\0'+b''.join(bytes(rgb)*scale for rgb in row))*scale for row in canvas)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',len(canvas[0])*scale,
            len(canvas)*scale,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows,9))+chunk(b'IEND',b''))


def svg(canvas, scale):
    w,h=len(canvas[0]),len(canvas)
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{w*scale}" height="{h*scale}" viewBox="0 0 {w} {h}" shape-rendering="crispEdges">']
    for y,row in enumerate(canvas):
        x=0
        while x<w:
            end=x+1
            while end<w and row[end]==row[x]: end+=1
            color='#'+''.join(f'{v:02x}' for v in row[x])
            lines.append(f'<rect x="{x}" y="{y}" width="{end-x}" height="1" fill="{color}"/>')
            x=end
    return ('\n'.join(lines+['</svg>'])+'\n').encode('utf-8')


def preview(root, source, tag, **options):
    options = {'width':16,'height':16,'scale':8,'mirror':False,'labels':None,**options}
    root = Path(root).resolve()
    source = Path(source).resolve()
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,63}',tag):
        raise ValueError('tag must contain 1..64 lowercase letters, digits, underscore or hyphen')
    base = root/'workdir'/'builds'
    folder = base/tag
    if not folder.resolve().is_relative_to(root) or folder.resolve()!=folder:
        raise ValueError('output path must not traverse symlinks or leave the worktree')
    source_bytes = source.read_bytes()
    data = parse_shades(source_bytes, source.name)
    canvas = render(data, **options)
    # Never replace a prior result or an input; the exclusive tag directory is the lock.
    folder.mkdir(parents=True, exist_ok=False)
    stage = folder/'sprite-preview'
    stage.mkdir()
    outputs = {'sheet.png':png(canvas,options.get('scale',8)),
               'sheet.svg':svg(canvas,options.get('scale',8)),
               'tiles.2bpp':encode_shades(data), 'source.json':source_bytes}
    hashes={}
    for name,content in outputs.items():
        (stage/name).write_bytes(content)
        hashes[name]=sha256(content).hexdigest()
    commit=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,check=True).stdout.strip()
    report={'status':'PASS','schema_version':1,'commit':commit,
            'source_sha256':hashes['source.json'],'options':options,
            'options_sha256':sha256(json.dumps(options,sort_keys=True).encode()).hexdigest(),
            'python':platform.python_version(),'zlib':zlib.ZLIB_RUNTIME_VERSION,
            'tools':{p.name:sha256(p.read_bytes()).hexdigest() for p in
                     (Path(__file__),Path(__file__).with_name('assets.py'),Path(__file__).with_name('expressions.py'))},
            'outputs':hashes}
    (stage/'result.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8',newline='\n')
    return stage


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--tag',required=True)
    parser.add_argument('--frame-width',type=int,default=16)
    parser.add_argument('--frame-height',type=int,default=16)
    parser.add_argument('--scale',type=int,default=8)
    parser.add_argument('--mirror',action='store_true')
    parser.add_argument('--labels',help='comma-separated uppercase labels in atlas row-major order')
    args=parser.parse_args()
    try:
        stage=preview(Path(__file__).resolve().parents[2],args.source,args.tag,
                      width=args.frame_width,height=args.frame_height,scale=args.scale,
                      mirror=args.mirror,labels=args.labels.split(',') if args.labels is not None else None)
    except (ValueError,OSError,AssemblyError,subprocess.SubprocessError) as error:
        print(f'FAIL: {error}',file=sys.stderr)
        return 1
    print(stage)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
