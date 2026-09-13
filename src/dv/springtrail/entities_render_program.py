"""Two fixed entity scenes; fixture-only fast tile copies, shared scene and IRQ code."""
import hashlib
import json
import sys
from dataclasses import replace
from entities_reference import World, Entity
from motion_reference import Player

NORMAL = World(mode=1, player=Player(x=136*16, y=12*16, camera=96, pose=2),
               enemy_x=168*16, enemy_vx=8, alive=True, patrol_frame=0,
               curl=Entity(208*16,64*16), moving=Entity(176*16,80*16,1,0,16),
               falling=Entity(208*16,104*16))
CHANGED = replace(NORMAL, alive=False, stomp=8,
                  curl=Entity(208*16,64*16,1,16),
                  moving=Entity(208*16,80*16,1,0,-16),
                  falling=Entity(208*16,104*16,1,8))
SCENES = {'normal': NORMAL, 'changed': CHANGED}


def build(root, destination, variant='normal'):
    prior=sys.path[:]
    try:
        sys.path[:0]=[str(root/'tools'),str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from sw.assets import load_shades, encode_shades
        from sw.columns import validate
        from state_seed import state_bytes, seed_copy
        from hud_reference import CHARS, MAPS
        from startup_anchor import derive
        validate(root)
        world=SCENES[variant]
        destination.mkdir(parents=True,exist_ok=True)
        source=root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        lines=['SECTION "code",ROM','Start:','DI','LD SP,$DFFE','XOR A,A',
               'LDH [$FF40],A','LDH [$FF0F],A','LD [$FFFF],A',
               'LDH [$FF43],A','LDH [$FF42],A','CALL InitSceneDMA']
        def write(address,value):
            lines.extend([f'LD A,${value&255:02X}',f'LD [${address:04X}],A'])
        lines += seed_copy()
        for address,value in ((0xc02e,0),(0xc02f,32),(0xc023,12),(0xc030,1),
                              (0xc050,0),(0xc051,96),(0xc054,12),(0xc055,0)):
            write(address,value)
        # All174 approved tiles pass through ordinary CPU VRAM writes. Only the
        # fixture copy loop is unrolled; source bytes remain the game's assets.
        lines += ['LD DE,$8000']
        def copy(label,count):
            lines.extend([f'LD HL,{label}',f'LD B,{count}','CALL FastTiles'])
        copy('Tiles',74)
        for char in CHARS:
            copy('CoreTiles+'+str(MAPS['glyph-'+char]['pieces'][0]['tile']*16),1)
        for label,count in (('CoreTiles+256',4),('CoreTiles+336',6),
                            ('CoreTiles+688',3),('CoreTiles+864',1),
                            ('TerrainTiles+160',24),('TerrainTiles+608',8)):
            copy(label,count)
        for offset in (1392,1408,1424,1440,1456,1088,1232,832,848):
            copy('CoreTiles+'+str(offset),1)
        copy('EnemyTiles',11);copy('EnemyTiles+304',14)
        for base in (0x9800,0x9c00):
            lines += [f'LD HL,${base:04X}','LD B,64','XOR A,A',f'Clear{base}:',
                      'LD [HL+],A','DEC B',f'JR NZ,Clear{base}',
                      'LD HL,ScoreLabel',f'LD DE,${base+12:04X}','CALL PublishLabel']
            write(base+33,147);write(base+44,148)
        lines += ['LD A,$E4','LDH [$FF47],A','LDH [$FF48],A','RingColumn:',
                  'LD A,[$C054]','LD DE,$C200','CALL DecodeColumn',
                  'LD A,[$C054]','LD HL,$C200','CALL PublishColumn',
                  'LD A,[$C054]','INC A','LD [$C054],A','CP A,44','JR NZ,RingColumn',
                  'CALL PrepareScene','CALL PrepareHUD','CALL PrepareProgress',
                  'CALL PublishHUD','LD HL,ProgressCache','LD DE,$9C22',
                  'CALL PublishProgressMap','CALL PublishScene',
                  'XOR A,A','LDH [$FF0F],A','LD A,15','LDH [$FF45],A',
                  'LD A,$40','LDH [$FF41],A','LD A,3','LD [$FFFF],A',
                  'LD A,$99','LDH [$FF40],A','EI','WaitFrame:','DI',
                  'LD A,[FramePending]','OR A,A','JR NZ,ConsumeFrame',
                  'EI','HALT','JR WaitFrame','ConsumeFrame:','XOR A,A',
                  'LD [FramePending],A','LD A,[$C055]','OR A,A','JR NZ,Finished',
                  'INC A','LD [$C055],A','EI','CALL PublishHUD',
                  'CALL PublishProgress','DI','CALL PublishScene','EI','JP WaitFrame',
                  'Finished:','XOR A,A','LD [$FFFF],A','LD A,$A5','LD [$C0FF],A',
                  'HALT','EXPORT Start','FastTiles:']
        lines += ['LD A,[HL+]','LD [DE],A','INC DE']*16
        lines += ['DEC B','JR NZ,FastTiles','RET','SECTION "assets",ROM',
                  'Tiles:','ASSET "Tiles"','ASSET "Courier"','SeedValues:',
                  'DB '+','.join(str(v) for v in state_bytes(world))]
        for name in ('movement','render','world','collision','interactions','map_restore',
                     'scene','stream','hud','columns','power','blocks','progress','entities'):
            lines.append(f'INCLUDE "{name}.asm"')
        path=destination/'program.asm';path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        assets={}
        for name,relative in (('Tiles','tiles.json'),('Courier','assets/courier/unique-tiles.json'),
                              ('Core','assets/core/core-tiles.json'),('Terrain','assets/core/terrain-tiles.json'),
                              ('Enemies','assets/core/enemies-tiles.json')):
            asset=source/relative
            assets[name]=encode_shades(load_shades(asset,str(asset)),str(asset))
        obj=assemble(path,destination,root/'src/sw/generated/interfaces.inc',assets)
        layout=json.loads((source/'layout.json').read_text())
        layout['sections']=[dict(row,unit='program.asm', **({'region':'ROM1','address':0x7bc0} if row['section']=='code' else {})) for row in layout['sections']]
        linked=link([('program.asm',obj)],layout,dict(unit='program.asm',symbol='Start'))
        image=package(linked,'ENTITY '+variant.upper(),1)
        (destination/'program.gb').write_bytes(image)
        timing=derive(image,lcdc_on=0x99)
        record=dict(sha256=hashlib.sha256(image).hexdigest(),variant=variant,lcd=timing['lcd'],
                    end_bound=timing['lcd']+2*70224,tiles=174,frames=2,dma_bytes=320,
                    source_timing=timing,
                    sections=[dict(name=r['section'],address=r['address'],size=r['size']) for r in linked['map']['sections'] if r['section'] not in ('code','assets')],
                    shared_sections={r['section']:hashlib.sha256(image[r['address']:r['address']+r['size']]).hexdigest()
                                     for r in linked['map']['sections'] if r['section'] not in ('code','assets')})
        (destination/'entities-render.json').write_text(json.dumps(record,indent=2)+'\n')
        (destination/'entities-render-listing.json').write_text(json.dumps(linked['listing'],indent=2)+'\n')
        return image
    finally:
        sys.path[:]=prior
