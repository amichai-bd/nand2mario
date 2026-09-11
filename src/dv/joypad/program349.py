"""Original STOP/joypad-wake program and its contract-derived retirement table."""
import hashlib
import json
import sys

# Directions are selected before STOP, so a direction press is the wake source
# and an action press is not. STOP assembles to 10 00: no enabled request is
# pending, so the padding byte is consumed and PC advances by two.
BEFORE = [('DI', 'f3', 4, {}), ('XOR A,A', 'af', 4, {'f': 0x80}),
          ('LDH [$FF40],A', 'e040', 12, {}), ('LD A,$20', '3e20', 8, {'a': 0x20}),
          ('LDH [$FF00],A', 'e000', 12, {}), ('STOP', '1000', 4, {'stopped': 1})]
# The wake press is a selected-line fall, so IF bit 4 is also set by it and the
# effective mask holds the pressed direction across every resumed retirement.
AFTER = [('LD A,$5A', '3e5a', 8, {'a': 0x5a, 'stopped': 0, 'iflags': 0x10, 'buttons': 0x01}),
         ('LD [$C011],A', 'ea11c0', 16, {}), ('HALT', '76', 4, {'halted': 1})]
WAKE_READ_DOTS = 4


def build(root, destination):
    sys.path.insert(0, str(root / 'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    destination.mkdir(parents=True, exist_ok=True)
    rows = BEFORE + AFTER
    source = destination / 'program.asm'
    source.write_text('SECTION "code",ROM\nStart:\n' + '\n'.join(x[0] for x in rows)
                      + '\nEXPORT Start\n', encoding='utf-8')
    obj = assemble(source, destination, root / 'src/sw/generated/interfaces.inc')
    layout = {'schema_version': 1, 'sections': [
        {'unit': 'program.asm', 'section': 'code', 'region': 'ROM0', 'address': 512}]}
    image = package(link([('program.asm', obj)], layout,
                         {'unit': 'program.asm', 'symbol': 'Start'}), 'N2M STOP', 1)
    validate_image(image, 512, 'N2M STOP', 1)
    literal = b''.join(bytes.fromhex(x[1]) for x in rows)
    assert image[512:512 + len(literal)] == literal, 'STOP349_LITERAL_IMAGE'

    fields = dict(version=1, kind=0, epoch=2, seq=0, dot=0, pc_before=0, pc_after=0,
                  opcode=0, opcode_length=0, a=0, f=0, b=0, c=0, d=0, e=0, h=0, l=0,
                  sp=65534, ime=0, ime_delay=0, halted=0, stopped=0, halt_bug=0,
                  ie=0, iflags=0, buttons=0)
    events = []

    def append(pc, encoded, duration, changes, next_pc=None):
        data = bytes.fromhex(encoded)
        fields.update(changes)
        fields.update(seq=len(events), dot=fields['dot'] + duration, pc_before=pc,
                      pc_after=pc + len(data) if next_pc is None else next_pc,
                      opcode=int.from_bytes(data, 'little'), opcode_length=len(data))
        events.append(dict(fields))

    append(256, '00', 8, {})
    append(257, 'c30002', 16, {}, 512)
    pc = 512
    for _, encoded, duration, changes in BEFORE:
        append(pc, encoded, duration, changes)
        pc += len(bytes.fromhex(encoded))
    stop_dot = fields['dot']
    stop_pc = pc - 2
    resume_pc = pc
    entry_events = list(events)
    # STOP withholds emulated ticks, so no dot elapses while the CPU sleeps. The
    # wake spends one M-cycle reading the stored architectural PC afresh before
    # the first resumed instruction runs, so the schedule restarts four dots on.
    resumed = []
    for index, (_, encoded, duration, changes) in enumerate(AFTER):
        append(pc, encoded, duration + (WAKE_READ_DOTS if index == 0 else 0), changes)
        resumed.append(dict(events[-1]))
        pc += len(bytes.fromhex(encoded))
    digest = hashlib.sha256(image).hexdigest()
    assert digest == '3ba4fd710ccfbbd0aabd570e874e84116119744c165ed989097166d6812199af', 'STOP349_IMAGE_HASH'
    assert (len(entry_events), stop_dot, stop_pc, resume_pc) == (8, 68, 0x208, 0x20a), 'STOP349_SCHEDULE'
    record = dict(sha256=digest, entry_events=entry_events, stop_event=entry_events[-1],
                  resumed_events=resumed, stop_dot=stop_dot, stop_pc=stop_pc,
                  resume_pc=resume_pc, marker_address=0xc011, marker_value=0x5a,
                  marker_dot=resumed[1]['dot'] - 4, wake_dot=resumed[0]['dot'],
                  select_write=0x20, wake_buttons=0x01, inert_buttons=0x10)
    (destination / 'program.gb').write_bytes(image)
    (destination / 'stop349.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    return image
