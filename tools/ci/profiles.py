"""Validate fresh fixed-profile builder records before controller attestation."""
import json
import hashlib
import os
import re
from types import SimpleNamespace
from pathlib import Path
from tools.n2m import baseline, fpga, fpga_pll, simulation, questa
from tools.n2m.hdl import dependencies
from tools.n2m.records import git_state, digest as builder_digest
from tools.n2m.questa import diagnostic
from .model import PROFILES, require
from .source import verify_sources
from .storage import beneath, file_hash, inventory


def child_command(root, profile, target, tag, tools, python):
    require(profile in PROFILES and target in PROFILES[profile], 'fixed child profile')
    base = [python, str(root / 'tools/build.py')]
    if profile == 'questa-baseline':
        return base + ['sim', 'test', target, '--sim', 'questa', '--seed', '1',
                       '--questa-bin', tools['questa'], '--tag', tag, '--rebuild', '--json']
    return base + ['fpga', 'build', target, '--quartus-bin', tools['quartus'],
                   '--timeout', '600', '--tag', tag, '--rebuild', '--json']


def expected_inputs(root, profile, target):
    if profile == 'questa-baseline':
        definition, registry = simulation.load_target(root, target)
        paths = dependencies(root, definition['sources']) + [registry.relative_to(root).as_posix(),
                                                               'tools/n2m/dependencies.json']
    else:
        definition = fpga.target_definition(root, target)
        paths = [fpga.REGISTRY, *dependencies(root, definition['sources'], synthesis=True),
                 *definition['constraints']]
    paths += ['tools/build.py', *[p.relative_to(root).as_posix() for p in (root / 'tools/n2m').glob('*.py')]]
    return {p: file_hash(root / p) for p in paths}


def check_artifacts(root, build, record):
    require(type(record['artifacts']) is dict and bool(record['artifacts']), 'missing artifact map')
    for name, expected in record['artifacts'].items():
        path = beneath(root, name)
        require(path.resolve().is_relative_to(build.resolve()) and path.is_file(), 'artifact scope/missing')
        require(file_hash(path) == expected, 'artifact hash mismatch')


def check_record(root, req, profile, target, tag, raw_exit, printed, selected_tools):
    source_inventory = verify_sources(root, req['sha'])
    build = root / 'workdir/builds' / tag
    stage = build / ('sim/test' if profile == 'questa-baseline' else 'fpga') / target
    record = json.loads((stage / 'result.json').read_text(encoding='utf-8'))
    require(all(printed.get(k) == v for k, v in record.items()), 'printed/stage record mismatch')
    clean = builder_digest({'diff': hashlib.sha256(b'').hexdigest(), 'untracked': {}})
    require(git_state(root)['dirty_tree_fingerprint'] == clean, 'execution checkout changed')
    require(record['cache'] == 'BUILT' and record['provenance']['commit'] == req['sha']
            and record['provenance']['dirty_tree_fingerprint'] == git_state(root)['dirty_tree_fingerprint'],
            'fresh authorized source execution')
    require(record['inputs'] == expected_inputs(root, profile, target), 'complete current source inventory')
    require(bool(record['tools']), 'missing tool identities')
    check_artifacts(root, build, record)
    attempts = list((stage / 'attempts').iterdir())
    require(len(attempts) == 1 and attempts[0].is_dir(), 'one fresh immutable attempt')
    attempt = attempts[0]
    require(json.loads((attempt / 'result.json').read_text(encoding='utf-8')) == record,
            'immutable attempt record differs')
    for path in attempt.rglob('*'):
        if path.is_file() and path.name != 'result.json':
            require(path.relative_to(root).as_posix() in record['artifacts'], 'truncated attempt inventory')
    validate_commands(root, profile, record, attempt, build, target, selected_tools)
    if profile == 'questa-baseline':
        definition, _ = simulation.load_target(root, target)
        require(raw_exit == 0 and record['status'] == 'PASS' and record['seed'] == 1
                and record['options'] == {'seed': 1, 'target': target, 'definition': definition},
                'Questa target outcome')
        commands = record['commands']
        names = [Path(c['argv'][0]).stem.lower() for c in commands]
        require(names == ['vmap', 'vlib', 'vmap', 'vlog', 'vmap', 'vmap', 'vsim'],
                'complete Questa compile/elaborate/run commands')
        require(all(c['exit_code'] == 0 for c in commands[:-1]) and
                (commands[-1]['exit_code'] != 0) == (target == 'baseline-broken'), 'raw Questa exits')
        compiler = build / 'compile/questa' / target / attempt.name
        for directory, names in ((compiler, ('ini.log', 'library.log', 'map.log', 'compile.log', 'modelsim.ini')),
                                 (attempt, ('ini.log', 'map.log', 'run.do', 'sim.log', 'waves/simulation.wlf',
                                            'transactions.csv', 'baseline.vcd'))):
            for name in names:
                require((directory / name).relative_to(root).as_posix() in record['artifacts'],
                        'required Questa evidence missing')
        for path in compiler.rglob('*'):
            if path.is_file():
                require(path.relative_to(root).as_posix() in record['artifacts'], 'truncated compile inventory')
        transcript = (attempt / 'sim.log').read_text(encoding='utf-8')
        expected = definition['signature'] if target == 'baseline-broken' else None
        require(definition['signature'] in transcript and diagnostic(transcript, expected) is None,
                'exact Questa expected diagnostic')
        baseline.evidence(root, tag, 1, target == 'baseline-broken')
    else:
        require(record['target'] == target and record['definition'] == fpga.target_definition(root, target),
                'FPGA target identity')
        if target == 'clocking-nominal':
            require(raw_exit == 0 and record['status'] == 'PASS' and
                    fpga.complete_cache(record, record['fingerprint'], root, build, record['definition']),
                    'complete checked FPGA evidence')
            names = [Path(c['argv'][0]).stem.lower() for c in record['commands']]
            require(names == [*fpga.TOOLS, 'qmegawiz', 'quartus_sh', 'quartus_sta', 'quartus_eda'] and
                    all(c['exit_code'] == 0 for c in record['commands']), 'fresh complete FPGA tool chain')
        else:
            require(raw_exit == 1 and record['status'] == 'FAIL', 'intended FPGA negative result')
            commands = record['commands']
            require([Path(c['argv'][0]).stem.lower() for c in commands] ==
                    [*fpga.TOOLS, 'qmegawiz', 'quartus_sh'] and
                    all(c['exit_code'] == 0 for c in commands[:-1]) and commands[-1]['exit_code'] == 3,
                    'intended negative reached compile after successful generation')
            required = ['design.qpf', 'design.qsf', 'checked.sdc', 'audit.tcl',
                        'n2m_pixel_pll.v', 'generate-pll.log', 'compile.log', 'failure.log']
            required += [f'{name}-version.log' for name in fpga.TOOLS]
            for name in required:
                path = attempt / name
                require(path.relative_to(root).as_posix() in record['artifacts'] and path.is_file()
                        and path.stat().st_size > 0, 'required invalid-target evidence: ' + name)
            require((attempt / 'checked.sdc').read_text(encoding='utf-8') ==
                    fpga.checked_constraints(record['definition']), 'invalid-target checked constraints')
            text = (attempt / 'compile.log').read_text(encoding='utf-8')
            require('Error (332000): checked endpoint count mismatch: reset_0' in text and
                    record['error'] == 'Quartus exit 3; see compile.log', 'exact invalid constraint diagnostic')
    return {'target': target, 'record': record, 'source_inventory': source_inventory,
            'complete_build_inventory': inventory(build)}


