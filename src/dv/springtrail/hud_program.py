"""Link finite ordinary HUD/column operands with the game's exact routines."""
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
        from sw.columns import validate
        from hud_unit_cases import cases, game
        from interaction_cases import ADDRESSES, state_bytes
        validate(root)
        destination.mkdir(parents=True, exist_ok=True)
        source = root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        selected = cases()[:1] if short else cases()
        lines = ['SECTION "code",ROM', 'Start:', 'DI', 'LD SP,$DFFE',
                 'XOR A,A', 'LDH [$FF40],A', 'LD [$FFFF],A', 'CALL InitSceneDMA']
        last_state = {}
        def write(address, value):
            lines.extend([f'LD A,${value & 255:02X}', f'LD [${address:04X}],A'])
        for index, case in enumerate(selected):
            for address, value in zip(ADDRESSES, state_bytes(game(case))):
                if last_state.get(address) != value: write(address, value)
                last_state[address] = value
            for address, value in ((0xc02e, int(case['kind'] == 'restart')),
                    (0xc02f, case.get('restore', 32)), (0xc023, case.get('old', 0)//8),
                    (0xc051, 0xa6), (0xc052, 0xa5), (0xc053, 0), (0xc040, 0)):
                write(address, value)
            # Cache poison is not an expected result; it makes missing writes
            # and stale data visible without injecting any routine output.
            if index == 0:
                lines += ['LD HL,$C200', 'LD B,39', 'LD A,$A5', 'CachePoison:',
                          'LD [HL+],A', 'DEC B', 'JR NZ,CachePoison']
            write(0xff40, 8 if case['kind'] == 'restart' else 0)
            if case['kind'] == 'scene':
                lines += ['LD HL,$C100', 'LD B,160', 'LD A,$A5', 'ShadowPoison:',
                          'LD [HL+],A', 'DEC B', 'JR NZ,ShadowPoison']
            write(0xc0fc, index+1)
            kind = case['kind']
            if kind == 'decode':
                lines += [f'LD A,{case["column"]}', 'LD DE,$C200', 'CALL DecodeColumn']
            elif kind == 'restore':
                lines += ['CALL PrepareMap', 'CALL RestoreMapPair']
            elif kind == 'restart':
                lines += ['CALL PrepareMap', 'CALL BeginMapRestore', 'CALL RestoreMapPair']*2
            elif kind == 'enter':
                lines += ['CALL PrepareMap', 'CALL StreamMap']
            elif kind == 'hud':
                lines += ['CALL PrepareHUD', 'CALL PublishHUD']
            else:
                lines += ['CALL PrepareScene', 'CALL PrepareMap', 'CALL PrepareHUD',
                          'CALL StreamMap', 'CALL PublishHUD', 'CALL PublishScene',
                          'LD HL,$FE00', 'LD DE,$C300', 'LD B,160', 'ReadOAM:',
                          'LD A,[HL+]', 'LD [DE],A', 'INC DE', 'DEC B', 'JR NZ,ReadOAM']
            write(0xc0fd, index+1)
        write(0xc0ff, 0xa5)
        lines += ['HALT', 'EXPORT Start']
        for name in ('movement', 'render', 'world', 'collision', 'interactions',
                     'map_restore', 'scene', 'stream', 'hud', 'columns'):
            lines.append(f'INCLUDE "{name}.asm"')
        path = destination/'program.asm'
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        core = source/'assets/core/core-tiles.json'
        assets = {'Core':encode_shades(load_shades(core, str(core)), str(core))}
        obj = assemble(path, destination, root/'src/sw/generated/interfaces.inc', assets)
        layout = json.loads((source/'layout.json').read_text())
        layout['sections'] = [dict(row, unit='program.asm') for row in layout['sections']
                              if row['section'] != 'assets']
        linked = link([('program.asm', obj)], layout, dict(unit='program.asm', symbol='Start'))
        image = package(linked, 'HUD COLUMNS', 1)
        (destination/'program.gb').write_bytes(image)
        record = dict(sha256=hashlib.sha256(image).hexdigest(), cases=len(selected),
                      end_bound=10000 if short else 120000,
                      budget=dict(per_case_setup=1000, cases=19, decode_calls=18,
                                  decode_each=1500, publication=12000, hud=8000,
                                  scene=25000, dma_readback=9000, setup_tail=6000,
                                  conservative_total=106000),
                      shared_sections={row['section']:hashlib.sha256(image[row['address']:row['address']+row['size']]).hexdigest()
                                       for row in linked['map']['sections'] if row['section'] != 'code'})
        (destination/'hud-unit.json').write_text(json.dumps(record, indent=2)+'\n')
        (destination/'hud-unit-listing.json').write_text(json.dumps(linked['listing'], indent=2)+'\n')
        return image
    finally:
        sys.path[:] = prior
