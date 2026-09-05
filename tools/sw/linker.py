"""Deterministic placement and relocation of validated version-one objects."""
from copy import deepcopy
import re
from n2m import generated_interfaces as hw
from .expressions import AssemblyError, evaluate
from .objects import validate

ROM_REGIONS = ('ROM0', 'ROM1')
RAM_REGIONS = ('VRAM', 'WRAM', 'OAM', 'HRAM')
REGIONS = {name: (getattr(hw, 'GB_' + name + '_START'), getattr(hw, 'GB_' + name + '_END') + 1)
           for name in ROM_REGIONS + RAM_REGIONS}
VECTORS = {name.removeprefix('VECTOR_'): value for name, value in vars(hw).items() if name.startswith('VECTOR_')}


def fail(code, cause, span=None, **context):
    error = AssemblyError(code, cause, span or {'file': 'layout.json', 'line': 1, 'column': 1}, **context)
    error.diagnostic['stage'] = 'link'
    raise error


def mapping_profile(profile):
    if profile != 'dmg-direct-v1':
        fail('PROFILE_MISMATCH', 'only dmg-direct-v1 is supported')
    if not (hw.GB_ROM0_START == 0 and hw.GB_ROM0_END + 1 == hw.GB_ROM1_START == hw.PROFILE_BANK_BYTES
            and hw.GB_ROM1_END + 1 == hw.PROFILE_ROM_BYTES == 2 * hw.PROFILE_BANK_BYTES
            and hw.PROFILE_HEADER_START == 0x100 and hw.PROFILE_HEADER_END == 0x14f):
        fail('PROFILE_MISMATCH', 'generated direct profile has incompatible CPU-to-file mapping')


def reserved():
    return [(hw.PROFILE_HEADER_START, hw.PROFILE_HEADER_END + 1, 'header')] + [
        (address, address + hw.PROFILE_VECTOR_SLOT_BYTES, name) for name, address in VECTORS.items()]


def validate_layout(layout, objects):
    if type(layout) is not dict or set(layout) != {'schema_version', 'sections'}:
        fail('SCHEMA_MISMATCH', 'layout requires schema_version and sections')
    if type(layout['schema_version']) is not int or layout['schema_version'] != 1 or type(layout['sections']) is not list:
        fail('SCHEMA_MISMATCH', 'unsupported layout schema')
    available = {(unit, s['name']): s for unit, obj in objects for s in obj['sections']}
    rows = {}
    for item in layout['sections']:
        if (type(item) is not dict or not {'unit', 'section', 'region'} <= item.keys()
                or item.keys() - {'unit', 'section', 'region', 'address', 'alignment', 'vector'}):
            fail('SCHEMA_MISMATCH', 'unknown or missing layout fields')
        if any(type(item[k]) is not str for k in ('unit', 'section', 'region')):
            fail('SCHEMA_MISMATCH', 'layout names must be strings')
        key = (item['unit'], item['section'])
        if key not in available or key in rows:
            fail('LAYOUT_SECTION', 'duplicate or absent layout section', section=item['section'], unit=item['unit'])
        section = available[key]
        row = {'address': None, 'alignment': 1, 'vector': None, **item}
        region, address, alignment = row['region'], row['address'], row['alignment']
        if region not in (ROM_REGIONS if section['kind'] == 'ROM' else RAM_REGIONS):
            fail('LAYOUT_REGION', 'absent or incompatible allocation region', section=key[1], unit=key[0])
        if type(alignment) is not int or not 1 <= alignment <= 65536 or alignment & (alignment - 1):
            fail('ALIGNMENT', 'alignment must be a power of two in 1..65536', section=key[1])
        if address is not None and (type(address) is not int or not 0 <= address <= 65535 or address % alignment):
            fail('ALIGNMENT', 'fixed address must be aligned and in CPU range', section=key[1])
        vector = row['vector']
        if vector is not None:
            if type(vector) is not str or vector not in VECTORS or region != 'ROM0':
                fail('RESERVATION', 'unknown or non-ROM0 vector slot', section=key[1])
            if address not in (None, VECTORS[vector]) or VECTORS[vector] % alignment or section['size'] > hw.PROFILE_VECTOR_SLOT_BYTES:
                fail('RESERVATION', 'vector section must fit its named slot at the slot address', section=key[1])
            row['address'] = VECTORS[vector]
        rows[key] = row
    if rows.keys() != available.keys():
        fail('LAYOUT_SECTION', 'every object section must be assigned exactly once')
    return rows


