"""Original SM83 assembler. Placement and cartridge packaging belong to the linker."""
import hashlib
import json
from pathlib import Path
import re

from .expressions import AssemblyError, Unresolved, check_cycles, evaluate, parse, references
from .objects import validate

FORMS = json.loads(Path(__file__).with_name('opcodes.json').read_text())['forms']
RESERVED = {row['form'].split()[0].upper() for row in FORMS} | {
    'A', 'B', 'C', 'D', 'E', 'H', 'L', 'AF', 'BC', 'DE', 'HL', 'SP', 'NZ', 'Z', 'NC',
    'SECTION', 'ROM', 'RAM', 'EQU', 'EXPORT', 'IMPORT', 'DB', 'DW', 'DS', 'INCLUDE', 'ASSET', 'LOW', 'HIGH'}
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z0-9_]*\Z')


def split(text, delimiter=','):
    result, start, quoted, escaped, depth = [], 0, False, False, 0
    for index, char in enumerate(text):
        if escaped:
            escaped = False
        elif quoted and char == '\\':
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif not quoted:
            if char in '([':
                depth += 1
            elif char in ')]':
                depth -= 1
            elif char == delimiter and depth == 0:
                result.append(text[start:index].strip())
                start = index + 1
    if quoted or depth:
        raise AssemblyError('SYNTAX', 'unclosed string or operand delimiter')
    result.append(text[start:].strip())
    return result


def string(text):
    if len(text) < 2 or text[0] != '"' or text[-1] != '"':
        raise AssemblyError('SYNTAX', 'quoted string required')
    result, index = '', 1
    while index < len(text) - 1:
        char = text[index]
        index += 1
        if char == '"':
            raise AssemblyError('SYNTAX', 'unexpected quote')
        if char == '\\':
            if index >= len(text) - 1:
                raise AssemblyError('SYNTAX', 'unfinished escape')
            escape = text[index]
            index += 1
            if escape == 'x':
                digits = text[index:index + 2]
                if not re.fullmatch('[0-9a-fA-F]{2}', digits):
                    raise AssemblyError('SYNTAX', 'invalid hexadecimal escape')
                char = chr(int(digits, 16))
                index += 2
            elif escape in ('\\', '"', 'n', 'r', 't'):
                char = {'\\': '\\', '"': '"', 'n': '\n', 'r': '\r', 't': '\t'}[escape]
            else:
                raise AssemblyError('SYNTAX', 'unsupported string escape')
        result += char
    return result


def identifier(name):
    if not IDENTIFIER.fullmatch(name) or name.upper() in RESERVED:
        raise AssemblyError('SYNTAX', f'invalid or reserved identifier {name!r}')
    return name


def source_lines(source, tree, sources, stack=()):
    resolved = source.resolve()
    if not resolved.is_relative_to(tree) or source.is_symlink():
        raise AssemblyError('PRIVATE_PATH', 'include escapes target tree')
    relative = resolved.relative_to(tree).as_posix()
    if relative in stack:
        raise AssemblyError('INCLUDE_CYCLE', 'include cycle: ' + ' -> '.join((*stack, relative)), include_stack=list(stack))
    try:
        data = resolved.read_bytes()
        text = data.decode('utf-8')
    except (OSError, UnicodeError) as error:
        raise AssemblyError('SYNTAX', f'unreadable UTF-8 source: {relative}') from error
    if text.startswith('\ufeff'):
        raise AssemblyError('SYNTAX', 'UTF-8 BOM is unsupported')
    if relative.startswith(('__n2m__/', '__assets__/')):
        raise AssemblyError('PRIVATE_PATH', 'source path uses reserved generated namespace')
    sources[relative] = hashlib.sha256(text.replace('\r\n', '\n').encode('utf-8')).hexdigest()
    for number, line in enumerate(text.splitlines(), 1):
        # A semicolon ends a statement only outside a quoted string.
        quoted, escaped, end = False, False, len(line)
        for index, char in enumerate(line):
            if escaped:
                escaped = False
            elif quoted and char == '\\':
                escaped = True
            elif char == '"':
                quoted = not quoted
            elif char == ';' and not quoted:
                end = index
                break
        statement = line[:end].strip()
        location = {'file': relative, 'line': number, 'column': len(line) - len(line.lstrip()) + 1}
        if not statement:
            continue
        if re.match(r'INCLUDE\b', statement, re.I):
            name = string(statement.split(None, 1)[1])
            path = Path(name)
            if path.is_absolute() or '..' in path.parts or ':' in name or '\\' in name:
                raise AssemblyError('PRIVATE_PATH', 'include path must stay in target tree', location)
            try:
                yield from source_lines(resolved.parent / path, tree, sources, (*stack, relative))
            except AssemblyError as error:
                if not error.diagnostic['span']['file']:
                    error.diagnostic['span'] = location
                error.diagnostic.setdefault('include_stack', list((*stack, relative)))
                raise
        else:
            yield statement, location


