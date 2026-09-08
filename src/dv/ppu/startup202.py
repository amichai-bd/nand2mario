"""Original first-line OAM access witness with literal CPU expectations."""
import hashlib
import json
import sys
from pathlib import Path


def build(root, destination, case):
    if case not in ('read', 'write'):
        raise ValueError('unknown startup202 case')
    sys.path.insert(0, str(root/'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    destination.mkdir(parents=True, exist_ok=True)
    instructions = [('DI','f3',4,{}), ('XOR A,A','af',4,{'f':128}),
        ('LDH [$FF40],A','e040',12,{}), ('LD DE,$FE00','1100fe',12,{'d':254}),
        ('LD [DE],A','12',8,{}), ('LD A,$81','3e81',8,{'a':129}),
        ('LDH [$FF40],A','e040',12,{})]
    instructions += [('NOP','00',4,{})]*111
    if case == 'read':
        instructions += [('LD A,[DE]','1a',8,{'a':255})]
    else:
        instructions += [('LD [DE],A','12',8,{}), ('XOR A,A','af',4,{'a':0}),
            ('LDH [$FF40],A','e040',12,{}), ('LD A,[DE]','1a',8,{'a':129})]
    instructions += [('HALT','76',4,{'halted':1})]
    source=destination/'program.asm'
    source.write_text('SECTION "code",ROM\nStart:\n'+'\n'.join(x[0] for x in instructions)+'\nEXPORT Start\n')
    obj=assemble(source,destination,root/'src/sw/generated/interfaces.inc')
    layout={'schema_version':1,'sections':[{'unit':'program.asm','section':'code','region':'ROM0','address':512}]}
    linked=link([('program.asm',obj)],layout,{'unit':'program.asm','symbol':'Start'})
    image=package(linked,'N2M START',1)
    validate_image(image,512,'N2M START',1)
    literal=b''.join(bytes.fromhex(x[1]) for x in instructions)
    if image[512:512+len(literal)] != literal:
        raise ValueError('startup202 literal instruction bytes differ')
    fields=dict(version=1,kind=0,epoch=2,seq=0,dot=0,pc_before=0,pc_after=0,
        opcode=0,opcode_length=0,a=0,f=0,b=0,c=0,d=0,e=0,h=0,l=0,sp=65534,
        ime=0,ime_delay=0,halted=0,stopped=0,halt_bug=0,ie=0,iflags=0,buttons=0)
    events=[]
    def append(pc, data, duration, changes, next_pc=None):
        fields.update(changes)
        fields.update(seq=len(events),dot=fields['dot']+duration,pc_before=pc,
            pc_after=pc+len(data) if next_pc is None else next_pc,
            opcode=int.from_bytes(data,'little'),opcode_length=len(data))
        events.append(dict(fields))
    append(256,b'\x00',8,{})
    append(257,bytes.fromhex('c30002'),16,{},512)
    pc=512
    for _, encoded, duration, changes in instructions:
        data=bytes.fromhex(encoded);append(pc,data,duration,changes);pc+=len(data)
    hashes={'read':'9c335f748639e9d9449ffc4bc0a4743f00e4959bcbeaf62b53bf880438108b48',
        'write':'3bebeea4b7689829fdb2ac7c483a9fc73e402054c782b05852c3fda470307008'}
    if hashlib.sha256(image).hexdigest()!=hashes[case]:
        raise ValueError('declared startup202 image identity differs')
    record=dict(case=case,sha256=hashlib.sha256(image).hexdigest(),length=len(image),
        enable_commit=80,access_commit=532,access_retirement=536,halt_retirement=events[-1]['dot'],events=events)
    (destination/'program.gb').write_bytes(image)
    (destination/'startup202.json').write_text(json.dumps(record,indent=2)+'\n')
    return image
