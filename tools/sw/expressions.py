"""Bounded assembly expressions, represented as data rather than Python code."""
import re


class AssemblyError(ValueError):
    def __init__(self, code, cause, span=None, **context):
        self.diagnostic = {'code': code, 'stage': 'assemble', 'cause': cause,
                           'span': span or {'file': '', 'line': 1, 'column': 1}, **context}
        super().__init__(cause)


class Unresolved(Exception):
    pass


TOKEN = re.compile(r'\s*(\$[0-9a-fA-F]+|%[01]+|[0-9]+|[A-Za-z_][A-Za-z0-9_]*|<<|>>|[-+~*/&^|()@])')
PRECEDENCE = {'|': 1, '^': 2, '&': 3, '<<': 4, '>>': 4, '+': 5, '-': 5, '*': 6, '/': 6}


def parse(text, here=None):
    tokens, position = [], 0
    while position < len(text.rstrip()):
        match = TOKEN.match(text, position)
        if not match:
            raise AssemblyError('SYNTAX', f'invalid expression near {text[position:]!r}')
        tokens.append(match[1])
        position = match.end()
    tokens.append(None)
    index = 0

    def expression(minimum=0):
        nonlocal index
        token = tokens[index]
        index += 1
        if token is None:
            raise AssemblyError('SYNTAX', 'missing expression')
        if token in ('+', '-', '~'):
            left = {'op': token, 'args': [expression(7)]}
        elif token == '(':
            left = expression()
            if tokens[index] != ')':
                raise AssemblyError('SYNTAX', 'missing closing parenthesis')
            index += 1
        elif token == '@':
            if here is None:
                raise AssemblyError('SYNTAX', 'current address requires a section')
            left = {'op': 'address', 'section': here[0], 'offset': here[1]}
        elif token[0].isdigit() or token[0] in '$%':
            left = {'op': 'integer', 'value': int(token[1:], 16 if token[0] == '$' else 2) if token[0] in '$%' else int(token)}
        elif re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', token):
            if token.upper() in ('LOW', 'HIGH') and tokens[index] == '(':
                index += 1
                left = {'op': token.upper(), 'args': [expression()]}
                if tokens[index] != ')':
                    raise AssemblyError('SYNTAX', 'missing function parenthesis')
                index += 1
            else:
                left = {'op': 'symbol', 'name': token}
        else:
            raise AssemblyError('SYNTAX', f'unexpected expression token {token}')
        while tokens[index] in PRECEDENCE and PRECEDENCE[tokens[index]] >= minimum:
            operator = tokens[index]
            index += 1
            left = {'op': operator, 'args': [left, expression(PRECEDENCE[operator] + 1)]}
        return left

    result = expression()
    if tokens[index] is not None:
        raise AssemblyError('SYNTAX', 'trailing expression tokens')
    return result


def evaluate(node, symbols, addresses=None, chain=()):
    op = node['op']
    if op == 'integer':
        return node['value']
    if op == 'address':
        if addresses is None or node['section'] not in addresses:
            raise Unresolved(node['section'])
        return addresses[node['section']] + node['offset']
    if op == 'symbol':
        name = node['name']
        if name in chain:
            raise AssemblyError('CYCLIC_SYMBOL', 'cyclic expression: ' + ' -> '.join((*chain, name)), symbol=name)
        if name not in symbols:
            raise Unresolved(name)
        return evaluate(symbols[name], symbols, addresses, (*chain, name))
    values = [evaluate(arg, symbols, addresses, chain) for arg in node['args']]
    a = values[0]
    if len(values) == 1:
        if op in ('LOW', 'HIGH'):
            if not 0 <= a <= 65535:
                raise AssemblyError('RANGE', f'{op} input outside 0..65535')
            return (a >> (8 if op == 'HIGH' else 0)) & 255
        return {'+': lambda: a, '-': lambda: -a, '~': lambda: ~a}[op]()
    b = values[1]
    if op == '/' and b == 0:
        raise AssemblyError('RANGE', 'division by zero')
    if op in ('<<', '>>') and not 0 <= b <= 63:
        raise AssemblyError('RANGE', 'shift count outside 0..63')
    operations = {'+': lambda: a + b, '-': lambda: a - b, '*': lambda: a * b,
                  '/': lambda: (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1),
                  '<<': lambda: a << b, '>>': lambda: a >> b,
                  '&': lambda: a & b, '^': lambda: a ^ b, '|': lambda: a | b}
    return operations[op]()


def references(node):
    if node['op'] == 'symbol':
        yield node['name']
    for arg in node.get('args', []):
        yield from references(arg)


def check_cycles(symbols):
    done = set()
    def visit(name, chain):
        if name in chain:
            raise AssemblyError('CYCLIC_SYMBOL', 'cyclic expression: ' + ' -> '.join((*chain, name)), symbol=name)
        if name in done or name not in symbols:
            return
        for dependency in references(symbols[name]):
            visit(dependency, (*chain, name))
        done.add(name)
    for name in symbols:
        visit(name, ())