def link(objects, layout, entry, profile='dmg-direct-v1'):
    mapping_profile(profile)
    if type(objects) is not list or not objects:
        fail('MALFORMED_OBJECT', 'ordered nonempty unit/object list required')
    seen = set()
    for item in objects:
        if type(item) not in (tuple, list) or len(item) != 2:
            fail('MALFORMED_OBJECT', 'each unit requires its object')
        unit, obj = item
        if (type(unit) is not str or not unit or unit.startswith('/') or ':' in unit or '\\' in unit
                or '..' in unit.split('/') or unit in seen):
            fail('PRIVATE_PATH', 'unique target-relative source unit required')
        seen.add(unit)
        try:
            validate(obj)
        except AssemblyError as error:
            error.diagnostic.update(stage='link', unit=unit)
            raise
    rows = validate_layout(layout, objects)
    units = dict(objects)
    exports = {}
    for unit, obj in objects:
        for name in obj['exports']:
            if name in exports:
                other = exports[name]
                fail('DUPLICATE_SYMBOL', 'export is globally ambiguous', obj['symbols'][name]['span'],
                     symbol=name, unit=unit, other_unit=other, other_span=units[other]['symbols'][name]['span'])
            exports[name] = unit
    for unit, obj in objects:
        for name in obj['imports']:
            if name not in exports:
                fail('UNDEFINED_SYMBOL', 'import has no exported definition', {'file': unit, 'line': 1, 'column': 1}, unit=unit, symbol=name)
    order = [(unit, s) for unit, obj in objects for s in obj['sections']]
    placements = {}
    occupied = []
    for fixed in (True, False):
        for unit, section in order:
            key = (unit, section['name']); row = rows[key]
            if (row['address'] is not None) != fixed:
                continue
            start, end = REGIONS[row['region']]
            blocked = [(a, b) for a, b, _ in occupied]
            if section['kind'] == 'ROM':
                blocked += [(a, b) for a, b, name in reserved() if name != row['vector']]
            size = section['size']; alignment = row['alignment']
            address = row['address'] if fixed else (start + alignment - 1) & -alignment
            if not fixed and size:
                for a, b in sorted(blocked):
                    if address < b and address + size > a:
                        address = (b + alignment - 1) & -alignment
            if address < start or address >= end or address + size > end:
                fail('OVERFLOW' if fixed else 'EXHAUSTION', 'section does not fit its region/bank', section['span'], unit=unit, section=key[1])
            if size and any(address < b and address + size > a for a, b in blocked):
                fail('OVERLAP', 'section overlaps allocation or reservation', section['span'], unit=unit, section=key[1])
            placements[key] = address
            if size:
                occupied.append((address, address + size, key))
    values = {}
    def symbol(unit, name, chain=()):
        key = (unit, name)
        obj = units[unit]
        if name not in obj['symbols']:
            if name not in obj['imports'] or name not in exports:
                fail('UNDEFINED_SYMBOL', 'unimported or absent cross-unit symbol', unit=unit, symbol=name)
            return symbol(exports[name], name, chain)
        if key in chain:
            fail('CYCLIC_SYMBOL', 'cyclic cross-unit expression', obj['symbols'][name]['span'], symbol=name, unit=unit,
                 chain=['::'.join(k) for k in (*chain, key)])
        if key not in values:
            try:
                values[key] = expression(unit, obj['symbols'][name]['expression'], (*chain, key))
            except AssemblyError as error:
                error.diagnostic.update(stage='link', unit=unit, symbol=name, span=obj['symbols'][name]['span'])
                raise
        return values[key]
    def expression(unit, node, chain=()):
        if node['op'] == 'symbol': return symbol(unit, node['name'], chain)
        if node['op'] == 'address': return placements[(unit, node['section'])] + node['offset']
        if node['op'] == 'integer': return node['value']
        return evaluate({'op': node['op'], 'args': [{'op': 'integer', 'value': expression(unit, arg, chain)} for arg in node['args']]}, {})
    for unit, obj in objects:
        for name in obj['symbols']: symbol(unit, name)
    data = {(unit, s['name']): bytearray(s['data']) for unit, s in order}
    applied = {}
    for unit, obj in objects:
        for relocation in obj['relocations']:
            key = (unit, relocation['section'])
            try:
                value = expression(unit, relocation['expression'])
                if not relocation['minimum'] <= value <= relocation['maximum'] or (relocation['allowed'] and value not in relocation['allowed']):
                    fail('RANGE', 'relocation value violates operand constraint', relocation['span'], unit=unit, section=key[1])
                encoded = value
                if relocation['kind'] == 'REL8':
                    encoded -= placements[key] + relocation['offset'] + 1
                    if not -128 <= encoded <= 127:
                        fail('RANGE', 'relative branch displacement outside -128..127', relocation['span'], unit=unit, section=key[1])
                encoded = (encoded + relocation['bias']) << relocation['shift']
                width = 2 if relocation['kind'] in ('U16LE', 'ADDR16LE') else 1
                for index in range(width):
                    mask = (relocation['mask'] >> (8 * index)) & 255
                    offset = relocation['offset'] + index
                    data[key][offset] = (data[key][offset] & ~mask) | ((encoded >> (8 * index)) & mask)
                applied.setdefault(key, []).append({'offset': relocation['offset'], 'kind': relocation['kind'], 'value': value, 'encoded': encoded})
            except AssemblyError as error:
                error.diagnostic.update(stage='link', span=relocation['span'], unit=unit, section=key[1])
                raise
    if type(entry) is not dict or set(entry) != {'unit', 'symbol'} or type(entry['unit']) is not str or entry['unit'] not in units or type(entry['symbol']) is not str:
        fail('ENTRY', 'explicit unit and symbol entry required')
    address = symbol(entry['unit'], entry['symbol'])
    boundaries = {placements[(unit, line['section'])] + line['offset'] for unit, obj in objects for line in obj['listing'] if line['instruction']}
    if address not in boundaries or any(a <= address < b for a, b, _ in reserved()):
        fail('ENTRY', 'entry must target an emitted instruction boundary outside reservations', symbol=entry['symbol'])
    image = bytearray([255] * hw.PROFILE_ROM_BYTES)
    maps = []
    for unit, section in order:
        key = (unit, section['name']); start = placements[key]
        file_offset = start if section['kind'] == 'ROM' else None
        if file_offset is not None: image[start:start + section['size']] = data[key]
        maps.append({'unit': unit, 'section': key[1], 'kind': section['kind'], 'region': rows[key]['region'],
                     'address': start, 'size': section['size'], 'file_offset': file_offset})
    symbols = [{'name': unit + '::' + name, 'unit': unit, 'symbol': name, 'value': value,
                'visibility': 'export' if name in units[unit]['exports'] else 'local'} for (unit, name), value in sorted(values.items())]
    listing = []
    for unit, obj in objects:
        for line in obj['listing']:
            key = (unit, line['section']); start = line['offset']; end = start + line['size']
            listing.append({'unit': unit, 'section': key[1], 'span': deepcopy(line['span']), 'address': placements[key] + start,
                            'size': line['size'], 'bytes': list(data[key][start:end]), 'instruction': line['instruction'],
                            'relocations': [r for r in applied.get(key, []) if start <= r['offset'] < end]})
    return {'image': bytes(image), 'entry': address,
            'map': {'schema_version': 1, 'sections': sorted(maps, key=lambda m: (m['address'], m['section'], m['unit']))},
            'symbols': {'schema_version': 1, 'symbols': symbols}, 'listing': {'schema_version': 1, 'lines': listing}}
