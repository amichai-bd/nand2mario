"""Original fixed renderer operands using unchanged game publication routines."""
import hashlib
import json
import sys


def build(root, destination):
    prior = sys.path[:]
    try:
        sys.path[:0] = [str(root/'tools'), str(root/'src/dv/springtrail')]
        from sw.assembler import assemble
        from sw.linker import link
        from sw.package import package
        from sw.assets import load_shades, encode_shades
        from sw.columns import validate
        from interaction_cases import ADDRESSES, state_bytes
        from interactions_reference import Game, Player
        validate(root)
        destination.mkdir(parents=True, exist_ok=True)
        source = root/'src/sw/springtrail'
        for path in source.glob('*.asm'):
            (destination/path.name).write_bytes(path.read_bytes())
        game = Game(mode=1, player=Player(x=120*16, y=12*16, camera=97))
        lines = ['SECTION "code",ROM', 'Start:', 'DI', 'LD SP,$DFFE',
                 'XOR A,A', 'LDH [$FF40],A', 'LDH [$FF0F],A',
                 'LD [$FFFF],A', 'LDH [$FF43],A', 'LDH [$FF42],A',
                 'CALL InitSceneDMA']
        def write(address, value):
            lines.extend([f'LD A,${value & 255:02X}', f'LD [${address:04X}],A'])
        for address, value in zip(ADDRESSES, state_bytes(game)):
            write(address, value)
        for address, value in ((0xc02e, 0), (0xc02f, 32), (0xc023, 11),
                               (0xc030, 1), (0xc040, 0), (0xc050, 0),
                               (0xc051, 95), (0xc054, 0), (0xc055, 0)):
            write(address, value)
        # Fixture-only unrolling still loads every approved byte through CPU VRAM writes.
        lines += ['LD HL,Tiles', 'LD DE,$8000', 'LD B,74', 'TileBlock:']
        lines += ['LD A,[HL+]', 'LD [DE],A', 'INC DE']*16
        lines += ['DEC B', 'JR NZ,TileBlock', 'LD HL,$9800', 'LD B,64',
                  'XOR A,A', 'ClearHUD:', 'LD [HL+],A', 'DEC B',
                  'JR NZ,ClearHUD', 'CALL InitHUD', 'LD A,$E4',
                  'LDH [$FF47],A', 'LDH [$FF48],A', 'RingColumn:',
                  'LD A,[$C054]', 'LD DE,$C200', 'CALL DecodeColumn',
                  'LD A,[$C054]', 'LD HL,$C200', 'CALL PublishColumn',
                  'LD A,[$C054]', 'INC A', 'LD [$C054],A', 'CP A,32',
                  'JR NZ,RingColumn', 'CALL PrepareScene', 'CALL PrepareHUD',
                  'CALL PrepareMap', 'CALL PublishHUD', 'CALL PublishScene',
                  'XOR A,A', 'LDH [$FF0F],A', 'LD A,15', 'LDH [$FF45],A',
                  'LD A,$40', 'LDH [$FF41],A', 'LD A,3', 'LD [$FFFF],A',
                  'LD A,$99', 'LDH [$FF40],A', 'EI', 'WaitFrame:', 'DI',
                  'LD A,[FramePending]', 'OR A,A', 'JR NZ,ConsumeFrame',
                  'EI', 'HALT', 'JR WaitFrame', 'ConsumeFrame:', 'XOR A,A',
                  'LD [FramePending],A', 'LD A,[$C055]', 'OR A,A',
                  'JR NZ,Finished', 'INC A', 'LD [$C055],A', 'EI',
                  'CALL StreamMap', 'LD A,[Camera]', 'LD [PublishedCamera],A',
                  'CALL PublishHUD', 'DI', 'CALL PublishScene', 'EI',
                  'JP WaitFrame', 'Finished:', 'XOR A,A', 'LD [$FFFF],A',
                  'LD A,$A5', 'LD [$C0FF],A', 'HALT', 'EXPORT Start',
                  'SECTION "assets",ROM', 'Tiles:', 'ASSET "Tiles"',
                  'ASSET "Courier"']
        for name in ('movement', 'render', 'world', 'collision', 'interactions',
                     'map_restore', 'scene', 'stream', 'hud', 'columns'):
            lines.append(f'INCLUDE "{name}.asm"')
        path = destination/'program.asm'
        path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        assets = {}
        for name, relative in (('Tiles', 'tiles.json'),
                               ('Courier', 'assets/courier/unique-tiles.json'),
                               ('Core', 'assets/core/core-tiles.json')):
            asset = source/relative
            assets[name] = encode_shades(load_shades(asset, str(asset)), str(asset))
        assert len(assets['Tiles'])+len(assets['Courier']) == 1184
        obj = assemble(path, destination, root/'src/sw/generated/interfaces.inc', assets)
        layout = json.loads((source/'layout.json').read_text())
        layout['sections'] = [dict(row, unit='program.asm') for row in layout['sections']]
        linked = link([('program.asm', obj)], layout, dict(unit='program.asm', symbol='Start'))
        image = package(linked, 'HUD RENDER', 1)
        (destination/'program.gb').write_bytes(image)
        # Branch-inclusive startup allowances: each of 32 columns has at most
        # four runs/16 stores, one unrolled publication and counter overhead
        # (<1875 dots). Font/HUD includes both cleared rows. Preparation includes
        # the complete scene, one entering decode, both HUD copies and DMA.
        # The second VBlank is 135888 dots after LCD enable; 1112 covers its
        # shared ISR, token consumption, terminal write and final HALT.
        record = dict(sha256=hashlib.sha256(image).hexdigest(),
                      operands=dict(state=list(state_bytes(game)), old_camera=95,
                                    camera=97, old_camera_tile=11, entering_column=32),
                      lcd_bound=150000, end_bound=300000,
                      budget=dict(tile_copy=29624, font_hud=20000, ring=60000,
                                  preparation=30000, setup=10000,
                                  lcd_off_total=149624, two_vblanks_and_tail=137000),
                      shared_sections={row['section']:hashlib.sha256(image[row['address']:row['address']+row['size']]).hexdigest()
                                       for row in linked['map']['sections']
                                       if row['section'] not in ('code', 'assets')})
        (destination/'hud-render.json').write_text(json.dumps(record, indent=2)+'\n')
        (destination/'hud-render-listing.json').write_text(json.dumps(linked['listing'], indent=2)+'\n')
        return image
    finally:
        sys.path[:] = prior
