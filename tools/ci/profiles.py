"""Validate fresh fixed-profile builder records before controller attestation."""
import json
import hashlib
import os
import platform
import re
from types import SimpleNamespace
from pathlib import Path
from tools.n2m import baseline, fpga, fpga_pll, simulation, verilator
from tools.n2m.hdl import dependencies
from tools.n2m.records import git_state, digest as builder_digest
from tools.n2m.test_budget import target_selection
from tools.n2m.verilator import diagnostic
from .model import PROFILES, require
from .diagnostics import invalid_compile
from .source import verify_sources
from .storage import beneath, file_hash, inventory

BASELINE = 'verilator-baseline'


def child_command(root, profile, target, tag, tools, python):
    require(profile in PROFILES and target in PROFILES[profile], 'fixed child profile')
    base = [python, str(root / 'tools/build.py')]
    if profile == BASELINE:
        return base + ['sim', 'test', target, '--sim', 'verilator', '--seed', '1',
                       '--verilator-bin', tools['verilator'], '--tag', tag, '--rebuild', '--json']
    return base + ['fpga', 'build', target, '--quartus-bin', tools['quartus'],
                   '--timeout', '600', '--tag', tag, '--rebuild', '--json']


def expected_inputs(root, profile, target):
    if profile == BASELINE:
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
    stage = (build / 'sim/test' / target / 'verilator' if profile == BASELINE
             else build / 'fpga' / target)
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
    if profile == BASELINE:
        definition, _ = simulation.load_target(root, target)
        require(raw_exit == 0 and record['status'] == 'PASS' and record['seed'] == 1
                and record['options'] == {'seed': 1, 'target': target, 'definition': definition,
                                          'simulator': 'verilator', 'os': platform.system()},
                'Verilator target outcome')
        commands = record['commands']
        names = [Path(c['argv'][0]).name.lower() for c in commands]
        require(names == ['verilator', 'sim'], 'complete Verilator build/run commands')
        require(commands[0]['exit_code'] == 0 and
                (commands[-1]['exit_code'] != 0) == (target == 'baseline-broken'), 'raw Verilator exits')
        compiler = build / 'compile/verilator' / target / attempt.name
        for directory, names in ((compiler, ('build.log', verilator.HARNESS, 'obj_dir/sim')),
                                 (attempt, ('sim.log', verilator.WAVES, 'transactions.csv', 'baseline.vcd'))):
            for name in names:
                require((directory / name).relative_to(root).as_posix() in record['artifacts'],
                        'required Verilator evidence missing')
        require((compiler / verilator.HARNESS).read_text(encoding='utf-8') == verilator.main_source(definition['top']),
                'retained harness main')
        for path in compiler.rglob('*'):
            if path.is_file():
                require(path.relative_to(root).as_posix() in record['artifacts'], 'truncated compile inventory')
        transcript = (attempt / 'sim.log').read_text(encoding='utf-8')
        expected = definition['signature'] if target == 'baseline-broken' else None
        require(definition['signature'] in transcript and diagnostic(transcript, expected) is None,
                'exact Verilator expected diagnostic')
        baseline.evidence(root, tag, 1, target == 'baseline-broken')
    else:
        require(record['target'] == target and record['definition'] == fpga.target_definition(root, target),
                'FPGA target identity')
        parallel = record['definition']['pll'].get('system_divide') == 2
        generators = ['qmegawiz'] * (2 if parallel else 1)
        if target == 'clocking-nominal':
            require(raw_exit == 0 and record['status'] == 'PASS' and
                    fpga.complete_cache(record, record['fingerprint'], root, build, record['definition']),
                    'complete checked FPGA evidence')
            logs = ['generate-pll.log', 'compile.log', 'audit.log', 'netlist.log']
            if parallel: logs.append('generate-system-pll.log')
            for name in logs:
                text = (attempt / name).read_text(encoding='utf-8')
                explained = fpga_pll.explained_diagnostics(text, attempt, record['definition']['pll']) if 'Warning (176127)' in text else []
                fpga.diagnostics(text, explained)
            names = [Path(c['argv'][0]).stem.lower() for c in record['commands']]
            require(names == [*fpga.TOOLS, *generators, 'quartus_sh', 'quartus_sta', 'quartus_eda'] and
                    all(c['exit_code'] == 0 for c in record['commands']), 'fresh complete FPGA tool chain')
        else:
            require(raw_exit == 1 and record['status'] == 'FAIL', 'intended FPGA negative result')
            commands = record['commands']
            require([Path(c['argv'][0]).stem.lower() for c in commands] ==
                    [*fpga.TOOLS, *generators, 'quartus_sh'] and
                    all(c['exit_code'] == 0 for c in commands[:-1]) and commands[-1]['exit_code'] == 3,
                    'intended negative reached compile after successful generation')
            required = ['design.qpf', 'design.qsf', 'checked.sdc', 'audit.tcl',
                        'n2m_pixel_pll.v', 'generate-pll.log', 'compile.log', 'failure.log']
            if parallel: required += ['n2m_system_pll.v', 'generate-system-pll.log']
            required += [f'{name}-version.log' for name in fpga.TOOLS]
            for name in required:
                path = attempt / name
                require(path.relative_to(root).as_posix() in record['artifacts'] and path.is_file()
                        and path.stat().st_size > 0, 'required invalid-target evidence: ' + name)
            require((attempt / 'checked.sdc').read_text(encoding='utf-8') ==
                    fpga.checked_constraints(record['definition']), 'invalid-target checked constraints')
            fpga.diagnostics((attempt / 'generate-pll.log').read_text(encoding='utf-8'))
            if parallel: fpga.diagnostics((attempt / 'generate-system-pll.log').read_text(encoding='utf-8'))
            text = (attempt / 'compile.log').read_text(encoding='utf-8')
            invalid_compile(text, attempt, selected_tools['quartus'], pll=record['definition']['pll'])
            require(record['error'] == 'Quartus exit 3; see compile.log', 'exact invalid constraint diagnostic')
    return {'target': target, 'record': record, 'source_inventory': source_inventory,
            'complete_build_inventory': inventory(build)}


