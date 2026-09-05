"""Validate the interface source and render deterministic, checked-in ABI exports."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path("cfg/interfaces.json")
OUTPUTS = (Path("src/rtl/interfaces/n2m_interfaces_pkg.sv"),
           Path("tools/n2m/generated_interfaces.py"), Path("wiki/src/interface-tables.md"))


def keys(value, expected, location):
    if type(value) is not dict or set(value) != set(expected.split()):
        raise ValueError(f"{location}: expected exactly {expected}")


def integer(value, low, high, location):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{location}: integer outside {low}..{high}")


def name(value, pattern, location):
    if type(value) is not str or not re.fullmatch(pattern, value):
        raise ValueError(f"{location}: invalid name")


def prose(value):
    if type(value) is not str or not value or any(c in value for c in '\n\r|`<>'):
        raise ValueError("description must be plain single-line text")


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    data = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)
    validate(data)
    return data


def validate(data):
    """Closed schema v1: unknown keys, booleans, collisions and overflow fail."""
    keys(data, 'schema_version byte_order profile_name groups records commands references', 'source')
    integer(data['schema_version'], 1, 1, 'schema_version')
    if data['byte_order'] != 'little' or data['profile_name'] != 'dmg-direct-v1':
        raise ValueError('unsupported byte order or profile')
    keys(data['groups'], 'gb gb_reg gb_view vector profile host host_reg state button wire status trace frame command', 'groups')
    constants = {}
    for group, entries in data['groups'].items():
        if type(entries) is not list or not entries:
            raise ValueError('constant group must be nonempty list')
        for item in entries:
            keys(item, 'name bits value description', group)
            name(item['name'], '[A-Z][A-Z0-9_]*', group)
            integer(item['bits'], 1, 64, group)
            integer(item['value'], 0, (1 << item['bits']) - 1, item['name'])
            prose(item['description'])
            symbol = group.upper() + '_' + item['name']
            if symbol in constants:
                raise ValueError('duplicate constant: ' + symbol)
            constants[symbol] = item['value']
    if type(data['records']) is not dict or not data['records']:
        raise ValueError('records must be a nonempty object')
    for record, fields in data['records'].items():
        name(record, '[a-z][a-z0-9_]*', 'record')
        if type(fields) is not list or not fields:
            raise ValueError('record must contain fields')
        seen = set()
        for field in fields:
            keys(field, 'name bits description', record)
            name(field['name'], '[a-z][a-z0-9_]*', record)
            integer(field['bits'], 8, 64, record)
            if field['bits'] % 8 or field['name'] in seen:
                raise ValueError('duplicate field or non-byte width')
            seen.add(field['name'])
            prose(field['description'])
    if type(data['commands']) is not list or type(data['references']) is not list:
        raise ValueError('commands/references must be lists')
    command_names = []
    layouts = set(data['records']) | {'empty', 'bytes', 'offset+bytes'}
    for command in data['commands']:
        keys(command, 'name request response state', 'command')
        if command['request'] not in layouts or command['response'] not in layouts:
            raise ValueError('unknown command layout')
        prose(command['state'])
        command_names.append(command['name'])
    if command_names != [c['name'] for c in data['groups']['command']]:
        raise ValueError('command metadata must match command constants in order')
    for reference in data['references']:
        keys(reference, 'name revision license url purpose', 'reference')
        for value in reference.values():
            prose(value)
        name(reference['revision'], '[0-9a-f]{40}', 'reference revision')
    if not data['references']:
        raise ValueError('pinned references required')
    for group in ('gb_reg', 'host_reg', 'command', 'status', 'button', 'vector'):
        values = [row['value'] for row in data['groups'][group]]
        if len(values) != len(set(values)):
            raise ValueError('duplicate address/ID in ' + group)
    for row in data['groups']['gb_reg']:
        if not (0xff00 <= row['value'] <= 0xff7f or row['value'] == 0xffff) or row['bits'] != 16:
            raise ValueError('DMG register outside DMG I/O address space')
    for row in data['groups']['host_reg']:
        if row['value'] <= 0xffff or row['value'] % 4 or row['bits'] != 32:
            raise ValueError('host address overlaps DMG or is unaligned')
    # Ordered regions must cover the CPU space once; aliases are separate regions.
    cursor = 0
    for region in ('ROM0','ROM1','VRAM','CART_RAM','WRAM','ECHO','OAM','UNUSABLE','IO','HRAM','IE'):
        start, end = constants['GB_'+region+'_START'], constants['GB_'+region+'_END']
        if start != cursor or end < start:
            raise ValueError('overlapping or missing DMG region')
        cursor = end + 1
    if cursor != 65536:
        raise ValueError('DMG map does not cover 16 bits')
    if constants['PROFILE_ROM_BYTES'] != constants['GB_ROM1_END'] + 1 or constants['PROFILE_BANK_BYTES'] != constants['GB_ROM1_START']:
        raise ValueError('direct ROM mapping mismatch')
    if constants['FRAME_BYTES'] * 8 != constants['FRAME_WIDTH'] * constants['FRAME_HEIGHT'] * constants['FRAME_PIXEL_BITS']:
        raise ValueError('frame geometry mismatch')
    return constants


def render(data):
    constants = validate(data)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    mark = 'Generated from cfg/interfaces.json by tools/n2m/interfaces.py; DO NOT EDIT.'
    sv = ['// ' + mark, '// Source SHA-256: ' + digest, '`timescale 1ns/1ps', 'package n2m_interfaces_pkg;']
    py = ['"""' + mark + '\nSource SHA-256: ' + digest + '\n"""']
    md = ['# Interface tables', '', mark, '', 'Source SHA-256: `' + digest + '`.', '',
          'See [interface contracts](interface-contracts.md) for behavior, reset, framing and tests.', '']
    for group, items in data['groups'].items():
        md += ['## ' + group.replace('_', ' ').title(), '', '| Constant | Bits | Value | Meaning |', '|---|---|---|---|']
        for item in items:
            symbol = group.upper() + '_' + item['name']
            bits, value = item['bits'], item['value']
            sv.append(f"  localparam logic [{bits-1}:0] {symbol} = {bits}'h{value:X};")
            py.append(f'{symbol} = {value}')
            md.append(f"| `{symbol}` | {bits} | `0x{value:X}` | {item['description']} |")
        md.append('')
    for record, fields in data['records'].items():
        prefix = record.upper()
        size = sum(f['bits'] for f in fields) // 8
        sv.append(f'  localparam integer {prefix}_BYTES = {size};')
        py.append(f'{prefix}_BYTES = {size}')
        md += ['## ' + record.replace('_', ' ').title() + ' record', '', f'{size} bytes, in listed order; each field is unsigned little-endian.', '', '| Field | Byte offset | Bits | Meaning |', '|---|---|---|---|']
        offset = 0
        for field in fields:
            symbol = prefix + '_' + field['name'].upper() + '_OFFSET'
            sv.append(f'  localparam integer {symbol} = {offset};')
            py.append(f'{symbol} = {offset}')
            md.append(f"| `{field['name']}` | {offset} | {field['bits']} | {field['description']} |")
            offset += field['bits'] // 8
        sv.append('  typedef struct packed {')
        # First wire byte is the low byte of the packed vector, irrespective of host endian.
        for field in reversed(fields):
            sv.append(f"    logic [{field['bits']-1}:0] {field['name']};")
        sv.append(f'  }} {record}_t;')
        md.append('')
    sv += ['endpackage', '']
    py += ['', 'PROFILE_NAME = ' + repr(data['profile_name']),
           'HOST_REGISTERS = ' + repr({row['value']: row['name'] for row in data['groups']['host_reg']}),
           'RECORDS = ' + repr(data['records']),
           'COMMANDS = ' + repr(data['commands']), 'SOURCE_SHA256 = ' + repr(digest), '']
    md += ['## Commands', '', '| Name | Request payload | Successful response | Allowed state |', '|---|---|---|---|']
    md += [f"| `{c['name']}` | `{c['request']}` | `{c['response']}` | {c['state']} |" for c in data['commands']]
    md += ['', '## Provenance', '']
    md += [f"- [{r['name']}]({r['url']}), `{r['revision']}`, {r['license']}: {r['purpose']}." for r in data['references']]
    return dict(zip(OUTPUTS, ('\n'.join(sv), '\n'.join(py), '\n'.join(md)+'\n')))


def generate(root=ROOT, check=False):
    outputs = render(load(root / SOURCE))
    drift = []
    for path, text in outputs.items():
        target = root / path
        # Normalize checkout CRLF; content and missing final newline still cause drift.
        if check:
            if not target.exists() or target.read_text(encoding='utf-8') != text:
                drift.append(str(path))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding='utf-8', newline='\n')
    if drift:
        raise ValueError('interface generation drift: ' + ', '.join(drift))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        generate(check=args.check)
    except (ValueError, KeyError, TypeError) as error:
        parser.exit(1, f'{error}\n')
    print('PASS interface source and generated exports')


if __name__ == '__main__':
    main()
