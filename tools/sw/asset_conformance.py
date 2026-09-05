"""Independent pixel-by-pixel inverse check of actual ASSET software builds."""
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
from n2m.records import atomic_json, file_hash
from .rom_build import build_target


def decode_tiles(encoded, width, height):
    if len(encoded)!=width*height//4:
        raise ValueError('asset byte length mismatch')
    pixels=[]
    for y in range(height):
        row=[]
        for x in range(width):
            tile=(y//8)*(width//8)+(x//8)
            pair=tile*16+(y%8)*2
            place=2**(7-x%8)
            row.append((encoded[pair]//place)%2+2*((encoded[pair+1]//place)%2))
        pixels.append(row)
    return pixels


def compare_pixels(expected, decoded):
    for y,row in enumerate(expected):
        for x,value in enumerate(row):
            if decoded[y][x]!=value:
                raise ValueError(f'asset pixel mismatch x={x} y={y} expected={value} actual={decoded[y][x]}')


def proof(root, build, args, provenance):
    stage=build/'sw/asset-conformance'
    folder=stage/'runs'/uuid.uuid4().hex[:12];folder.mkdir(parents=True)
    report={'status':'FAIL',**provenance}
    try:
        built=build_target(root,build,SimpleNamespace(target='assets-basic',rebuild=False),provenance)
        if built['status']!='PASS':raise ValueError('asset build failed: '+built['error'])
        report['inputs']=built['inputs']
        report['build_result']=built
        source=root/'src/sw/assets/original-pattern/shades.json'
        expected=json.loads(source.read_text(encoding='utf-8'))
        original=next(root/name for name in built['artifacts'] if name.endswith('/asset-Pattern.2bpp')).read_bytes()
        encoded=bytearray(original)
        if args.mutate=='planes':
            for index in range(0,len(encoded),2):encoded[index],encoded[index+1]=encoded[index+1],encoded[index]
        elif args.mutate=='bitorder':
            encoded=bytearray(int(f'{value:08b}'[::-1],2) for value in encoded)
        (folder/'actual.2bpp').write_bytes(encoded)
        atomic_json(folder/'expected.json',expected)
        decoded=decode_tiles(encoded,expected['width'],expected['height'])
        atomic_json(folder/'decoded.json',decoded)
        compare_pixels(expected['pixels'],decoded)
        coverage={(x%8,y%8,value) for y,row in enumerate(decoded) for x,value in enumerate(row)}
        if len(coverage)!=256:raise ValueError('fixture must cover every local pixel position and shade')
        if encoded[:64]!=encoded[64:] or len(encoded)!=128:raise ValueError('duplicate tile row not preserved')
        rom=(root/built['rom']).read_bytes()
        if rom[513:641]!=original:raise ValueError('ASSET bytes differ in linked image')
        atomic_json(folder/'coverage.json',{'local_pixel_shade_bins':256,'pixels':512,'tiles':8,'duplicate_tiles':4,'rom_offset':513})
        report.update(status='PASS',pixels=512,tiles=8,local_pixel_shade_bins=256,build_result=built)
    except Exception as error:report['error']=str(error)
    report['artifacts']={**report.get('build_result',{}).get('artifacts',{}),
                         **{p.relative_to(root).as_posix():file_hash(p) for p in folder.iterdir() if p.is_file()}}
    atomic_json(folder/'result.json',report);atomic_json(stage/'result.json',report)
    return report
