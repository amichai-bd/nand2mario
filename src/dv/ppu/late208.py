"""Original nonuniform late OAM witnesses; expectations precede DUT observation."""
from pathlib import Path
import sys, json, hashlib

HASHES = {
    'fe9c': 'f2af739bd5ba94be9d3bf8a14350b5ee7091afe8b5371193692d1407b8f0f24f',
    'fe9d': '642d672805a1c08f697218b73d449aa81acbb502017ebcbe0f5dae80e1b5afd7',
    'fe20': '2821829f9790d79acd37cba5954f9aba287ef35aa40f94b6b220c02a9523a24c',
}

def build(root, destination, case):
    if case not in HASHES:
        raise ValueError('unknown late208 case')
    sys.path.insert(0, str(root/'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    target=int(case,16)
    d=destination
    d.mkdir(parents=True,exist_ok=True)
    ins=[('DI','f3',4,{}),('XOR A,A','af',4,{'f':128}),('LDH [$FF40],A','e040',12,{}),('LD DE,$FE00','1100fe',12,{'d':254})]
    for i in range(160):
     value=(37*i+11)&255;nextaddr=0xFE01+i
     ins += [(f'LD A,${value:02X}',f'3e{value:02x}',8,{'a':value}),('LD [DE],A','12',8,{}),('INC DE','13',8,{'d':nextaddr>>8,'e':nextaddr&255})]
    ins += [(f'LD DE,${target:04X}','11'+target.to_bytes(2,'little').hex(),12,{'d':target>>8,'e':target&255}),('LD A,$81','3e81',8,{'a':129}),('LDH [$FF40],A','e040',12,{})]
    enable=24+sum(x[2] for x in ins)-4
    ins += [('NOP','00',4,{})]*131
    ins += [('LD [DE],A','12',8,{}),('XOR A,A','af',4,{'a':0,'f':128}),('LDH [$FF40],A','e040',12,{}),('HALT','76',4,{'halted':1})]
    source=d/'program.asm';source.write_text('SECTION "code",ROM\nStart:\n'+'\n'.join(x[0] for x in ins)+'\nEXPORT Start\n')
    obj=assemble(source,d,root/'src/sw/generated/interfaces.inc');layout={'schema_version':1,'sections':[{'unit':'program.asm','section':'code','region':'ROM0','address':512}]};image=package(link([('program.asm',obj)],layout,{'unit':'program.asm','symbol':'Start'}),'N2M OAM',1);validate_image(image,512,'N2M OAM',1)
    literal=b''.join(bytes.fromhex(x[1]) for x in ins);assert image[512:512+len(literal)]==literal
    state=dict(version=1,kind=0,epoch=2,seq=0,dot=0,pc_before=0,pc_after=0,opcode=0,opcode_length=0,a=0,f=0,b=0,c=0,d=0,e=0,h=0,l=0,sp=65534,ime=0,ime_delay=0,halted=0,stopped=0,halt_bug=0,ie=0,iflags=0,buttons=0)
    events=[]
    def append(pc,data,duration,change,nxt=None):
     state.update(change);state.update(seq=len(events),dot=state['dot']+duration,pc_before=pc,pc_after=pc+len(data) if nxt is None else nxt,opcode=int.from_bytes(data,'little'),opcode_length=len(data));events.append(dict(state))
    append(256,b'\0',8,{});append(257,bytes.fromhex('c30002'),16,{},512);pc=512
    for _,encoded,duration,change in ins:
     data=bytes.fromhex(encoded);append(pc,data,duration,change);pc+=len(data)
    if hashlib.sha256(image).hexdigest() != HASHES[case]:
        raise ValueError('declared late208 image differs')
    oam=[(37*i+11)&255 for i in range(160)]
    if case=='fe20':
        oam[32:40]=[0x81,0x90,0x4d,0x72,0x97,0xbc,0xe1,0x06]
    else:
        oam[target-0xfe00]=0x81
    record=dict(case=case,sha256=HASHES[case],target=target,enable_commit=3924,
                access_commit=4456,access_retirement=4460,halt_retirement=4480,
                events=events,oam=oam)
    (d/'program.gb').write_bytes(image)
    (d/'late208.json').write_text(json.dumps(record,indent=2)+'\n')
    return image
