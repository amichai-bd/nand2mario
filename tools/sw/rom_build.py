"""Immutable tagged software build publication with complete output inventories."""
import json
from pathlib import Path
import re
import uuid
from n2m.records import atomic_json, cache_matches, digest, file_hash, read_json
from .build import assemble_target
from .expressions import AssemblyError
from .linker import fail, link
from .package import package


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode('utf-8')


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
                or type(definitions['schema_version']) is not int or definitions['schema_version'] != 1
                or type(definitions['targets']) is not dict or safe != args.target):
            fail('SCHEMA_MISMATCH', 'invalid software target registry')
        target = definitions['targets'].get(args.target)
        if type(target) is not dict or set(target) != {'directory', 'sources', 'assets', 'layout', 'entry', 'title', 'version', 'profile', 'interface_schema_version'}:
            fail('SCHEMA_MISMATCH', 'complete software build target required')
        if type(target['interface_schema_version']) is not int or target['interface_schema_version'] != 1:
            fail('SCHEMA_MISMATCH', 'unsupported interface schema identity')
        def confined(base, name):
            if type(name) is not str or not name or Path(name).is_absolute() or '..' in Path(name).parts or ':' in name or '\\' in name:
                fail('PRIVATE_PATH', 'target-relative confined path required')
            path = base / name
            if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
                fail('PRIVATE_PATH', 'path escapes target ownership')
            return path.resolve()
        tree = confined(root / 'src/sw', target['directory'])
        layout_path = confined(tree, target['layout'])
        layout = json.loads(layout_path.read_text(encoding='utf-8'))
        if layout_path in [confined(tree, source) for source in target['sources']]:
            fail('PRIVATE_PATH', 'layout and source inputs must not overlap')
        assembly = assemble_target(root, build, args, provenance)
        if assembly['status'] != 'PASS':
            diagnostic_file = next(name for name in assembly['artifacts'] if name.endswith('diagnostics.json'))
            diagnostics = read_json(root / diagnostic_file)
            error = AssemblyError('ASSEMBLY_FAILED', assembly.get('error', 'assembly failed'))
            error.diagnostic = diagnostics[0]
            raise error
        objects = [read_json(root / name) for name in assembly['objects']]
        linked = link(list(zip(target['sources'], objects)), layout, target['entry'], target['profile'])
        rom = package(linked, target['title'], target['version'], target['profile'])
        inputs = dict(assembly['inputs'])
        inputs[layout_path.relative_to(root).as_posix()] = file_hash(layout_path)
        for path in sorted((root / 'tools/sw').glob('*')):
            if path.suffix in ('.py', '.json'):
                inputs[path.relative_to(root).as_posix()] = file_hash(path)
        outputs = {'image.gb': rom, 'map.json': json_bytes(linked['map']),
                   'symbols.json': json_bytes(linked['symbols']), 'listing.json': json_bytes(linked['listing']),
                   'diagnostics.json': json_bytes([])}
        outputs.update({f'{index}.object.json': json_bytes(obj) for index, obj in enumerate(objects)})
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
