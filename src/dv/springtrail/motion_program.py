"""Finite software operands call the exact linked motion and game routines."""
import hashlib
import json
import sys


KINDS = {'step': 0, 'init': 1, 'game': 2, 'power': 3, 'star': 4, 'reset': 5,
         'lives': 6, 'spawn': 7, 'scene': 8, 'limit': 9}


def build(root, destination, short=False, suite='motion', part=None):
    prior = sys.path[:]
    try:
        sys.path[:0] = [str(root/'tools'), str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from sw.assets import load_shades, encode_shades
        import importlib
        module = importlib.import_module(suite + '_cases')
        from current_unit_cases import adapt
        module = adapt(module)
        cases, RANGES = module.cases, module.RANGES
        destination.mkdir(parents=True, exist_ok=True)
        source = root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        selected = (cases()[:getattr(module, 'SHORT', 1)] if short
                    else module.parts()[part] if part else cases())
        lines = ['SECTION "code",ROM', 'Start:', 'DI', 'LD SP,$DFFE',
                 'XOR A,A', 'LDH [$FF40],A', 'LD [$FFFF],A',
                 'LD [$C0F0],A', 'LD HL,Operands', 'NextCase:',
                 # Each case starts from the progression contract's reset values, so
                 # the lives, the stage and the countdown hold them wherever a suite
                 # does not seed them: lives 2, no request, subdivision 40, 400, grade
                 # 0, stage 0. Seven stores cost about 100 dots; a full InitGame would
                 # also clear the block layer and break the short 20000-dot bound.
                 'LD A,2', 'LD [$C090],A', 'XOR A,A', 'LD [$C091],A', 'LD [$C093],A',
                 'LD [$C095],A', 'LD [$C096],A', 'LD A,40', 'LD [$C092],A',
                 'LD A,4', 'LD [$C094],A']
        if hasattr(module,'EXTRA_RANGES'):
            lines += ['PUSH HL','LD HL,ExtraOperands']
            for i,(address,count) in enumerate(module.EXTRA_RANGES):
                lines += [f'LD DE,${address:04X}',f'LD B,{count}',f'Extra{i}:',
                          'LD A,[HL+]','LD [DE],A','INC DE','DEC B',f'JR NZ,Extra{i}']
            lines += ['POP HL']
        for i, (address, count) in enumerate(getattr(module,'SEED_RANGES',RANGES)):
            lines += [f'LD DE,${address:04X}', f'LD B,{count}', f'Seed{i}:',
                      'LD A,[HL+]', 'LD [DE],A', 'INC DE', 'DEC B', f'JR NZ,Seed{i}']
        lines += ['LD A,[HL+]', 'LD [$C0F3],A', 'LD A,L', 'LD [$C0F1],A',
                  'LD A,H', 'LD [$C0F2],A', 'LD A,[$C0F0]', 'INC A',
                  'LD [$C0F0],A', 'LD [$C0FC],A', 'LD A,[$C0F3]',
                  'OR A,A', 'JR Z,StepCase', 'CP A,1', 'JR Z,InitCase',
                  'CP A,2', 'JR Z,GameCase', 'CP A,3', 'JR Z,PowerCase',
                  'CP A,4', 'JR Z,StarCase', 'CP A,6', 'JR Z,LivesCase',
                  'CP A,7', 'JR Z,SpawnCase',
                  'CP A,8', 'JR Z,SceneCase', 'CP A,9', 'JR Z,LimitCase',
                  'CALL InitGame', 'JR Report',
                  'SceneCase:', 'CALL PrepareScene', 'JR Report',
                  'LimitCase:', 'LD DE,$C1A0', 'CALL EmitPiece', 'JR Report',
                  'SpawnCase:', 'LD A,[Buttons]', 'CALL SpawnEntity', 'JR Report',
                  'LivesCase:', 'CALL UpdateLives', 'JR Report',
                  'GameCase:', 'CALL UpdateGame', 'JR Report',
                  'PowerCase:', 'CALL PowerUp', 'JR Report',
                  'StarCase:', 'CALL GrantStar', 'JR Report',
                  'StepCase:', 'CALL StepPlayer',
                  'JR Report', 'InitCase:', 'CALL InitPlayer', 'Report:',
                  'LD A,[$C0F0]', 'LD [$C0FD],A', f'CP A,{len(selected)}',
                  'JR Z,Finished', 'LD A,[$C0F1]', 'LD L,A', 'LD A,[$C0F2]',
                  'LD H,A', 'JP NextCase', 'Finished:', 'LD A,$A5',
                  'LD [$C0FF],A', 'HALT', 'EXPORT Start',
                  'SECTION "assets",ROM', 'Operands:']
        for case in selected:
            indexes=[module.ADDRESSES.index(a) for a in getattr(module,'SEED_ADDRESSES',module.ADDRESSES)]
            values = bytes(case['before'][i] for i in indexes) + bytes([KINDS[case['kind']]])
            lines.append('DB '+','.join(str(v) for v in values))
        if hasattr(module,'EXTRA_VALUES'):
            lines += ['ExtraOperands:','DB '+','.join(str(v) for v in module.EXTRA_VALUES)]
        for name in ('movement', 'render', 'world', 'collision', 'interactions',
                     'map_restore', 'scene', 'stream', 'hud', 'columns', 'power',
                     'blocks', 'progress', 'entities'):
            lines.append(f'INCLUDE "{name}.asm"')
        path = destination/'program.asm'
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        core = source/'assets/core/core-tiles.json'
        terrain = source/'assets/core/terrain-tiles.json'
        assets = {'Core':encode_shades(load_shades(core, str(core)), str(core)),
                  'Terrain':encode_shades(load_shades(terrain, str(terrain)), str(terrain)),
                  'Enemies':encode_shades(load_shades(source/'assets/core/enemies-tiles.json', 'Enemies'), 'Enemies')}
        obj = assemble(path, destination, root/'src/sw/generated/interfaces.inc', assets)
        layout = json.loads((source/'layout.json').read_text())
        layout['sections'] = [dict(row, unit='program.asm') for row in layout['sections']]
        linked = link([('program.asm', obj)], layout, dict(unit='program.asm', symbol='Start'))
        image = package(linked, getattr(module, 'TITLE', suite.upper() + ' UNIT'), 1)
        (destination/'program.gb').write_bytes(image)
        record = dict(sha256=hashlib.sha256(image).hexdigest(), cases=len(selected),
                      names=[c['name'] for c in selected],
                      end_bound=getattr(module, 'SHORT_BOUND', 10000) if short else getattr(module, 'FULL_BOUND', 500000),
                      budget=getattr(module, "BUDGET", dict(setup_per_case=1700, simple_calls=33,
                                  simple_ceiling=8000, game_calls=7, game_ceiling=20000,
                                  tail=1000, conservative_total=473000)),
                      shared_sections={r['section']:hashlib.sha256(image[r['address']:r['address']+r['size']]).hexdigest()
                                       for r in linked['map']['sections'] if r['section'] not in ('code', 'assets')})
        (destination/(suite + '-unit.json')).write_text(json.dumps(record, indent=2)+'\n')
        (destination/(suite + '-unit-listing.json')).write_text(json.dumps(linked['listing'], indent=2)+'\n')
        return image
    finally:
        sys.path[:] = prior
