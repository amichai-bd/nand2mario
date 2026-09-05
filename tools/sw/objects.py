"""Strict version-one relocatable object validation, shared with future linker."""
import re

from .expressions import AssemblyError, check_cycles, references

IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')
KINDS = {'U8': 1, 'U16LE': 2, 'ADDR16LE': 2, 'REL8': 1, 'HIGH8': 1, 'LOW8': 1}


def require(condition, cause):
    if not condition:
        raise AssemblyError('MALFORMED_OBJECT', cause)


def fields(value, names):
    require(type(value) is dict and set(value) == set(names.split()), 'unknown or missing object fields')


def integer(value, minimum=0, maximum=65536):
    require(type(value) is int and minimum <= value <= maximum, 'invalid integer or range')


def span(value):
    fields(value, 'file line column')
    require(type(value['file']) is str and value['file'] and '\\' not in value['file']
            and not value['file'].startswith('/') and ':' not in value['file']
            and '..' not in value['file'].split('/'), 'invalid source path')
    integer(value['line'], 1, 2**31 - 1)
    integer(value['column'], 1, 2**31 - 1)


def expression(node, sections, depth=0):
    require(depth < 64 and type(node) is dict, 'invalid expression depth/type')
    op = node.get('op')
    if op == 'integer':
        fields(node, 'op value')
        require(type(node['value']) is int, 'expression integer required')
    elif op == 'symbol':
        fields(node, 'op name')
        require(type(node['name']) is str and IDENTIFIER.fullmatch(node['name']), 'invalid symbol name')
    elif op == 'address':
        fields(node, 'op section offset')
        require(node['section'] in sections, 'expression references missing section')
        integer(node['offset'], 0, sections[node['section']]['size'])
    else:
        fields(node, 'op args')
        require(op in ('+', '-', '~', '*', '/', '<<', '>>', '&', '^', '|', 'LOW', 'HIGH'), 'unknown expression operator')
        require(type(node['args']) is list, 'expression arguments required')
        count = len(node['args'])
        require(count in ((1, 2) if op in ('+', '-') else (1,) if op in ('~', 'LOW', 'HIGH') else (2,)), 'wrong expression arity')
        for arg in node['args']:
            expression(arg, sections, depth + 1)


def _validate(obj):
    fields(obj, 'schema_version sources sections symbols exports imports relocations listing')
    if obj['schema_version'] != 1 or type(obj['schema_version']) is not int:
        raise AssemblyError('SCHEMA_MISMATCH', 'unsupported object schema version')
    require(type(obj['sources']) is dict and obj['sources'], 'source hashes required')
    for name, sha in obj['sources'].items():
        span({'file': name, 'line': 1, 'column': 1})
        require(type(sha) is str and re.fullmatch('[0-9a-f]{64}', sha), 'invalid source hash')
    require(type(obj['sections']) is list, 'ordered sections required')
    sections = {}
    for section in obj['sections']:
        fields(section, 'name kind data size span')
        require(type(section['name']) is str and section['name'] and section['name'] not in sections, 'duplicate/invalid section')
        require(section['kind'] in ('ROM', 'RAM'), 'invalid section kind')
        integer(section['size'])
        require(type(section['data']) is list, 'byte array required')
        for byte in section['data']:
            integer(byte, 0, 255)
        require(len(section['data']) == (section['size'] if section['kind'] == 'ROM' else 0), 'inconsistent section length')
        span(section['span'])
        sections[section['name']] = section
    require(type(obj['symbols']) is dict, 'symbols required')
    for name, definition in obj['symbols'].items():
        require(IDENTIFIER.fullmatch(name), 'invalid symbol')
        fields(definition, 'expression span')
        expression(definition['expression'], sections)
        span(definition['span'])
    for visibility in ('exports', 'imports'):
        values = obj[visibility]
        require(type(values) is list and all(type(v) is str and IDENTIFIER.fullmatch(v) for v in values), 'invalid visibility names')
        require(len(values) == len(set(values)), 'duplicate visibility name')
    require(set(obj['exports']) <= obj['symbols'].keys(), 'export has no definition')
    require(not set(obj['imports']) & obj['symbols'].keys(), 'import also defined locally')
    occupied = set()
    require(type(obj['relocations']) is list, 'relocations required')
    for relocation in obj['relocations']:
        fields(relocation, 'kind section offset expression minimum maximum mask shift bias allowed span')
        kind, section = relocation['kind'], relocation['section']
        require(kind in KINDS and section in sections and sections[section]['kind'] == 'ROM', 'invalid relocation kind/section')
        width = KINDS[kind]
        integer(relocation['offset'], 0, sections[section]['size'] - width)
        positions = {(section, relocation['offset'] + i) for i in range(width)}
        require(not occupied & positions, 'overlapping relocations')
        occupied |= positions
        integer(relocation['minimum'], -32768, 65535)
        integer(relocation['maximum'], relocation['minimum'], 65535)
        integer(relocation['mask'], 1, 65535 if width == 2 else 255)
        integer(relocation['shift'], 0, 7)
        integer(relocation['bias'], -65535, 65535)
        require(type(relocation['allowed']) is list, 'allowed relocation values required')
        for value in relocation['allowed']:
            integer(value, relocation['minimum'], relocation['maximum'])
        expression(relocation['expression'], sections)
        span(relocation['span'])
        shape = (relocation['minimum'], relocation['maximum'], relocation['mask'],
                 relocation['shift'], relocation['bias'], tuple(relocation['allowed']))
        if kind in ('U16LE', 'ADDR16LE'):
            require(shape == (-32768 if kind == 'U16LE' else 0, 65535, 65535, 0, 0, ()), 'invalid word relocation constraint')
        elif kind == 'REL8':
            require(shape == (0, 65535, 255, 0, 0, ()), 'invalid relative relocation constraint')
        else:
            permitted = [(-128, 255, 255, 0, 0, ()), (-128, 127, 255, 0, 0, ()),
                         (0, 7, 56, 3, 0, ()), (0, 56, 56, 0, 0, tuple(range(0, 57, 8)))]
            # High-memory address bounds are carried explicitly by the producer;
            # the patch must still map precisely to an unsigned byte.
            high_address = shape[1] - shape[0] == 255 and shape[2:] == (255, 0, -shape[0], ())
            require(shape in permitted or high_address, 'invalid byte relocation constraint')
    require(type(obj['listing']) is list, 'listing required')
    for line in obj['listing']:
        fields(line, 'section offset size instruction span')
        require(line['section'] in sections and type(line['instruction']) is bool, 'invalid listing section/instruction')
        integer(line['offset'], 0, sections[line['section']]['size'])
        integer(line['size'], 0, sections[line['section']]['size'] - line['offset'])
        span(line['span'])
    definitions = {name: value['expression'] for name, value in obj['symbols'].items()}
    for node in list(definitions.values()) + [r['expression'] for r in obj['relocations']]:
        require(set(references(node)) <= definitions.keys() | set(obj['imports']), 'undeclared expression symbol')
    check_cycles(definitions)
    return obj


def validate(obj):
    try:
        return _validate(obj)
    except (KeyError, TypeError, AttributeError, RecursionError) as error:
        raise AssemblyError('MALFORMED_OBJECT', 'invalid object structure or nesting') from error