def assemble(source, tree, prelude, assets=None):
    tree, source = Path(tree).resolve(), Path(source).resolve()
    obj = {'schema_version': 1, 'sources': {}, 'sections': [], 'symbols': {}, 'exports': [],
           'imports': [], 'relocations': [], 'listing': []}
    lines = list(source_lines(source, tree, obj['sources']))
    generated = Path(prelude).read_bytes()
    obj['sources']['__n2m__/interfaces.inc'] = hashlib.sha256(generated.replace(b'\r\n', b'\n')).hexdigest()
    prelude_lines = [(line, {'file': '__n2m__/interfaces.inc', 'line': i, 'column': 1})
                     for i, line in enumerate(generated.decode('utf-8').splitlines(), 1)
                     if line and not line.startswith(';')]
    lines = prelude_lines + lines
    symbols, equates, section = {}, {}, None
    for name, data in (assets or {}).items():
        if not IDENTIFIER.fullmatch(name) or type(data) is not bytes:
            raise AssemblyError('SYNTAX', 'declared assets require identifier names and generated bytes')
        obj['sources']['__assets__/' + name] = hashlib.sha256(data).hexdigest()
    # Forward constant EQU references must work even in assembly-time DS counts.
    for statement, location in lines:
        match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+(.+)', statement, re.I)
        if match:
            name = identifier(match[1])
            if name in equates:
                raise AssemblyError('DUPLICATE_SYMBOL', f'duplicate {name}', location, symbol=name, previous=equates[name][1])
            equates[name] = (match[2], location)
            if '@' not in match[2]:
                symbols[name] = parse(match[2])
    def define(name, expression, location):
        identifier(name)
        if name in obj['symbols']:
            raise AssemblyError('DUPLICATE_SYMBOL', f'duplicate {name}', location, symbol=name, previous=obj['symbols'][name]['span'])
        obj['symbols'][name] = {'expression': expression, 'span': location}
        symbols[name] = expression

    def relocation(expr, kind, offset, minimum, maximum, location, mask=None, shift=0, bias=0, allowed=None):
        width = 2 if kind in ('U16LE', 'ADDR16LE') else 1
        record = {'kind': kind, 'section': section['name'], 'offset': offset, 'expression': expr,
                  'minimum': minimum, 'maximum': maximum, 'mask': mask if mask is not None else (1 << (width * 8)) - 1,
                  'shift': shift, 'bias': bias, 'allowed': allowed or [], 'span': location}
        try:
            if kind == 'REL8':
                raise Unresolved('placement')
            value = evaluate(expr, symbols)
        except Unresolved:
            obj['relocations'].append(record)
            return
        if not minimum <= value <= maximum or (allowed and value not in allowed):
            raise AssemblyError('RANGE', f'value {value} outside operand constraint', location)
        value = ((value + bias) << shift) & record['mask']
        for i in range(width):
            mask_byte = (record['mask'] >> (8 * i)) & 255
            section['data'][offset + i] = (section['data'][offset + i] & ~mask_byte) | ((value >> (8 * i)) & mask_byte)

    for statement, location in lines:
        try:
            label = re.match(r'([A-Za-z_][A-Za-z0-9_]*):\s*(.*)', statement)
            if label:
                if section is None:
                    raise AssemblyError('SYNTAX', 'label requires a section')
                if label[1] in equates:
                    raise AssemblyError('DUPLICATE_SYMBOL', f'duplicate {label[1]}', previous=equates[label[1]][1])
                define(label[1], {'op': 'address', 'section': section['name'], 'offset': section['size']}, location)
                statement = label[2]
                if not statement:
                    continue
                location = {**location, 'column': location['column'] + label.start(2)}
            here = (section['name'], section['size']) if section else None
            match = re.fullmatch(r'([A-Za-z_][A-Za-z0-9_]*)\s+EQU\s+(.+)', statement, re.I)
            if match:
                define(match[1], parse(match[2], here), location)
                continue
            pieces = statement.split(None, 1)
            mnemonic, operands = pieces[0].upper(), pieces[1] if len(pieces) == 2 else ''
            if mnemonic == 'SECTION':
                parts = split(operands)
                if len(parts) != 2 or parts[1].upper() not in ('ROM', 'RAM'):
                    raise AssemblyError('SYNTAX', 'SECTION requires quoted name and ROM/RAM')
                name = string(parts[0])
                if not name or any(s['name'] == name for s in obj['sections']):
                    raise AssemblyError('DUPLICATE_SECTION', 'empty or reopened section')
                section = {'name': name, 'kind': parts[1].upper(), 'data': [], 'size': 0, 'span': location}
                obj['sections'].append(section)
                continue
            if mnemonic in ('EXPORT', 'IMPORT'):
                name = identifier(operands)
                key = mnemonic.lower() + 's'
                if name in obj[key]:
                    raise AssemblyError('DUPLICATE_SYMBOL', f'duplicate {mnemonic} {name}')
                obj[key].append(name)
                continue
            if section is None:
                raise AssemblyError('SYNTAX', 'emission/allocation requires a section')
            start = section['size']
            instruction = mnemonic not in ('DB', 'DW', 'DS', 'ASSET')
            if mnemonic == 'DS':
                if section['kind'] != 'RAM':
                    raise AssemblyError('SYNTAX', 'DS requires RAM')
                try:
                    count = evaluate(parse(operands, here), symbols)
                except Unresolved as error:
                    raise AssemblyError('UNDEFINED_SYMBOL', 'DS needs an assembly-time constant') from error
                if not 0 <= count <= 65536 - start:
                    raise AssemblyError('RANGE', 'invalid DS count')
                section['size'] += count
            else:
                if section['kind'] != 'ROM':
                    raise AssemblyError('SYNTAX', 'RAM forbids emitted bytes/instructions')
                if mnemonic == 'ASSET':
                    name = string(operands)
                    if name not in (assets or {}):
                        raise AssemblyError('UNDEFINED_SYMBOL', f'undeclared generated asset {name}')
                    section['data'].extend(assets[name])
                elif mnemonic in ('DB', 'DW'):
                    for item in split(operands):
                        if mnemonic == 'DB' and item.startswith('"'):
                            try:
                                section['data'].extend(string(item).encode('ascii'))
                            except UnicodeError as error:
                                raise AssemblyError('SYNTAX', 'DB strings must be ASCII') from error
                        else:
                            offset = len(section['data'])
                            section['data'].extend([0] * (2 if mnemonic == 'DW' else 1))
                            expr = parse(item, here)
                            kind = 'U16LE' if mnemonic == 'DW' else 'HIGH8' if expr['op'] == 'HIGH' else 'LOW8' if expr['op'] == 'LOW' else 'U8'
                            relocation(expr, kind, offset, -32768 if mnemonic == 'DW' else -128,
                                       65535 if mnemonic == 'DW' else 255, location)
                else:
                    encode(mnemonic, operands, here, section, symbols, relocation, location)
                section['size'] = len(section['data'])
                if section['size'] > 65536:
                    raise AssemblyError('RANGE', 'section exceeds address space')
            obj['listing'].append({'section': section['name'], 'offset': start,
                                   'size': section['size'] - start, 'instruction': instruction, 'span': location})
        except AssemblyError as error:
            error.diagnostic['span'] = location
            raise
    check_cycles(symbols)
    for name, expr in symbols.items():
        unknown = set(references(expr)) - symbols.keys() - set(obj['imports'])
        if unknown:
            raise AssemblyError('UNDEFINED_SYMBOL', f'undefined symbol {sorted(unknown)[0]}', obj['symbols'][name]['span'])
        try:
            evaluate(expr, symbols)
        except Unresolved:
            pass
    for item in obj['relocations']:
        unknown = set(references(item['expression'])) - symbols.keys() - set(obj['imports'])
        if unknown:
            raise AssemblyError('UNDEFINED_SYMBOL', f'undefined symbol {sorted(unknown)[0]}', item['span'])
    for name in obj['exports']:
        if name not in obj['symbols']:
            raise AssemblyError('UNDEFINED_SYMBOL', f'export has no definition: {name}', symbol=name)
    for name in obj['imports']:
        if name in obj['symbols']:
            raise AssemblyError('DUPLICATE_SYMBOL', f'import also defined locally: {name}', obj['symbols'][name]['span'], symbol=name)
    return validate(obj)


