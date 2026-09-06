"""Package the original smoke ROM; check literal bytes independently."""
import json
from pathlib import Path
import sys


def build(root, destination):
    sys.path.insert(0, str(root / 'tools'))
    from sw.assembler import assemble
    from sw.linker import link
    from sw.package import package, validate_image
    source = root / 'src/dv/integration'
    obj = assemble(source / 'program.asm', source, root / 'src/sw/generated/interfaces.inc')
    layout = {'schema_version': 1, 'sections': [
        {'unit': 'program.asm', 'section': 'code', 'region': 'ROM0', 'address': 0x200},
        {'unit': 'program.asm', 'section': 'handler', 'region': 'ROM0', 'vector': 'VBLANK'}]}
    linked = link([('program.asm', obj)], layout, {'unit': 'program.asm', 'symbol': 'Start'})
    image = package(linked, 'N2M SMOKE', 1)
    validate_image(image, 0x200, 'N2M SMOKE', 1)
    for event in json.loads((source / 'program.json').read_text())['events']:
        if 'pc' not in event:
            continue
        address = int(event['pc'], 16)
        literal = bytes.fromhex(event['bytes'])
        if image[address:address + len(literal)] != literal:
            raise ValueError(f'original instruction bytes differ at {address:04x}')
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'program.gb').write_bytes(image)
    (destination / 'layout.json').write_text(json.dumps(layout, indent=2) + '\n')
    return image


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[3]
    build(root, root / 'workdir/builds/integration140-image')
