"""Original v0.5 timer program and contract-derived ordered retirement table."""
import hashlib
import json
import sys


def build(root, destination):
    sys.path.insert(0, str(root / 'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    destination.mkdir(parents=True, exist_ok=True)
    before = [('DI','f3',4,{}), ('LD SP,$DFFE','31fedf',12,{'sp':0xdffe}),
        ('XOR A,A','af',4,{'f':128}), ('LDH [$FF40],A','e040',12,{})]
    before += [('NOP','00',4,{})] * 64
    before += [('LDH A,[$FF04]','f004',12,{'a':1}), ('XOR A,A','af',4,{'a':0}),
        ('LDH [$FF04],A','e004',12,{}), ('LDH A,[$FF04]','f004',12,{}),
        ('LD A,$3C','3e3c',8,{'a':0x3c}), ('LDH [$FF05],A','e005',12,{}),
        ('LDH A,[$FF05]','f005',12,{}), ('LD A,$42','3e42',8,{'a':0x42}),
        ('LDH [$FF06],A','e006',12,{}), ('LDH A,[$FF06]','f006',12,{}),
        ('XOR A,A','af',4,{'a':0}), ('LDH [$FF07],A','e007',12,{}),
        ('LDH A,[$FF07]','f007',12,{'a':0xf8}), ('LD A,$04','3e04',8,{'a':4}),
        ('LD [$FFFF],A','eaffff',16,{'ie':4}), ('XOR A,A','af',4,{'a':0}),
        ('LDH [$FF0F],A','e00f',12,{}), ('LD A,$FF','3eff',8,{'a':255}),
        ('LDH [$FF05],A','e005',12,{}), ('LD A,$04','3e04',8,{'a':4}),
        ('LDH [$FF07],A','e007',12,{}), ('XOR A,A','af',4,{'a':0}),
        ('LDH [$FF04],A','e004',12,{}), ('EI','fb',4,{'ime_delay':1}),
        ('NOP','00',4,{'ime':1,'ime_delay':0}), ('HALT','76',4,{'halted':1})]
    handler = [('LD A,$7B','3e7b',8,{'a':0x7b}),
        ('LD [$C010],A','ea10c0',16,{}), ('RETI','d9',16,{'ime':1,'sp':0xdffe})]
    after = [('DI','f3',4,{'ime':0}), ('XOR A,A','af',4,{'a':0}),
        ('LDH [$FF07],A','e007',12,{}), ('LDH A,[$FF05]','f005',12,{'a':0x42}),
        ('LD A,[$C010]','fa10c0',16,{'a':0x7b}), ('XOR A,A','af',4,{'a':0}),
        ('LD [$FFFF],A','eaffff',16,{'ie':0}), ('LD A,$91','3e91',8,{'a':0x91}),
        ('LDH [$FF40],A','e040',12,{}), ('HALT','76',4,{'halted':1})]
    source=destination/'program.asm'
    source.write_text('SECTION "code",ROM\nStart:\n'+'\n'.join(x[0] for x in before+after)+
        '\nEXPORT Start\nSECTION "handler",ROM\n'+'\n'.join(x[0] for x in handler)+'\n',encoding='utf-8')
    obj=assemble(source,destination,root/'src/sw/generated/interfaces.inc')
    layout={'schema_version':1,'sections':[{'unit':'program.asm','section':'code','region':'ROM0','address':512},
        {'unit':'program.asm','section':'handler','region':'ROM0','vector':'TIMER'}]}
    image=package(link([('program.asm',obj)],layout,{'unit':'program.asm','symbol':'Start'}),'N2M TIMER',1)
    validate_image(image,512,'N2M TIMER',1)
    for pc,rows in ((512,before+after),(0x50,handler)):
        literal=b''.join(bytes.fromhex(row[1]) for row in rows)
        assert image[pc:pc+len(literal)]==literal,'TIMER234_LITERAL_IMAGE'
    fields=dict(version=1,kind=0,epoch=2,seq=0,dot=0,pc_before=0,pc_after=0,
        opcode=0,opcode_length=0,a=0,f=0,b=0,c=0,d=0,e=0,h=0,l=0,sp=65534,
        ime=0,ime_delay=0,halted=0,stopped=0,halt_bug=0,ie=0,iflags=0,buttons=0)
    events=[]
    def append(pc,data,duration,changes,next_pc=None):
        fields.update(changes)
        fields.update(seq=len(events),dot=fields['dot']+duration,pc_before=pc,
            pc_after=pc+len(data) if next_pc is None else next_pc,
            opcode=int.from_bytes(data,'little'),opcode_length=len(data))
        events.append(dict(fields))
    append(256,b'\x00',8,{})
    append(257,bytes.fromhex('c30002'),16,{},512)
    pc=512
    for _,encoded,duration,changes in before:
        data=bytes.fromhex(encoded);append(pc,data,duration,changes);pc+=len(data)
    resume=pc
    assert fields['dot']==552
    # DIV commit536; overflow+1024, reload+1028, next T3/T4 wake+1032;
    # five-M-cycle interrupt entry closes20 dots after wake. No idle records.
    append(resume,b'',1588-fields['dot'],{'kind':1,'ime':0,'halted':0,'sp':0xdffc},0x50)
    pc=0x50
    for _,encoded,duration,changes in handler:
        data=bytes.fromhex(encoded)
        append(pc,data,duration,{'kind':0,**changes},resume if encoded=='d9' else None);pc+=len(data)
    pc=resume
    for _,encoded,duration,changes in after:
        data=bytes.fromhex(encoded);append(pc,data,duration,changes);pc+=len(data)
    assert fields['dot']==1720
    digest=hashlib.sha256(image).hexdigest()
    assert digest=='b6a4563d974f59e32db513d9f032c2dee8f40dc5782e26b6a2fa44ab9797b032','TIMER234_IMAGE_HASH'
    record=dict(sha256=digest,events=events,anchor=536,overflow=1560,reload=1564,wake=1568,
        irq=1588,marker_commit=1608,lcd_commit=1712,halt_retirement=1720)
    (destination/'program.gb').write_bytes(image)
    (destination/'timer234.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    return image
