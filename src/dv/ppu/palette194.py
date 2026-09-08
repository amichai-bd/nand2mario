"""Original palette-boundary program, packaged with the existing software tools."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools'))
from sw.assembler import assemble
from sw.linker import link
from sw.package import package, validate_image

TAIL='''LD BC,2510
PaletteDelay:
DEC BC
LD A,B
OR A,C
JR NZ,PaletteDelay
NOP
NOP
LD A,$00
LDH [$FF47],A
HALT
EXPORT Start'''


def build(root,destination,palette=0):
    if palette not in (0,0xfc):raise ValueError('unsupported palette194 case')
    original=root/'src/dv/integration'
    text=(original/'program.asm').read_text()
    if text.count('HALT\nEXPORT Start')!=1:
        raise ValueError('integration terminal instruction changed')
    destination.mkdir(parents=True,exist_ok=True)
    source=destination/'program.asm'
    source.write_text(text.replace('HALT\nEXPORT Start',TAIL.replace('LD A,$00',f'LD A,${palette:02X}')))
    obj=assemble(source,destination,root/'src/sw/generated/interfaces.inc')
    layout={'schema_version':1,'sections':[
        {'unit':'program.asm','section':'code','region':'ROM0','address':0x200},
        {'unit':'program.asm','section':'handler','region':'ROM0','vector':'VBLANK'}]}
    linked=link([('program.asm',obj)],layout,{'unit':'program.asm','symbol':'Start'})
    image=package(linked,'N2M PHASE',1)
    validate_image(image,0x200,'N2M PHASE',1)
    for event in json.loads((original/'program.json').read_text())['events']:
        if 'pc' not in event or event['instruction']=='HALT':continue
        address=int(event['pc'],16);literal=bytes.fromhex(event['bytes'])
        if image[address:address+len(literal)]!=literal:
            raise ValueError(f'unchanged setup differs at {address:04x}')
    if image[0x25b:0x26a]!=bytes.fromhex(f'01ce090b78b120fb00003e{palette:02x}e04776'):
        raise ValueError('palette delay/write literal differs')
    contract=json.loads((root/'src/dv/ppu/palette194.json').read_text())['images'][f'palette-{palette:02x}']
    if len(image)!=contract['length'] or hashlib.sha256(image).hexdigest()!=contract['sha256']:
        raise ValueError('declared palette194 image identity differs')
    (destination/'program.gb').write_bytes(image)
    (destination/'image.json').write_text(json.dumps({
        'sha256':hashlib.sha256(image).hexdigest(),'length':len(image),
        'lcdc_commit':592,'bgp_commit':70908,'bgp_retirement':70912,
        'halt_retirement':70916,'retirements':10114,'palette':palette},indent=2)+'\n')
    return image


if __name__=='__main__':
    for palette in (0xfc,0):build(ROOT,ROOT/f'workdir/builds/palette194-{palette:02x}-image',palette)