def encode(mnemonic, operands, here, section, symbols, emit_relocation, location):
    actual = split(operands) if operands else []
    normalized = [re.sub(r'\s+', '', part).lower() for part in actual]
    # BIT/RES/SET and RST have expression-bearing opcode fields.
    if mnemonic in ('BIT', 'RES', 'SET') and len(actual) == 2:
        register = normalized[1]
        row = next((r for r in FORMS if r['form'] == mnemonic.lower() + ' 0,' + register), None)
        if row:
            offset = len(section['data'])
            section['data'].extend(row['bytes'])
            emit_relocation(parse(actual[0], here), 'U8', offset + 1, 0, 7, location, mask=56, shift=3)
            return
    if mnemonic == 'RST' and len(actual) == 1:
        offset = len(section['data'])
        section['data'].append(199)
        emit_relocation(parse(actual[0], here), 'U8', offset, 0, 56, location, mask=56, allowed=list(range(0, 57, 8)))
        return
    for row in FORMS:
        parts = row['form'].split(' ', 1)
        if parts[0].upper() != mnemonic:
            continue
        wanted = parts[1].split(',') if len(parts) == 2 else []
        if len(wanted) != len(actual):
            continue
        dynamic = []
        for pattern, operand, raw in zip(wanted, normalized, actual):
            token = next((t for t in ('d16', 'a16', 'target', 'd8', 'a8', 'r8') if t in pattern), None)
            if token is None:
                if pattern != operand:
                    break
            else:
                before, after = pattern.split(token)
                if (before != 'sp+' and not operand.startswith(before)) or (after and not operand.endswith(after)):
                    break
                if not before and any(char in operand for char in '[]'):
                    break
                # Slice syntax while preserving identifier case and expression spaces.
                expression_text = raw.strip()
                if before == '[' and after == ']':
                    expression_text = expression_text[1:-1]
                elif before == 'sp+':
                    match = re.fullmatch(r'SP\s*([+-])\s*(.+)', expression_text, re.I)
                    if not match:
                        break
                    expression_text = match[1] + '(' + match[2] + ')'
                if (not expression_text or any(word.upper() in RESERVED - {'LOW', 'HIGH'}
                    for word in re.findall(r'(?<![A-Za-z0-9_$%])[A-Za-z_][A-Za-z0-9_]*', expression_text))):
                    break
                dynamic.append((token, expression_text))
        else:
            offset = len(section['data'])
            section['data'].extend(row['bytes'])
            for token, text in dynamic:
                expr = parse(text, here)
                width = 2 if token in ('d16', 'a16') else 1
                position = len(section['data'])
                section['data'].extend([0] * width)
                kind, minimum, maximum, bias = {
                    'd16': ('U16LE', -32768, 65535, 0), 'a16': ('ADDR16LE', 0, 65535, 0),
                    'd8': ('U8', -128, 255, 0), 'r8': ('U8', -128, 127, 0),
                    'a8': ('U8', 65280, 65535, -65280), 'target': ('REL8', 0, 65535, 0)}[token]
                if token == 'a8':
                    minimum = evaluate(symbols['GB_IO_START'], symbols)
                    maximum = evaluate(symbols['GB_IE_END'], symbols)
                    bias = -minimum
                elif width == 1 and expr['op'] in ('LOW', 'HIGH'):
                    kind = expr['op'] + '8'
                emit_relocation(expr, kind, position, minimum, maximum, location, bias=bias)
            return
    raise AssemblyError('UNSUPPORTED_INSTRUCTION', f'unsupported instruction/operands: {mnemonic} {operands}', location)
