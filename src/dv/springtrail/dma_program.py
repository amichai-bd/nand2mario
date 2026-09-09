"""Original CPU fixture linked with the game's exact publisher source."""
import hashlib
import json
from pathlib import Path
import sys


def build(root, destination, short=False):
    prior = sys.path[:]
    try:
        sys.path.insert(0, str(root/'tools'))
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package, validate_image
        destination.mkdir(parents=True, exist_ok=True)
        shared = (root/'src/sw/springtrail/oam_dma.asm').read_bytes()
        (destination/'oam_dma.asm').write_bytes(shared)
        # First image fills all40 entries, with nonzero last-byte attributes.
        first = [v for i in range(40) for v in (32+i//4*8, 16+i%4*8, i, (i%8)*16)]
        second = [48,32,3,0,48,40,4,32,56,32,5,64,56,40,6,96]+[0]*144
        lines=['SECTION "code",ROM','Start:','DI','LD SP,$DFFE','XOR A,A',
               'LDH [$FF40],A','LD [$FFFF],A','CALL InitSceneDMA']
        images=(first,) if short else (first,second)
        for index, data in enumerate(images):
            lines += ['LD HL,$C100']
            for value in data:
                lines += [f'LD A,${value:02X}','LD [HL+],A']
            lines += ['CALL PublishScene','LD HL,$FE00','LD DE,$C200','LD B,160',
                      f'Read{index}:','LD A,[HL+]','LD [DE],A','INC DE','DEC B',f'JR NZ,Read{index}',
                      f'LD A,{index+1}','LD [$C0FD],A']
        lines += ['LD A,$A5','LD [$C0FF],A','HALT','EXPORT Start',
                  'SECTION "publisher",ROM','INCLUDE "oam_dma.asm"']
        source=destination/'program.asm'
        source.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        obj=assemble(source,destination,root/'src/sw/generated/interfaces.inc')
        layout={'schema_version':1,'sections':[
            dict(unit='program.asm',section='code',region='ROM0',address=0x200),
            dict(unit='program.asm',section='publisher',region='ROM0',address=0x3000)]}
        image=package(link([('program.asm',obj)],layout,dict(unit='program.asm',symbol='Start')),'OAM DMA',1)
        validate_image(image,0x200,'OAM DMA',1)
        # Independent opcode anchor: source-page immediate and exact HRAM body.
        assert bytes.fromhex('3ec1cd80ffc9e0460628000520fcc9') in image, 'OAM_DMA_LITERAL'
        (destination/'program.gb').write_bytes(image)
        (destination/'oam_dma.json').write_text(json.dumps(dict(
            sha256=hashlib.sha256(image).hexdigest(),shared_sha256=hashlib.sha256(shared).hexdigest(),
            images=images,end_bound=22000),indent=2)+'\n')
        return image
    finally:
        sys.path[:]=prior
