"""Independent instruction-family fixture construction and actual RGBDS comparison.

This test-only fixed placement checks relocatable objects. It is not the product
linker, layout allocator or cartridge packager.
"""
import json
from pathlib import Path
import subprocess
import shutil
import uuid

from n2m.records import atomic_json, atomic_text, digest, file_hash
from n2m.rgbds import install
from .assembler import assemble
from .expressions import evaluate


def matrix():
    """Enumerate architectural families independently of imported opcode data."""
    cases = []
    def add(text, family):
        cases.append({'text': text, 'family': family})
    registers = ['B', 'C', 'D', 'E', 'H', 'L', '[HL]', 'A']
    pairs = ['BC', 'DE', 'HL', 'SP']
    for name in ['NOP', 'STOP', 'HALT', 'DI', 'EI', 'DAA', 'CPL', 'SCF', 'CCF',
                 'RLCA', 'RRCA', 'RLA', 'RRA', 'RET', 'RETI', 'JP HL']:
        add(name, 'fixed')
    for target in registers:
        for source in registers:
            if target != '[HL]' or source != '[HL]':
                add(f'LD {target},{source}', 'load-register')
        for value in [-128, 0, 255]:
            add(f'LD {target},{value}', 'load-byte-boundary')
        for operation in ['INC', 'DEC']:
            add(f'{operation} {target}', 'inc-dec-byte')
        for operation in ['ADD', 'ADC', 'SUB', 'SBC', 'AND', 'OR', 'XOR', 'CP']:
            add(f'{operation} A,{target}', 'alu-register')
        for operation in ['RLC', 'RRC', 'RL', 'RR', 'SLA', 'SRA', 'SWAP', 'SRL']:
            add(f'{operation} {target}', 'cb-shift')
        for bit in range(8):
            for operation in ['BIT', 'RES', 'SET']:
                add(f'{operation} {bit},{target}', 'cb-bit')
    for pair in pairs:
        for value in [-32768, 0, 65535]:
            add(f'LD {pair},{value}', 'load-word-boundary')
        for operation in ['INC', 'DEC']:
            add(f'{operation} {pair}', 'inc-dec-word')
        add(f'ADD HL,{pair}', 'add-word')
    for pointer in ['BC', 'DE', 'HL+', 'HL-']:
        add(f'LD [{pointer}],A', 'indirect-load')
        add(f'LD A,[{pointer}]', 'indirect-load')
    for value in [0, 65535]:
        for spelling in [f'LD [{value}],A', f'LD A,[{value}]', f'LD [{value}],SP']:
            add(spelling, 'address-boundary')
    for value in [65280, 65535]:
        add(f'LDH [{value}],A', 'high-address-boundary')
        add(f'LDH A,[{value}]', 'high-address-boundary')
    for spelling in ['LDH [C],A', 'LDH A,[C]', 'LD SP,HL']:
        add(spelling, 'special-load')
    for value in [-128, 0, 127]:
        add(f'ADD SP,{value}', 'signed-boundary')
        add(f'LD HL,SP+({value})', 'signed-boundary')
    for operation in ['ADD', 'ADC', 'SUB', 'SBC', 'AND', 'OR', 'XOR', 'CP']:
        for value in [-128, 0, 255]:
            add(f'{operation} A,{value}', 'alu-byte-boundary')
    for pair in ['BC', 'DE', 'HL', 'AF']:
        for operation in ['PUSH', 'POP']:
            add(f'{operation} {pair}', 'stack')
    for condition in ['', 'NZ,', 'Z,', 'NC,', 'C,']:
        for operation in ['JP', 'CALL']:
            for value in [0, 65535]:
                add(f'{operation} {condition}{value}', 'control-address-boundary')
        for displacement in [-128, 0, 127]:
            add(f'JR {condition}@+2+({displacement})', 'relative-boundary')
        if condition:
            add('RET ' + condition[:-1], 'conditional-return')
    for vector in range(0, 64, 8):
        add(f'RST {vector}', 'restart')
    return cases


def fixed_image(obj, base=512):
    """Apply one known test section at one fixed address; no layout decisions."""
    assert len(obj['sections']) == 1 and obj['sections'][0]['kind'] == 'ROM'
    section = obj['sections'][0]
    data = bytearray(section['data'])
    symbols = {name: value['expression'] for name, value in obj['symbols'].items()}
    for relocation in obj['relocations']:
        value = evaluate(relocation['expression'], symbols, {section['name']: base})
        assert relocation['minimum'] <= value <= relocation['maximum']
        assert not relocation['allowed'] or value in relocation['allowed']
        if relocation['kind'] == 'REL8':
            value -= base + relocation['offset'] + 1
            assert -128 <= value <= 127
        value = (value + relocation['bias']) << relocation['shift']
        width = 2 if relocation['kind'] in ('U16LE', 'ADDR16LE') else 1
        for index in range(width):
            mask = (relocation['mask'] >> (8 * index)) & 255
            position = relocation['offset'] + index
            data[position] = (data[position] & ~mask) | ((value >> (8 * index)) & mask)
    return bytes(data)


