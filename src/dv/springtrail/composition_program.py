"""Finite actual-CPU cases linked with unchanged game composition routines."""
import hashlib
import json
from pathlib import Path
import sys


def build(root,destination,short=False):
    prior=sys.path[:]
    try:
        sys.path[:0]=[str(root/'tools'),str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from composition_cases import cases
        from interaction_cases import ADDRESSES,state_bytes
        destination.mkdir(parents=True,exist_ok=True)
        source=root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        selected=cases()[:1] if short else cases()
        lines=['SECTION "code",ROM','Start:','DI','LD SP,$DFFE','XOR A,A',
               'LDH [$FF40],A','LD [$FFFF],A']
        def write(address,value):
            lines.extend([f'LD A,${value&255:02X}',f'LD [${address:04X}],A'])
        def word(address,value):
            write(address,value);write(address+1,value>>8)
        for index,case in enumerate(selected):
            # Poison once initially and once before the first full scene.
            # Per-case ordered writes already prove each courier result.
            if index in (0,28):lines += ['LD HL,$C100','LD B,160','LD A,$A5',f'Poison{index}:',
                      'LD [HL+],A','DEC B',f'JR NZ,Poison{index}']
            if case['kind']=='courier':
                for address,value in ((0xc041,case['pose']),(0xc040,32*case['left']),
                        (0xc03b,case['hidden'])):write(address,value)
                word(0xc042,case['x']);word(0xc044,case['y'])
                lines += ['LD DE,$C100']
                write(0xc0fc,index+1)
                lines += ['CALL ComposeCourier']
            else:
                for address,value in zip(ADDRESSES,state_bytes(case['game'],case['buttons'])):
                    write(address,value)
                write(0xc040,32)
                if case['kind']=='game':lines += ['CALL UpdateGame']
                # The main loop marks initial/restarted state for publication.
                write(0xc02e,1)
                write(0xc0fc,index+1)
                lines += ['CALL PrepareScene']
            write(0xc0fd,index+1)
        write(0xc0ff,0xa5)
        lines += ['HALT','EXPORT Start']
        for name in ('movement','render','world','collision','interactions','map_restore','scene','stream'):
            lines += [f'INCLUDE "{name}.asm"']
        path=destination/'program.asm'
        path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        obj=assemble(path,destination,root/'src/sw/generated/interfaces.inc')
        layout=json.loads((source/'layout.json').read_text())
        layout['sections']=[dict(row,unit='program.asm') for row in layout['sections'] if row['section']!='assets']
        linked=link([('program.asm',obj)],layout,dict(unit='program.asm',symbol='Start'))
        image=package(linked,'COURIER CASES',1)
        (destination/'program.gb').write_bytes(image)
        record=dict(sha256=hashlib.sha256(image).hexdigest(),cases=len(selected),
                    shared_sections={row['section']:hashlib.sha256(image[row['address']:row['address']+row['size']]).hexdigest() for row in linked['map']['sections'] if row['section']!='code'},
                    end_bound=10000 if short else 260000)
        (destination/'composition.json').write_text(json.dumps(record,indent=2)+'\n')
        (destination/'composition-listing.json').write_text(json.dumps(linked['listing'],indent=2)+'\n')
        return image
    finally:
        sys.path[:]=prior