def executable(info, directory, name):
    expected = (Path(directory) / (name + ('.exe' if os.name == 'nt' else ''))).resolve()
    require(info['path'] == str(expected) and expected.is_file() and info['sha256'] == file_hash(expected),
            'selected executable identity: ' + name)
    return str(expected)


def validate_commands(root, profile, record, attempt, build, target, selected_tools):
    if profile == BASELINE:
        info = record['tools']; directory = selected_tools['verilator']
        require(set(info) == {'backend', 'tools', 'discovery'} and info['backend'] == 'verilator' and
                set(info['tools']) == {'verilator', 'cxx'}, 'complete Verilator identity')
        paths = {'verilator': executable(info['tools']['verilator'], directory, 'verilator')}
        # The C++ compiler is discovered on PATH, not under the selected directory;
        # its recorded path and content hash must still match an existing file.
        compiler_path = Path(info['tools']['cxx']['path'])
        require(compiler_path.is_absolute() and compiler_path.is_file() and
                info['tools']['cxx']['sha256'] == file_hash(compiler_path), 'selected executable identity: cxx')
        paths['cxx'] = str(compiler_path)
        require(len(info['discovery']) == 2, 'complete Verilator version probes')
        for name, probe in zip(('verilator', 'cxx'), info['discovery']):
            require(probe['argv'] == [paths[name], '--version'] and probe['exit_code'] == 0 and
                    diagnostic(probe['output']) is None, 'Verilator version identity')
        verilator_probe, compiler_probe = info['discovery']
        release = re.match(r'Verilator (\d+\.\d+)\b', verilator_probe['output'].strip())
        require(release is not None and info['tools']['verilator']['version'] == verilator_probe['output'].strip()
                and info['tools']['verilator']['release'] == release[1], 'Verilator version identity')
        require(info['tools']['cxx']['version'] == compiler_probe['output'].strip().splitlines()[0],
                'C++ compiler version identity')
        definition, _ = simulation.load_target(root, target)
        compiler = build / 'compile/verilator' / target / attempt.name
        adapter = SimpleNamespace(tools=paths, path=lambda p: str(Path(p).resolve()))
        expected = verilator.commands(adapter, root, definition, 1, compiler, attempt)
        require(len(expected) == len(record['commands']), 'complete Verilator argv chain')
        timeouts = (target_selection(target, definition)[0], definition.get('timeout_seconds', 60))
        for actual, (argv, cwd, log, exit_class), timeout in zip(record['commands'], expected, timeouts):
            require(actual['argv'] == argv and actual['cwd'] == str(cwd) and actual['timeout_seconds'] == timeout,
                    'exact Verilator command arguments/working directory/timeout')
            require(log.is_file(), 'missing Verilator command log')
            require(diagnostic(log.read_text(encoding='utf-8'),
                    definition['signature'] if exit_class == 'nonzero' else None) is None,
                    'unexplained diagnostic in Verilator command log')
        require(record['fingerprint'] == builder_digest({'inputs': record['inputs'], 'tools': info,
                                                         'options': record['options']}), 'Verilator fingerprint')
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
        expected += [fpga_pll.generation_command(info['altpll'], record['definition']['pll'])]
        if record['definition']['pll'].get('system_divide') == 2:
            expected += [fpga_pll._command(info['altpll'], 'n2m_system_pll', 20000, 1, 2, 'LOW')]
        expected += [[paths['quartus_sh'], '--flow', 'compile', 'design']]
        if target == 'clocking-nominal':
            expected += [[paths['quartus_sta'], '-t', 'audit.tcl'],
                         [paths['quartus_eda'], '--simulation', '--tool=modelsim', '--format=verilog', 'design']]
        require(len(expected) == len(record['commands']), 'complete Quartus argv chain')
        require(all(actual['argv'] == argv and actual['cwd'] == str(attempt) and actual['timed_out'] is False
                    for actual, argv in zip(record['commands'], expected)), 'exact Quartus command arguments/cwd')
        require(record['fingerprint'] == builder_digest({'inputs': record['inputs'], 'tools': info,
                    'definition': record['definition'], 'timeout': 600}), 'Quartus fingerprint')