def executable(info, directory, name):
    expected = (Path(directory) / (name + ('.exe' if os.name == 'nt' else ''))).resolve()
    require(info['path'] == str(expected) and expected.is_file() and info['sha256'] == file_hash(expected),
            'selected executable identity: ' + name)
    return str(expected)


def validate_commands(root, profile, record, attempt, build, target, selected_tools):
    if profile == 'questa-baseline':
        info = record['tools']; directory = selected_tools['questa']
        require(set(info) == {'backend', 'tools', 'discovery'} and info['backend'] == 'questa' and
                set(info['tools']) == {'vlib', 'vmap', 'vlog', 'vsim'}, 'complete Questa identity')
        paths = {name: executable(detail, directory, name) for name, detail in info['tools'].items()}
        require(len(info['discovery']) == 3, 'complete Questa version probes')
        for name, probe in zip(('vmap', 'vlog', 'vsim'), info['discovery']):
            require(probe['argv'] == [paths[name], '-version'] and probe['exit_code'] == 0 and
                    'Questa' in probe['output'] and diagnostic(probe['output']) is None and
                    info['tools'][name]['version'] == probe['output'].strip(), 'Questa version identity')
        definition, _ = simulation.load_target(root, target)
        compiler = build / 'compile/questa' / target / attempt.name
        adapter = SimpleNamespace(tools=paths, path=lambda p: str(Path(p).resolve()))
        expected = questa.commands(adapter, root, definition, 1, compiler, attempt, prepare=False)
        require(len(expected) == len(record['commands']), 'complete Questa argv chain')
        for actual, (argv, cwd, _, _) in zip(record['commands'], expected):
            require(actual['argv'] == argv and actual['cwd'] == str(cwd) and actual['timeout_seconds'] == 60,
                    'exact Questa command arguments/working directory/timeout')
        require(record['fingerprint'] == builder_digest({'inputs': record['inputs'], 'tools': info,
                                                         'options': record['options']}), 'Questa fingerprint')
    else:
        info = record['tools']; directory = selected_tools['quartus']
        require(set(info) == {*fpga.TOOLS, 'altpll'}, 'complete Quartus identity')
        paths = {name: executable(info[name], directory, name) for name in fpga.TOOLS}
        require(info['altpll'] == fpga_pll.identity(directory), 'complete ALTPLL dependency identity')
        for name in fpga.TOOLS:
            text = (attempt / f'{name}-version.log').read_text(encoding='utf-8')
            version = re.search(r'(?m)^Version (.+)$', text)
            require(version and 'Quartus' in text and info[name]['version'] == version[1].strip(),
                    'Quartus version identity')
            fpga.diagnostics(text)
        require(len({info[name]['version'] for name in fpga.TOOLS}) == 1, 'matched Quartus versions')
        expected = [[paths[name], '--version'] for name in fpga.TOOLS]
        expected += [fpga_pll.generation_command(info['altpll'], record['definition']['pll']),
                     [paths['quartus_sh'], '--flow', 'compile', 'design']]
        if target == 'clocking-nominal':
            expected += [[paths['quartus_sta'], '-t', 'audit.tcl'],
                         [paths['quartus_eda'], '--simulation', '--tool=modelsim', '--format=verilog', 'design']]
        require(len(expected) == len(record['commands']), 'complete Quartus argv chain')
        require(all(actual['argv'] == argv and actual['cwd'] == str(attempt) and actual['timed_out'] is False
                    for actual, argv in zip(record['commands'], expected)), 'exact Quartus command arguments/cwd')
        require(record['fingerprint'] == builder_digest({'inputs': record['inputs'], 'tools': info,
                    'definition': record['definition'], 'timeout': 600}), 'Quartus fingerprint')