def conformance(root, build, args, provenance):
    stage = build / 'sw/conformance'
    folder = stage / 'runs' / uuid.uuid4().hex
    folder.mkdir(parents=True)
    report = {'status': 'FAIL', **provenance, 'commands': []}
    try:
        pin, tools, installation = install(root, stage / 'cache', args.offline)
        report['installation'] = installation
        report['inputs'] = {p.relative_to(root).as_posix(): file_hash(p)
                            for p in list((root / 'tools/sw').glob('*.py')) +
                            [root / 'tools/sw/opcodes.json', root / 'tools/sw/object.schema.json',
                             root / 'src/sw/generated/interfaces.inc', root / 'tools/n2m/dependencies.json']}
        report['inputs'].update({name: file_hash(root / name) for name in
                                ('tools/n2m/rgbds.py', 'tools/n2m/records.py',
                                 'tools/n2m/generated_interfaces.py', 'cfg/interfaces.json')})
        report['fingerprint'] = digest({'inputs': report['inputs'], 'installation': installation})
        cases = matrix()
        source = 'SECTION "code", ROM\n' + '\n'.join(case['text'] for case in cases) + '\n'
        atomic_text(folder / 'matrix.asm', source)
        obj = assemble(folder / 'matrix.asm', folder, root / 'src/sw/generated/interfaces.inc')
        atomic_json(folder / 'matrix.object.json', obj)
        actual = bytearray(fixed_image(obj))
        # Deliberate mutation tests the end-to-end byte comparator, not tool failure.
        if args.mutate:
            actual[0] ^= 1
        (folder / 'actual.bin').write_bytes(actual)
        oracle_source = 'SECTION "code", ROM0[$0200]\n' + '\n'.join(
            f'Case{index:04d}::\n' + case['text'] for index, case in enumerate(cases)) + '\nOracleEnd::\n'
        atomic_text(folder / 'oracle.asm', oracle_source)
        def run(command, name):
            report['commands'].append([str(item) for item in command])
            result = subprocess.run(command, cwd=folder, text=True, encoding='utf-8', errors='replace',
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            atomic_text(folder / (name + '.log'), result.stdout)
            atomic_json(folder / (name + '.exit.json'), {'returncode': result.returncode})
            if result.returncode or 'warning:' in result.stdout.lower():
                raise ValueError(f'{name} failed: exit {result.returncode}')
            return result.stdout.strip()
        for name, tool in tools.items():
            if run([tool, '--version'], name + '-version') != name + ' v' + pin['version']:
                raise ValueError('oracle version mismatch')
        run([tools['rgbasm'], '-Wall', '-Werror', '-o', folder / 'oracle.o', folder / 'oracle.asm'], 'assemble')
        run([tools['rgblink'], '-p', '255', '-o', folder / 'oracle.gb', '-n', folder / 'oracle.sym', folder / 'oracle.o'], 'link')
        oracle_symbols = {}
        for line in (folder / 'oracle.sym').read_text().splitlines():
            fields = line.split()
            if len(fields) == 2 and not line.startswith(';'):
                oracle_symbols[fields[1]] = int(fields[0].split(':')[1], 16)
        expected = (folder / 'oracle.gb').read_bytes()[512:oracle_symbols['OracleEnd']]
        if len(expected) != len(actual):
            raise ValueError(f'encoded size mismatch actual={len(actual)} expected={len(expected)}')
        (folder / 'expected.bin').write_bytes(expected)
        listing = obj['listing']
        base_opcodes, cb_opcodes = set(), set()
        for index, (case, line) in enumerate(zip(cases, listing)):
            offset, size = line['offset'], line['size']
            oracle_start = oracle_symbols[f'Case{index:04d}']
            oracle_end = oracle_symbols[f'Case{index + 1:04d}'] if index + 1 < len(cases) else oracle_symbols['OracleEnd']
            if offset != oracle_start - 512 or size != oracle_end - oracle_start:
                raise ValueError(f'instruction boundary mismatch case={index}')
            encoded = expected[offset:offset + size]
            if encoded[0] == 203:
                cb_opcodes.add(encoded[1])
            else:
                base_opcodes.add(encoded[0])
            case.update(offset=offset, size=size, expected=encoded.hex(), actual=bytes(actual[offset:offset + size]).hex())
        atomic_json(folder / 'coverage.json', {'cases': cases, 'base_opcodes': sorted(base_opcodes), 'cb_opcodes': sorted(cb_opcodes)})
        if len(base_opcodes) != 244 or len(cb_opcodes) != 256:
            raise ValueError(f'incomplete oracle coverage: base={len(base_opcodes)}, CB={len(cb_opcodes)}')
        report.update(cases=len(cases), base_opcodes=len(base_opcodes), cb_opcodes=len(cb_opcodes))
        if actual != expected:
            mismatch = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
            raise ValueError(f'encoding mismatch offset={mismatch} actual={actual[mismatch]:02x} expected={expected[mismatch]:02x}')
        report.update(status='PASS', cases=len(cases), base_opcodes=len(base_opcodes), cb_opcodes=len(cb_opcodes))
    except Exception as error:
        report['error'] = str(error)
    if (stage / 'cache').exists():
        shutil.copytree(stage / 'cache', folder / 'cache-snapshot')
    report['artifacts'] = {path.relative_to(root).as_posix(): file_hash(path) for path in folder.rglob('*') if path.is_file()}
    atomic_json(folder / 'result.json', report)
    atomic_json(stage / 'result.json', report)
    return report
