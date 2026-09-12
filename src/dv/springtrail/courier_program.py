"""Seed ordinary courier operands and call unchanged linked game routines."""
import hashlib
import json
import sys


def build(root, destination, short=False, part='a'):
    prior = sys.path[:]
    try:
        sys.path[:0] = [str(root/'tools'), str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from sw.assets import load_shades, encode_shades
        from courier_cases import cases, parts, operands
        selected = cases()[:1] if short else parts()[part]
        destination.mkdir(parents=True, exist_ok=True)
        source = root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        lines = ['SECTION "code",ROM', 'Start:', 'DI', 'LD SP,$DFFE',
                 'XOR A,A', 'LDH [$FF40],A', 'LD [$FFFF],A',
                 'LD HL,$C000', 'LD B,240', 'LD A,$5A', 'SeedState:',
                 'LD [HL+],A', 'DEC B', 'JR NZ,SeedState',
                 'LD HL,$C300', 'LD B,56', 'LD A,$5A', 'SeedEntities:',
                 'LD [HL+],A', 'DEC B', 'JR NZ,SeedEntities',
                 'LD HL,$C100', 'LD B,160', 'LD A,$A5', 'Poison:',
                 'LD [HL+],A', 'DEC B', 'JR NZ,Poison',
                 'XOR A,A', 'LD [$C0F0],A', 'LD HL,Operands', 'NextCase:']
        # Explicit input fields only. Output bytes never enter the operand ROM.
        for address in (0xc041, 0xc040, 0xc03b, 0xc0f3, 0xc042, 0xc043,
                        0xc044, 0xc045, 0xc01b, 0xc01c):
            lines += ['LD A,[HL+]', f'LD [${address:04X}],A']
        lines += ['LD A,L', 'LD [$C0F1],A', 'LD A,H', 'LD [$C0F2],A']
        for src, dst in ((0xc042,0xc034),(0xc043,0xc035),
                         (0xc044,0xc036),(0xc045,0xc037)):
            lines += [f'LD A,[${src:04X}]', f'LD [${dst:04X}],A']
        lines += ['LD A,[$C0F0]', 'INC A', 'LD [$C0F0],A', 'LD [$C0FC],A',
                  'LD A,[$C0F3]', 'OR A,A', 'JR Z,Compose',
                  'CALL ScenePosition', 'Compose:', 'LD DE,$C100',
                  'CALL ComposeCourier', 'XOR A,A', 'CALL ClearSceneByte',
                  'LD A,[$C0F0]', 'LD [$C0FD],A', f'CP A,{len(selected)}',
                  'JR Z,Finished', 'LD A,[$C0F1]', 'LD L,A',
                  'LD A,[$C0F2]', 'LD H,A', 'JP NextCase',
                  'Finished:', 'LD A,$A5', 'LD [$C0FF],A', 'HALT',
                  'EXPORT Start', 'SECTION "assets",ROM', 'Operands:']
        for case in selected:
            lines.append('DB '+','.join(str(v) for v in operands(case)))
        for name in ('movement', 'render', 'world', 'collision', 'interactions',
                     'map_restore', 'scene', 'stream', 'hud', 'columns', 'power',
                     'blocks', 'progress', 'entities'):
            lines.append(f'INCLUDE "{name}.asm"')
        path = destination/'program.asm'
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        assets = {}
        for name, file in (('Core','core-tiles.json'),('Terrain','terrain-tiles.json'),
                           ('Enemies','enemies-tiles.json')):
            asset = source/'assets/core'/file
            assets[name] = encode_shades(load_shades(asset, str(asset)), str(asset))
        obj = assemble(path, destination, root/'src/sw/generated/interfaces.inc', assets)
        layout = json.loads((source/'layout.json').read_text())
        layout['sections'] = [dict(row, unit='program.asm') for row in layout['sections']]
        linked = link([('program.asm', obj)], layout, dict(unit='program.asm', symbol='Start'))
        image = package(linked, 'COURIER CASES', 1)
        (destination/'program.gb').write_bytes(image)
        record = dict(sha256=hashlib.sha256(image).hexdigest(), cases=len(selected),
                      names=[row['name'] for row in selected],
                      end_bound=40000 if short else 150000,
                      shared_sections={r['section']:hashlib.sha256(image[r['address']:r['address']+r['size']]).hexdigest()
                                       for r in linked['map']['sections'] if r['section'] not in ('code','assets')})
        (destination/'courier-unit.json').write_text(json.dumps(record, indent=2)+'\n')
        (destination/'courier-unit-listing.json').write_text(json.dumps(linked['listing'], indent=2)+'\n')
        return image
    finally:
        sys.path[:] = prior
