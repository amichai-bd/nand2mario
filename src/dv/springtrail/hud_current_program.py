"""Current shared HUD/column calls with ordinary CPU-seeded operands."""
import hashlib
import json
import sys


def build(root,destination,short=False,part='a'):
    prior=sys.path[:]
    try:
        sys.path[:0]=[str(root/'tools'),str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from sw.assets import load_shades,encode_shades
        from sw.columns import validate
        from hud_current_cases import cases,parts,operands,ADDRESSES,RANGES
        validate(root)
        selected=cases()[:1] if short else parts()[part]
        destination.mkdir(parents=True,exist_ok=True);source=root/'src/sw/springtrail'
        for path in source.glob('*.asm'):(destination/path.name).write_bytes(path.read_bytes())
        lines=['SECTION "code",ROM','Start:','DI','LD SP,$DFFE','XOR A,A',
               'LDH [$FF40],A','LD [$FFFF],A','CALL InitSceneDMA',
               'LD HL,$C200','LD B,40','LD A,$A5','PoisonCache:',
               'LD [HL+],A','DEC B','JR NZ,PoisonCache']
        def write(a,v):lines.extend([f'LD A,${v:02X}',f'LD [${a:04X}],A'])
        for index,case in enumerate(selected):
            lines.extend([f'LD HL,Inputs{index}','CALL SeedWorld'])
            for a,v in operands(case).items():
                if a not in ADDRESSES:write(a,v)
            if case['kind']=='scene':
                lines.extend(['LD HL,$C100','LD B,160','LD A,$A5','PoisonShadow:',
                              'LD [HL+],A','DEC B','JR NZ,PoisonShadow'])
            write(0xc0fc,index+1)
            kind=case['kind']
            if kind=='decode':lines.extend([f'LD A,{case["column"]}','LD DE,$C200','CALL DecodeColumn'])
            elif kind=='restore':
                lines.append('CALL PrepareMap')
                if case['restore']==30:lines.extend(['CALL PrepareHUD','CALL PrepareProgress'])
                lines.append('CALL RestoreMapPair')
                if case['restore']==30:lines.extend(['CALL PublishHUD','CALL PublishProgress'])
            elif kind=='restart':lines.extend(['CALL BeginMapRestore','CALL PrepareMap','CALL RestoreMapPair']*2)
            elif kind=='enter':lines.extend(['CALL PrepareMap','CALL StreamMap'])
            elif kind=='dirty':lines.extend(['CALL PrepareMap','CALL StreamMap']*2)
            elif kind=='hud':lines.extend(['CALL PrepareHUD','CALL PublishHUD'])
            elif kind=='progress':lines.extend(['CALL PrepareProgress','CALL PublishProgress'])
            else:
                lines.extend(['CALL PrepareScene','CALL PrepareMap','CALL PrepareHUD','CALL PrepareProgress',
                              'CALL StreamMap','CALL PublishHUD','CALL PublishProgress','CALL PublishScene',
                              'LD HL,$FE00','LD DE,$C400','LD B,160','ReadOAM:',
                              'LD A,[HL+]','LD [DE],A','INC DE','DEC B','JR NZ,ReadOAM'])
            write(0xc0fd,index+1)
        write(0xc0ff,0xa5);lines.extend(['HALT','SeedWorld:'])
        for i,(address,count) in enumerate(RANGES):
            lines.extend([f'LD DE,${address:04X}',f'LD B,{count}',f'Seed{i}:',
                          'LD A,[HL+]','LD [DE],A','INC DE','DEC B',f'JR NZ,Seed{i}'])
        lines.extend(['RET','EXPORT Start','SECTION "assets",ROM'])
        for i,case in enumerate(selected):
            data=operands(case);lines.extend([f'Inputs{i}:','DB '+','.join(str(data[a]) for a in ADDRESSES)])
        for name in ('movement','render','world','collision','interactions','map_restore','scene',
                     'stream','hud','columns','power','blocks','progress','entities'):
            lines.append(f'INCLUDE "{name}.asm"')
        path=destination/'program.asm';path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        assets={}
        for name,file in (('Core','core-tiles.json'),('Terrain','terrain-tiles.json'),('Enemies','enemies-tiles.json')):
            asset=source/'assets/core'/file;assets[name]=encode_shades(load_shades(asset,str(asset)),str(asset))
        obj=assemble(path,destination,root/'src/sw/generated/interfaces.inc',assets)
        layout=json.loads((source/'layout.json').read_text())
        layout['sections']=[dict(row,unit='program.asm') for row in layout['sections']]
        # Fixture-only code uses the free1KiB tail; game section addresses stay fixed.
        for row in layout['sections']:
            if row['section']=='code':row.update(address=0x7c00,region='ROM1')
        linked=link([('program.asm',obj)],layout,dict(unit='program.asm',symbol='Start'))
        image=package(linked,'HUD CURRENT',1);(destination/'program.gb').write_bytes(image)
        record=dict(sha256=hashlib.sha256(image).hexdigest(),names=[c['name'] for c in selected],
                    cases=len(selected),end_bound=30000 if short else 160000,
                    shared_sections={r['section']:hashlib.sha256(image[r['address']:r['address']+r['size']]).hexdigest()
                                     for r in linked['map']['sections'] if r['section'] not in ('code','assets')})
        (destination/'hud-current.json').write_text(json.dumps(record,indent=2)+'\n')
        (destination/'hud-current-listing.json').write_text(json.dumps(linked['listing'],indent=2)+'\n')
        return image
    finally:sys.path[:]=prior
