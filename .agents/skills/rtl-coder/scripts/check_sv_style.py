#!/usr/bin/env python3
"""Reject SystemVerilog variable/net declaration assignments in tracked source."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
BUILTINS = set('logic reg wire bit byte shortint int longint integer time realtime real shortreal string chandle event genvar tri tri0 tri1 wand wor uwire'.split())
QUALIFIERS = {'signed', 'unsigned', 'var', 'static', 'automatic', 'const'}
TOKEN = re.compile(r'[A-Za-z_$][\w$]*(?:``[\w$]+)*|::|==|!=|<=|>=|===|!==|\S')


def violations(source):
    # Keep positions for file/line diagnostics; comments and strings contain no declarations.
    clean = re.sub(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"',
                   lambda m: re.sub(r'[^\n]', ' ', m.group()), source)
    types = BUILTINS | set(re.findall(r'\btypedef\b[^;]*?\b(\w+)\s*;', clean))
    tokens = list(TOKEN.finditer(clean))
    found = set()
    for i, token in enumerate(tokens):
        if token.group() not in types:
            continue
        # Constant definitions must retain their values. Skip type casts and function returns.
        j = i - 1
        while j >= 0 and tokens[j].group() in QUALIFIERS:
            j -= 1
        if j >= 0 and tokens[j].group() in {'parameter', 'localparam', 'typedef', 'function'}:
            continue
        j = i + 1
        depth = 0
        saw_name = False
        while j < len(tokens):
            value = tokens[j].group()
            if value == '[':
                depth += 1
            elif value == ']':
                depth -= 1
            elif depth == 0:
                if value in {';', ')', '(', "'", '{', '}', ':'}:
                    break
                if value == '=':
                    if saw_name:
                        found.add(source.count('\n', 0, token.start()) + 1)
                    break
                if value not in QUALIFIERS and value != ',':
                    if not re.fullmatch(r'[A-Za-z_$][\w$]*(?:``[\w$]+)*', value):
                        break
                    saw_name = True
            j += 1
    return sorted(found)


def main():
    paths = subprocess.check_output(['git', 'ls-files', '-z', '--', '*.sv', '*.svh'], cwd=ROOT).decode().split('\0')
    errors = []
    for name in filter(None, paths):
        for line in violations((ROOT / name).read_text(encoding='utf-8')):
            errors.append(f'{name}:{line}: separate declaration and assignment')
    print('\n'.join(errors) if errors else 'PASS SystemVerilog declaration style')
    return bool(errors)


if __name__ == '__main__':
    sys.exit(main())
