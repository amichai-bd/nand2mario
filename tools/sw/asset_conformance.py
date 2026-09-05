"""Independent pixel-by-pixel inverse check of actual ASSET software builds."""
import json
from pathlib import Path
from types import SimpleNamespace
import uuid
from n2m.records import atomic_json, file_hash
from .rom_build import build_target
from .assets import encode_shades


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


def mutate_bytes(original, mutation):
    encoded=bytearray(original)
    if mutation=='planes':
        for index in range(0,len(encoded),2):encoded[index],encoded[index+1]=encoded[index+1],encoded[index]
    elif mutation=='bitorder':encoded=bytearray(int(f'{value:08b}'[::-1],2) for value in encoded)
    elif mutation=='columns':
        for index,value in enumerate(encoded):
            a=(value>>7)&1;b=(value>>3)&1
            encoded[index]=(value&~0x88)|(a<<3)|(b<<7)
    elif mutation=='rows':
        for tile in range(0,len(encoded),16):
            encoded[tile:tile+2],encoded[tile+8:tile+10]=encoded[tile+8:tile+10],encoded[tile:tile+2]
    elif mutation=='tiles':encoded[:16],encoded[16:32]=encoded[16:32],encoded[:16]
    return bytes(encoded)


def basis_proof(mutation=None, evidence=None):
    # A moving nonzero pixel distinguishes positions even where periodic
    # integration patterns repeat. No DUT-derived expected permutation exists.
    from hashlib import sha256
    digest=sha256();cases=[]
    for case in range(769):
        pixels=[[0]*16 for _ in range(16)]
        if case:
            position=(case-1)//3;shade=1+(case-1)%3;x=position%16;y=position//16
            pixels[y][x]=shade
        else:x=y=shade=0
        value={'schema_version':1,'width':16,'height':16,'pixels':pixels}
        encoded=mutate_bytes(encode_shades(value),mutation)
        decoded=decode_tiles(encoded,16,16)
        try:compare_pixels(pixels,decoded)
        except ValueError as error:
            if evidence is not None:
                atomic_json(evidence/'basis-failure.json',{'case':case,'expected':value,'actual_pixels':decoded,'actual_hex':encoded.hex(),'mutation':mutation})
            raise ValueError(f'asset basis case={case}: {error}') from error
        digest.update(encoded)
        cases.append({'case':case,'x':x,'y':y,'shade':shade,'encoded_sha256':sha256(encoded).hexdigest()})
    return {'cases':cases,'case_count':769,'width':16,'height':16,'ordered_encoded_sha256':digest.hexdigest()}


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
        metadata_file=next(root/name for name in built['artifacts'] if name.endswith('/assets.json'))
        metadata=json.loads(metadata_file.read_text(encoding='utf-8'))
        original=next(root/name for name in built['artifacts'] if name.endswith('/'+metadata['Pattern']['file'])).read_bytes()
        encoded=mutate_bytes(original,args.mutate)
        (folder/'actual.2bpp').write_bytes(encoded)
        atomic_json(folder/'expected.json',expected)
        decoded=decode_tiles(encoded,expected['width'],expected['height'])
        atomic_json(folder/'decoded.json',decoded)
        compare_pixels(expected['pixels'],decoded)
        coverage={(x%8,y%8,value) for y,row in enumerate(decoded) for x,value in enumerate(row)}
        if len(coverage)!=256:raise ValueError('fixture must cover every local pixel position and shade')
        if encoded[:64]!=encoded[64:] or len(encoded)!=128:raise ValueError('duplicate tile row not preserved')
        basis=basis_proof(args.mutate,folder)
        atomic_json(folder/'basis.json',basis)
        rom=(root/built['rom']).read_bytes()
        if rom[513:641]!=original:raise ValueError('ASSET bytes differ in linked image')
        atomic_json(folder/'coverage.json',{'local_pixel_shade_bins':256,'pixels':512,'tiles':8,'duplicate_tiles':4,'rom_offset':513})
        report.update(status='PASS',pixels=512,tiles=8,local_pixel_shade_bins=256,basis_cases=769,build_result=built)
    except Exception as error:report['error']=str(error)
    report['artifacts']={**report.get('build_result',{}).get('artifacts',{}),
                         **{p.relative_to(root).as_posix():file_hash(p) for p in folder.iterdir() if p.is_file()}}
    atomic_json(folder/'result.json',report);atomic_json(stage/'result.json',report)
    return report
