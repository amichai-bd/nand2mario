"""Immutable tagged software build publication with complete output inventories."""
import json
import hashlib
from pathlib import Path
import re
import uuid
from n2m.interfaces import render
from n2m import generated_interfaces as hw
from n2m.records import atomic_json, cache_matches, digest, file_hash, read_json
from .build import assemble_target
from .expressions import AssemblyError
from .linker import fail, link
from .package import package
from .targets import validate_target


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('utf-8')


def require_legacy_scene(root, target):
    """The old renderer fixture is tied to its nine-object scene implementation."""
    if target in ('render', 'render-s'):
        source=(root/'src/sw/springtrail/scene.asm').read_bytes().replace(b'\r\n',b'\n')
        if hashlib.sha256(source).hexdigest()!='148686f9b770a167dc3e0597659f9bb20d8c75783009ffba730e14966cdc8e75':
            fail('HISTORICAL_RENDER_SOURCE', 'old renderer fixture requires #316 scene; use courier-unit and composition checks')


def build_target(root, build, args, provenance):
    safe = args.target if re.fullmatch('[a-z0-9][a-z0-9_-]*', args.target) else 'invalid-target'
    stage = build / 'sw/build' / safe
    folder = stage / 'runs' / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    report = {'status': 'FAIL', 'target': args.target, **provenance}
    try:
        registry = root / 'src/sw/targets.json'
        definitions = json.loads(registry.read_text(encoding='utf-8'))
        if (type(definitions) is not dict or set(definitions) != {'schema_version', 'targets'}
                or type(definitions['schema_version']) is not int or definitions['schema_version'] != 2
                or type(definitions['targets']) is not dict or safe != args.target):
            fail('SCHEMA_MISMATCH', 'invalid software target registry')
        target = definitions['targets'].get(args.target)
        validate_target(target, require_package=True, stage='link')
        require_legacy_scene(root,args.target)
        if args.target == 'springtrail':
            from .columns import validate as validate_columns
            validate_columns(root)
        def confined(base, name):
            if type(name) is not str or not name or Path(name).is_absolute() or '..' in Path(name).parts or ':' in name or '\\' in name:
                fail('PRIVATE_PATH', 'target-relative confined path required')
            path = base / name
            if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
                fail('PRIVATE_PATH', 'path escapes target ownership')
            return path.resolve()
        interface_data = json.loads((root / 'cfg/interfaces.json').read_text(encoding='utf-8'))
        generated = render(interface_data)
        for name in ['src/sw/generated/interfaces.inc', 'tools/n2m/generated_interfaces.py']:
            if (root / name).read_text(encoding='utf-8') != generated[Path(name)]:
                fail('SCHEMA_MISMATCH', 'generated interface export is stale: ' + name)
        if hw.PROFILE_NAME != target['profile']:
            fail('PROFILE_MISMATCH', 'target differs from generated runtime profile')
        tree = confined(root / 'src/sw', target['directory'])
        layout_path = confined(tree, target['layout'])
        layout = json.loads(layout_path.read_text(encoding='utf-8'))
        if layout_path in [confined(tree, source) for source in target['sources']]:
            fail('PRIVATE_PATH', 'layout and source inputs must not overlap')
        assembly = assemble_target(root, build, args, provenance)
        if assembly['status'] != 'PASS':
            diagnostic_file = next(name for name in assembly['artifacts'] if name.endswith('diagnostics.json'))
            diagnostics = json.loads((root / diagnostic_file).read_text(encoding='utf-8'))
            if type(diagnostics) is not list or not diagnostics or type(diagnostics[0]) is not dict:
                fail('SCHEMA_MISMATCH', 'assembly failure has malformed diagnostic evidence')
            error = AssemblyError('ASSEMBLY_FAILED', assembly.get('error', 'assembly failed'))
            error.diagnostic = diagnostics[0]
            raise error
        objects = [read_json(root / name) for name in assembly['objects']]
        linked = link(list(zip(target['sources'], objects)), layout, target['entry'], target['profile'])
        rom = package(linked, target['title'], target['version'], target['profile'])
        inputs = dict(assembly['inputs'])
        inputs[layout_path.relative_to(root).as_posix()] = file_hash(layout_path)
        inputs['tools/n2m/interfaces.py'] = file_hash(root / 'tools/n2m/interfaces.py')
        for path in sorted((root / 'tools/sw').glob('*')):
            if path.suffix in ('.py', '.json'):
                inputs[path.relative_to(root).as_posix()] = file_hash(path)
        outputs = {'image.gb': rom, 'map.json': json_bytes(linked['map']),
                   'symbols.json': json_bytes(linked['symbols']), 'listing.json': json_bytes(linked['listing']),
                   'diagnostics.json': json_bytes([])}
        outputs.update({f'{index}.object.json': json_bytes(obj) for index, obj in enumerate(objects)})
        outputs.update({name: (root / relative).read_bytes() for name, relative in assembly.get('asset_outputs', {}).items()})
        fingerprint = digest({'inputs': inputs, 'target': target})
        report.update(inputs=inputs, fingerprint=fingerprint, profile=target['profile'], entry=linked['entry'])
        previous = read_json(stage / 'result.json')
        prior_name = previous.get('attempt')
        complete = type(prior_name) is str and re.fullmatch('[0-9a-f]{12}', prior_name)
        if complete:
            prior = stage / 'runs' / prior_name
            expected = {p.relative_to(root).as_posix() for p in [prior / name for name in outputs]}
            complete = (previous.get('rom') == (prior / 'image.gb').relative_to(root).as_posix()
                        and set(previous.get('artifacts', {})) == expected and read_json(prior / 'result.json') == previous
                        and all((prior / name).is_file() and (prior / name).read_bytes() == value for name, value in outputs.items()))
        if not args.rebuild and complete and cache_matches(previous, fingerprint, root, build):
            return {**previous, **provenance, 'cache': 'HIT', 'reused_from': previous.get('commit')}
        for name, value in outputs.items():
            (folder / name).write_bytes(value)
        report.update(status='PASS', cache='MISS', attempt=folder.name,
                      artifacts={(folder / name).relative_to(root).as_posix(): file_hash(folder / name) for name in outputs},
                      rom=(folder / 'image.gb').relative_to(root).as_posix())
    except Exception as error:
        diagnostic = error.diagnostic if isinstance(error, AssemblyError) else {
            'code': 'SCHEMA_MISMATCH', 'stage': 'link', 'cause': str(error),
            'span': {'file': 'targets.json', 'line': 1, 'column': 1}}
        atomic_json(folder / 'diagnostics.json', [diagnostic])
        report.update(status='FAIL', error=str(error),
                      artifacts={(folder / 'diagnostics.json').relative_to(root).as_posix(): file_hash(folder / 'diagnostics.json')})
    atomic_json(folder / 'result.json', report)
    atomic_json(stage / 'result.json', report)
    return report
