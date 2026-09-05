"""Tagged assembler integration; emits relocatable JSON, never a cartridge."""
import json
from pathlib import Path
import re
import uuid

from n2m.records import atomic_json, cache_matches, digest, file_hash, read_json
from .assembler import assemble
from .expressions import AssemblyError
from .objects import validate


def assemble_target(root, build, args, provenance):
    safe_target = args.target if re.fullmatch('[a-z0-9][a-z0-9_-]*', args.target) else 'invalid-target'
    stage = build / 'sw/assemble' / safe_target
    folder = stage / 'runs' / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    try:
        return _assemble_target(root, build, args, provenance, stage, folder)
    except Exception as error:
        diagnostic = error.diagnostic if isinstance(error, AssemblyError) else {
            'code': 'SYNTAX', 'stage': 'assemble', 'cause': str(error),
            'span': {'file': 'targets.json', 'line': 1, 'column': 1}}
        atomic_json(folder / 'diagnostics.json', [diagnostic])
        report = {'status': 'FAIL', 'target': args.target, **provenance, 'error': str(error),
                  'artifacts': {(folder / 'diagnostics.json').relative_to(root).as_posix(): file_hash(folder / 'diagnostics.json')}}
        atomic_json(folder / 'result.json', report)
        atomic_json(stage / 'result.json', report)
        return report


def _assemble_target(root, build, args, provenance, stage, folder):
    if not re.fullmatch('[a-z0-9][a-z0-9_-]*', args.target):
        raise AssemblyError('SYNTAX', 'invalid target name')
    registry = root / 'src/sw/targets.json'
    data = json.loads(registry.read_text())
    if set(data) != {'schema_version', 'targets'} or type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise AssemblyError('SCHEMA_MISMATCH', 'unsupported software target registry')
    target = data['targets'].get(args.target)
    if not isinstance(target, dict) or set(target) != {'directory', 'sources', 'assets'}:
        raise AssemblyError('SYNTAX', 'unknown or malformed software target')

    def confined(base, spelling):
        path = Path(spelling)
        if path.is_absolute() or '..' in path.parts or ':' in spelling or '\\' in spelling:
            raise AssemblyError('PRIVATE_PATH', 'target path must be relative without traversal')
        result = base / path
        if not result.resolve().is_relative_to(base.resolve()) or result.is_symlink():
            raise AssemblyError('PRIVATE_PATH', 'target path escapes its owner')
        return result.resolve()

    tree = confined(root / 'src/sw', target['directory'])
    if not isinstance(target['sources'], list) or not target['sources']:
        raise AssemblyError('SYNTAX', 'ordered assembly sources required')
    paths = [confined(tree, name) for name in target['sources']]
    if len(paths) != len(set(paths)):
        raise AssemblyError('SYNTAX', 'duplicate resolved assembly source')
    if not isinstance(target['assets'], dict):
        raise AssemblyError('SYNTAX', 'declared generated asset map required')
    assets = {}
    for name, relative in target['assets'].items():
        path = confined(root / 'workdir', relative)
        assets[name] = path.read_bytes()
    report = {'status': 'FAIL', 'target': args.target, **provenance,
              'scope': 'relocatable assembly objects; no link placement or cartridge packaging'}
    try:
        objects = [assemble(path, tree, root / 'src/sw/generated/interfaces.inc', assets) for path in paths]
        implementation = [root / 'tools/sw' / name for name in
                          ('assembler.py', 'expressions.py', 'objects.py', 'build.py', 'opcodes.json',
                           'object.schema.json', 'targets.schema.json')]
        implementation += [root / name for name in ('tools/n2m/records.py', 'tools/n2m/cli.py',
                            'tools/n2m/generated_interfaces.py', 'cfg/interfaces.json')]
        inputs = {path.relative_to(root).as_posix(): file_hash(path) for path in implementation + [registry]}
        source_paths = {root / 'src/sw/generated/interfaces.inc'}
        for obj in objects:
            source_paths.update(tree / name for name in obj['sources']
                                if not name.startswith(('__n2m__/', '__assets__/')))
        source_paths.update(confined(root / 'workdir', relative) for relative in target['assets'].values())
        inputs.update({path.relative_to(root).as_posix(): file_hash(path) for path in source_paths})
        fingerprint = digest({'objects': objects, 'implementation': inputs})
        report.update(fingerprint=fingerprint, inputs=inputs)
        previous = read_json(stage / 'result.json')
        retained = previous.get('objects', [])
        complete = type(retained) is list and len(retained) == len(objects)
        if complete:
            parents = {(root / relative).parent for relative in retained}
            complete = len(parents) == 1
            if complete:
                prior_folder = next(iter(parents))
                expected_files = [prior_folder / (str(i) + '.object.json') for i in range(len(objects))]
                expected_files.append(prior_folder / 'diagnostics.json')
                complete = (prior_folder.parent == stage / 'runs'
                            and re.fullmatch('[0-9a-f]{12}', prior_folder.name)
                            and retained == [p.relative_to(root).as_posix() for p in expected_files[:-1]]
                            and set(previous.get('artifacts', {})) == {p.relative_to(root).as_posix() for p in expected_files}
                            and read_json(prior_folder / 'result.json') == previous)
        if complete:
            complete = all((root / relative).is_file() and (root / relative).read_bytes() ==
                           (json.dumps(obj, indent=2, sort_keys=True) + '\n').encode('utf-8')
                           for relative, obj in zip(retained, objects))
        if not args.rebuild and complete and cache_matches(previous, fingerprint, root, build):
            # Parsing still revalidates every source/include and its schema; only
            # identical previously retained object bytes may be returned.
            for relative in previous.get('objects', []):
                validate(read_json(root / relative))
            return {**previous, **provenance, 'cache': 'HIT', 'reused_from': previous.get('commit')}
        output = []
        for index, obj in enumerate(objects):
            path = folder / (str(index) + '.object.json')
            atomic_json(path, obj)
            output.append(path.relative_to(root).as_posix())
        report.update(status='PASS', cache='MISS', objects=output)
        atomic_json(folder / 'diagnostics.json', [])
    except AssemblyError as error:
        report['error'] = str(error)
        atomic_json(folder / 'diagnostics.json', [error.diagnostic])
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['error'] = str(error)
        atomic_json(folder / 'diagnostics.json', [{'code': 'SYNTAX', 'stage': 'assemble', 'cause': str(error)}])
    report['artifacts'] = {p.relative_to(root).as_posix(): file_hash(p) for p in folder.iterdir() if p.is_file()}
    atomic_json(folder / 'result.json', report)
    atomic_json(stage / 'result.json', report)
    return report
