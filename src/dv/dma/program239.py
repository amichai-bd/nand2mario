"""Original HRAM DMA program and independent complete retirement expectations."""
import hashlib
import json
import sys


def build(root, destination):
    sys.path.insert(0, str(root / 'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    destination.mkdir(parents=True, exist_ok=True)
    rows = [('DI', 'f3', 4, {}), ('XOR A,A', 'af', 4, {'f': 0x80}),
        ('LDH [$FF40],A', 'e040', 12, {})]
    expected = [i ^ 0xa5 for i in range(160)]
    for i, value in enumerate(expected):
        rows += [(f'LD A,${value:02X}', f'3e{value:02x}', 8, {'a': value}),
            (f'LD [${0xc000+i:04X}],A', 'ea'+(0xc000+i).to_bytes(2, 'little').hex(), 16, {})]
    # Eleven HRAM bytes are copied with eleven two-instruction sequences.
    return_pc = 512 + sum(len(bytes.fromhex(x[1])) for x in rows) + 11*5 + 5
    hram = bytes.fromhex('e0460628000520fc') + b'\xc3' + return_pc.to_bytes(2, 'little')
    assert len(hram) == 11
    for i, value in enumerate(hram):
        rows += [(f'LD A,${value:02X}', f'3e{value:02x}', 8, {'a': value}),
            (f'LD [${0xff80+i:04X}],A', 'ea'+(0xff80+i).to_bytes(2, 'little').hex(), 16, {})]
    rows += [('LD A,$C0', '3ec0', 8, {'a': 0xc0}), ('JP $FF80', 'c380ff', 16, {})]
    after = [('LDH A,[$FF46]', 'f046', 12, {'a': 0xc0})]
    for i, value in enumerate(expected):
        after.append((f'LD A,[${0xfe00+i:04X}]', 'fa'+(0xfe00+i).to_bytes(2, 'little').hex(),
            16, {'a': value}))
    after += [('XOR A,A', 'af', 4, {'a': 0, 'f': 0x80}),
        ('LDH [$FF47],A', 'e047', 12, {}), ('LD A,$91', '3e91', 8, {'a': 0x91}),
        ('LDH [$FF40],A', 'e040', 12, {}), ('HALT', '76', 4, {'halted': 1})]
    source = destination / 'program.asm'
    source.write_text('SECTION "code",ROM\nStart:\n' + '\n'.join(x[0] for x in rows+after)
        + '\nEXPORT Start\n', encoding='utf-8')
    obj = assemble(source, destination, root/'src/sw/generated/interfaces.inc')
    layout = {'schema_version': 1, 'sections': [
        {'unit': 'program.asm', 'section': 'code', 'region': 'ROM0', 'address': 512}]}
    image = package(link([('program.asm', obj)], layout, {'unit': 'program.asm', 'symbol': 'Start'}),
        'N2M DMA', 1)
    validate_image(image, 512, 'N2M DMA', 1)
    literal = b''.join(bytes.fromhex(x[1]) for x in rows+after)
    assert image[512:512+len(literal)] == literal, 'DMA239_LITERAL_IMAGE'
    fields = dict(version=1, kind=0, epoch=2, seq=0, dot=0, pc_before=0, pc_after=0,
        opcode=0, opcode_length=0, a=0, f=0, b=0, c=0, d=0, e=0, h=0, l=0,
        sp=65534, ime=0, ime_delay=0, halted=0, stopped=0, halt_bug=0,
        ie=0, iflags=0, buttons=0)
    events = []

    def append(pc, encoded, duration, changes, next_pc=None):
        data = bytes.fromhex(encoded)
        fields.update(changes)
        fields.update(seq=len(events), dot=fields['dot']+duration, pc_before=pc,
            pc_after=pc+len(data) if next_pc is None else next_pc,
            opcode=int.from_bytes(data, 'little'), opcode_length=len(data))
        events.append(dict(fields))

    append(256, '00', 8, {})
    append(257, 'c30002', 16, {}, 512)
    pc = 512
    for _, encoded, duration, changes in rows:
        append(pc, encoded, duration, changes, 0xff80 if encoded == 'c380ff' else None)
        pc += len(bytes.fromhex(encoded))
    assert pc == return_pc
    append(0xff80, 'e046', 12, {})
    trigger = fields['dot'] - 4  # Accepted data T4 precedes closing fetch by four dots.
    append(0xff82, '0628', 8, {'b': 40})
    for old_b in range(40, 0, -1):
        append(0xff84, '00', 4, {})
        new_b = old_b-1
        flags = 0x40 | (0x80 if new_b == 0 else 0) | (0x20 if old_b & 15 == 0 else 0)
        append(0xff85, '05', 4, {'b': new_b, 'f': flags})
        append(0xff86, '20fc', 12 if new_b else 8, {}, 0xff84 if new_b else 0xff88)
    append(0xff88, hram[8:].hex(), 16, {}, return_pc)
    readbacks = []
    pc = return_pc
    lcd_commit = None
    for _, encoded, duration, changes in after:
        append(pc, encoded, duration, changes)
        if encoded.startswith('fa'):
            readbacks.append(dict(dot=fields['dot']-4, address=int.from_bytes(bytes.fromhex(encoded)[1:], 'little'),
                value=changes['a']))
        if encoded == 'e040':
            lcd_commit = fields['dot']-4
        pc += len(bytes.fromhex(encoded))
    digest = hashlib.sha256(image).hexdigest()
    assert digest == 'ea9083836660427fdf719e553c63cadc3d20638d1df6e26839ea56bf0fd56a47', 'DMA239_IMAGE_HASH'
    assert (len(events), trigger, lcd_commit, fields['dot']) == (638, 4180, 7608, 7616)
    record = dict(sha256=digest, events=events,
        hram_hex=hram.hex(), return_pc=return_pc, expected_oam=expected,
        trigger=trigger, first_transfer=trigger+8, last_transfer=trigger+644,
        readbacks=readbacks, lcd_commit=lcd_commit, halt_retirement=fields['dot'])
    (destination/'program.gb').write_bytes(image)
    (destination/'dma239.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')
    return image
