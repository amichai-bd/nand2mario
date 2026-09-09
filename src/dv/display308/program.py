"""Original finite setup and literal ISR encodings, using the existing assembler."""
import hashlib
import json
import sys


def build(root, destination):
    sys.path.insert(0,str(root/'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    destination.mkdir(parents=True,exist_ok=True)
    rows=[]
    def emit(text,encoded,dots):
        rows.append((text,bytes.fromhex(encoded),dots))
    def store(address,value):
        emit(f'LD A,${value:02X}',f'3e{value:02x}',8)
        emit(f'LD [${address:04X}],A','ea'+address.to_bytes(2,'little').hex(),16)
    emit('DI','f3',4)
    emit('LD SP,$FFFE','31feff',12)
    emit('XOR A,A','af',4)
    emit('LDH [$FF40],A','e040',12)
    # Original tile bytes are deliberately specified separately from scene.py.
    tiles=[]
    for color in range(4):
        tiles.extend([255 if color&1 else 0,255 if color&2 else 0]*8)
    tiles.extend([0xaa,0]*8)
    tiles.extend([0,255]*8)
    for y in range(8):tiles.extend([0x80 if y<3 else 0,255])
    for i,value in enumerate(tiles):store(0x8000+i,value)
    for y in range(5):
        for x in range(32):store(0x9800+y*32+x,(x+y)%4)
    oam=[36,24,4,0,36,28,5,0,36,28,6,0,36,40,5,0x80,36,64,6,0x60]+[0]*140
    for i,value in enumerate(oam):store(0xc000+i,value)
    hram=bytes.fromhex('e0460628000520fcc9')
    for i,value in enumerate(hram):store(0xff80+i,value)
    for address,value in ((0xff47,0xe4),(0xff48,0xe4),(0xff49,0xe4),
                          (0xff42,0),(0xff43,0),(0xff45,15),(0xff41,0x40),
                          (0xffff,3),(0xff0f,0)):
        store(address,value)
    emit('LD A,$93','3e93',8)
    emit('LDH [$FF40],A','e040',12)
    lcd_commit=24+sum(row[2] for row in rows)-4
    emit('EI','fb',4)
    emit('NOP','00',4)
    halt_pc=0x400+sum(len(row[1]) for row in rows)
    emit('HALT','76',4)
    emit(f'JR ${halt_pc:04X}','18fd',12)
    # Vector JP, AF save and mode read have a conservative 68-dot entry bound.
    stat=bytes.fromhex('f5f041e60320fa3e08e043e042f1d9')
    vblank=bytes.fromhex('f5c5afe043e0423ec0cd80ffc1f1d9')
    source=destination/'program.asm'
    source.write_text('SECTION "code",ROM\nStart:\n'+'\n'.join(row[0] for row in rows)+
        '\nEXPORT Start\nSECTION "stat",ROM\nPUSH AF\nWait:\nLDH A,[$FF41]\nAND A,$03\nJR NZ,Wait\nLD A,$08\nLDH [$FF43],A\nLDH [$FF42],A\nPOP AF\nRETI\n'+
        'SECTION "vblank",ROM\nPUSH AF\nPUSH BC\nXOR A,A\nLDH [$FF43],A\nLDH [$FF42],A\nLD A,$C0\nCALL $FF80\nPOP BC\nPOP AF\nRETI\n'+
        'SECTION "vb_vector",ROM\nJP $0340\nSECTION "stat_vector",ROM\nJP $0300\n',encoding='utf-8')
    obj=assemble(source,destination,root/'src/sw/generated/interfaces.inc')
    layout={'schema_version':1,'sections':[dict(unit='program.asm',section=name,region='ROM0',address=address)
        for name,address in (('code',0x400),('stat',0x300),('vblank',0x340),('vb_vector',0x40),('stat_vector',0x48))]}
    layout['sections'][3]['vector']='VBLANK'
    layout['sections'][4]['vector']='STAT'
    image=package(link([('program.asm',obj)],layout,dict(unit='program.asm',symbol='Start')),'N2M DISPLAY',1)
    validate_image(image,0x400,'N2M DISPLAY',1)
    for address,data in ((0x400,b''.join(row[1] for row in rows)),(0x300,stat),
                         (0x340,vblank),(0x40,bytes.fromhex('c34003')),(0x48,bytes.fromhex('c30003'))):
        assert image[address:address+len(data)]==data,'DISPLAY308_LITERAL_IMAGE'
    record=dict(sha256=hashlib.sha256(image).hexdigest(),lcd_commit=lcd_commit,
        halt_pc=halt_pc,hram_hex=hram.hex(),stat_hex=stat.hex(),vblank_hex=vblank.hex(),
        expected_oam=oam,short_end=lcd_commit+1024,end=lcd_commit+70224+32*456)
    (destination/'program.gb').write_bytes(image)
    (destination/'display308.json').write_text(json.dumps(record,indent=2)+'\n')
    return image
