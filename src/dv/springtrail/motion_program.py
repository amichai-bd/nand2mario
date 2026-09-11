"""Finite software operands call the exact linked motion and game routines."""
import hashlib
import json
import sys


def build(root, destination, short=False):
    prior = sys.path[:]
    try:
        sys.path[:0] = [str(root/'tools'), str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from sw.assets import load_shades, encode_shades
        from motion_cases import cases, RANGES
        destination.mkdir(parents=True, exist_ok=True)
        source = root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        selected = cases()[:1] if short else cases()
        lines = ['SECTION "code",ROM', 'Start:', 'DI', 'LD SP,$DFFE',
                 'XOR A,A', 'LDH [$FF40],A', 'LD [$FFFF],A',
                 'LD [$C0F0],A', 'LD HL,Operands', 'NextCase:']
        for i, (address, count) in enumerate(RANGES):
            lines += [f'LD DE,${address:04X}', f'LD B,{count}', f'Seed{i}:',
                      'LD A,[HL+]', 'LD [DE],A', 'INC DE', 'DEC B', f'JR NZ,Seed{i}']
        lines += ['LD A,[HL+]', 'LD [$C0F3],A', 'LD A,L', 'LD [$C0F1],A',
                  'LD A,H', 'LD [$C0F2],A', 'LD A,[$C0F0]', 'INC A',
                  'LD [$C0F0],A', 'LD [$C0FC],A', 'LD A,[$C0F3]',
                  'OR A,A', 'JR Z,StepCase', 'CP A,1', 'JR Z,InitCase',
                  'CALL UpdateGame', 'JR Report', 'StepCase:', 'CALL StepPlayer',
                  'JR Report', 'InitCase:', 'CALL InitPlayer', 'Report:',
                  'LD A,[$C0F0]', 'LD [$C0FD],A', f'CP A,{len(selected)}',
                  'JR Z,Finished', 'LD A,[$C0F1]', 'LD L,A', 'LD A,[$C0F2]',
                  'LD H,A', 'JP NextCase', 'Finished:', 'LD A,$A5',
                  'LD [$C0FF],A', 'HALT', 'EXPORT Start',
                  'SECTION "assets",ROM', 'Operands:']
        for case in selected:
            values = case['before'] + bytes([{'step':0, 'init':1, 'game':2}[case['kind']]])
            lines.append('DB '+','.join(str(v) for v in values))
        for name in ('movement', 'render', 'world', 'collision', 'interactions',
                     'map_restore', 'scene', 'stream', 'hud', 'columns'):
            lines.append(f'INCLUDE "{name}.asm"')
        path = destination/'program.asm'
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        core = source/'assets/core/core-tiles.json'
        assets = {'Core':encode_shades(load_shades(core, str(core)), str(core))}
        obj = assemble(path, destination, root/'src/sw/generated/interfaces.inc', assets)
        layout = json.loads((source/'layout.json').read_text())
        layout['sections'] = [dict(row, unit='program.asm') for row in layout['sections']]
        linked = link([('program.asm', obj)], layout, dict(unit='program.asm', symbol='Start'))
        image = package(linked, 'MOTION UNIT', 1)
        (destination/'program.gb').write_bytes(image)
        record = dict(sha256=hashlib.sha256(image).hexdigest(), cases=len(selected),
                      names=[c['name'] for c in selected], end_bound=10000 if short else 500000,
                      budget=dict(setup_per_case=1700, simple_calls=33,
                                  simple_ceiling=8000, game_calls=7, game_ceiling=20000,
                                  tail=1000, conservative_total=473000),
                      shared_sections={r['section']:hashlib.sha256(image[r['address']:r['address']+r['size']]).hexdigest()
                                       for r in linked['map']['sections'] if r['section'] not in ('code', 'assets')})
        (destination/'motion-unit.json').write_text(json.dumps(record, indent=2)+'\n')
        (destination/'motion-unit-listing.json').write_text(json.dumps(linked['listing'], indent=2)+'\n')
        return image
    finally:
        sys.path[:] = prior
