"""Synthetic complete builder records: host proofs, never licensed evidence."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
from tools.n2m.hdl import dependencies
import unittest
from tools.ci import profiles, storage
from tools.n2m import questa, fpga, fpga_pll
from tools.n2m.records import atomic_json, digest, git_state

REPO = Path(__file__).resolve().parents[3]


class ProfileTests(unittest.TestCase):
    def setUp(self):
        base = REPO / 'workdir/.tmp'; base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=base)
        self.base = Path(self.temp.name); self.root = self.base / 'repo'; self.root.mkdir()
        self.bin = self.base / 'installed/bin'; self.bin.mkdir(parents=True)
        self.tools = {'questa': str(self.bin), 'quartus': str(self.bin)}
    def tearDown(self): self.temp.cleanup()

    def write(self, path, text='host fixture\n'):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def binary(self, name):
        path = self.write(self.bin / (name + ('.exe' if os.name == 'nt' else '')))
        return {'path': str(path.resolve()), 'sha256': storage.file_hash(path)}

    def simulation_record(self, broken=False):
        target = 'baseline-broken' if broken else 'baseline-good'
        definitions = json.loads((REPO / 'src/dv/builder/targets.json').read_text(encoding='utf-8'))
        definition = deepcopy(definitions[target]); definition['sources'] = ['src/dv/fixture.sv']
        self.write(self.root / 'src/dv/fixture.sv', 'module fixture; endmodule\n')
        self.write(self.root / 'src/dv/builder/targets.json', json.dumps({target: definition}))
        self.write(self.root / 'tools/n2m/dependencies.json', '{}')
        self.write(self.root / 'tools/build.py', '# synthetic source\n')
        self.write(self.root / '.gitignore', 'workdir/\n')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True,
                                           stderr=subprocess.DEVNULL).strip()
        git('init', '-b', 'main'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'test@example.invalid')
        git('add', '.'); git('commit', '-m', 'Synthetic source')
        self.req = {'sha': git('rev-parse', 'HEAD')}
        self.target = target; self.tag = 'fixture'
        self.build = self.root / 'workdir/builds' / self.tag
        self.stage = self.build / 'sim/test' / target
        self.attempt = self.stage / 'attempts/one'
        self.compiler = self.build / 'compile/questa' / target / 'one'
        self.attempt.mkdir(parents=True); self.compiler.mkdir(parents=True)
        info = {'backend': 'questa', 'tools': {}, 'discovery': []}
        for name in ('vlib', 'vmap', 'vlog', 'vsim'):
            detail = self.binary(name)
            if name != 'vlib':
                detail['version'] = f'Questa synthetic {name}'
                info['discovery'].append({'argv': [detail['path'], '-version'], 'exit_code': 0,
                                          'output': detail['version'] + '\n'})
            info['tools'][name] = detail
        adapter = SimpleNamespace(tools={n: i['path'] for n, i in info['tools'].items()},
                                  path=lambda p: str(Path(p).resolve()))
        commands = []
        for argv, cwd, log, expected in questa.commands(adapter, self.root, definition, 1, self.compiler, self.attempt):
            self.write(log, definition['signature'] + '\nErrors: ' + ('1' if broken else '0') + ', Warnings: 0\n'
                       if log.name == 'sim.log' else 'host fixture\n')
            commands.append({'argv': argv, 'cwd': str(cwd), 'timeout_seconds': 60,
                             'exit_code': 1 if expected == 'nonzero' else 0})
        self.write(self.compiler / 'modelsim.ini')
        self.write(self.attempt / 'waves/simulation.wlf')
        self.write(self.attempt / 'baseline.vcd')
        rows = ['seed,cycle,reset,enable,operand,expected,actual']
        for i in range(1, (6 if broken else 75) + 1):
            rows.append(f'1,{i},0,0,0,0,{128 if broken and i == 6 else 0}')
        self.write(self.attempt / 'transactions.csv', '\n'.join(rows) + '\n')
        if not broken: self.write(self.attempt / 'coverage/bins.txt', 'bins=ff\n')
        self.record = {'status': 'PASS', 'cache': 'BUILT', 'provenance': git_state(self.root),
                       'inputs': profiles.expected_inputs(self.root, 'questa-baseline', target),
                       'tools': info, 'options': {'target': target, 'seed': 1, 'definition': definition},
                       'seed': 1, 'commands': commands, 'artifacts': {}}
        self.republish()

    def republish(self):
        self.record['artifacts'] = {p.relative_to(self.root).as_posix(): storage.file_hash(p)
                                   for directory in (self.attempt, self.compiler) for p in directory.rglob('*')
                                   if p.is_file() and p.name != 'result.json'}
        self.record['fingerprint'] = digest({k: self.record[k] for k in ('inputs', 'tools', 'options')})
        for p in (self.attempt / 'result.json', self.stage / 'result.json', self.build / 'manifest.json'):
            atomic_json(p, self.record)

    def check(self):
        return profiles.check_record(self.root, self.req, 'questa-baseline', self.target,
                                     self.tag, 0, self.record, self.tools)

    def test_complete_synthetic_positive_and_negative(self):
        self.simulation_record()
        self.assertEqual(self.check()['target'], 'baseline-good')
        # Each fixture has an independent clean source repo.
        self.tearDown(); self.setUp(); self.simulation_record(broken=True)
        self.assertEqual(self.check()['target'], 'baseline-broken')

    def test_truncated_inventories_and_changed_raw_evidence(self):
        self.simulation_record()
        files = ['run.do', 'waves/simulation.wlf', 'transactions.csv', 'baseline.vcd', 'coverage/bins.txt']
        for name in files:
            path = self.attempt / name; data = path.read_bytes()
            with self.subTest(name=name):
                path.unlink(); self.republish()
                with self.assertRaises((ValueError, KeyError)): self.check()
                path.write_bytes(data); self.republish()
        self.write(self.attempt / 'transactions.csv', 'truncated\n'); self.republish()
        with self.assertRaises(ValueError): self.check()

    def test_tool_argv_fingerprint_and_source_mutations(self):
        self.simulation_record(); original = deepcopy(self.record)
        mutations = [lambda r: r['tools']['tools']['vsim'].__setitem__('sha256', '0' * 64),
                     lambda r: r['tools'].__setitem__('discovery', []),
                     lambda r: r['commands'][-1]['argv'].append('+unreviewed'),
                     lambda r: r['commands'][3]['argv'].__setitem__(1, '-not-sv'),
                     lambda r: r['commands'][-1].__setitem__('cwd', str(self.root)),
                     lambda r: r['commands'][-1].__setitem__('exit_code', 1),
                     lambda r: r['inputs'].clear()]
        for mutation in mutations:
            self.record = deepcopy(original); mutation(self.record); self.republish()
            with self.assertRaises((ValueError, KeyError)): self.check()
        self.record = deepcopy(original); self.republish()
        self.record['fingerprint'] = '0' * 64
        for p in (self.attempt / 'result.json', self.stage / 'result.json', self.build / 'manifest.json'):
            atomic_json(p, self.record)
        with self.assertRaisesRegex(ValueError, 'fingerprint'): self.check()

    def test_quartus_complete_command_plan_and_identity_mutations(self):
        attempt = self.root / 'attempt'; attempt.mkdir()
        info = {name: self.binary(name) for name in fpga.TOOLS}
        for name, detail in info.items():
            detail['version'] = '25.1std synthetic'
            self.write(attempt / f'{name}-version.log', 'Quartus\nVersion 25.1std synthetic\n')
        self.binary('qmegawiz')
        for name in ('libraries/megafunctions/xml_info/altpll_info.xml', 'libraries/megafunctions/altpll.tdf',
                     'eda/sim_lib/fiftyfivenm_atoms.v', 'eda/sim_lib/altera_primitives.v',
                     'libraries/megafunctions/xml_info/altpll_rules.xml',
                     'libraries/megafunctions/xml_info/altpll_wiz_map.xml'):
            self.write(self.bin.parent / name)
        info['altpll'] = fpga_pll.identity(self.bin)
        definition = {'pll': {'module': 'n2m_pixel_pll', 'input_ps': 20000, 'multiply': 63, 'divide': 125}}
        argv = [[info[n]['path'], '--version'] for n in fpga.TOOLS]
        argv += [fpga_pll.generation_command(info['altpll'], definition['pll']),
                 [info['quartus_sh']['path'], '--flow', 'compile', 'design'],
                 [info['quartus_sta']['path'], '-t', 'audit.tcl'],
                 [info['quartus_eda']['path'], '--simulation', '--tool=modelsim', '--format=verilog', 'design']]
        record = {'inputs': {'owned': 'a'}, 'tools': info, 'definition': definition,
                  'commands': [{'argv': a, 'cwd': str(attempt), 'timed_out': False} for a in argv]}
        record['fingerprint'] = digest({'inputs': record['inputs'], 'tools': info, 'definition': definition, 'timeout': 600})
        def check(value): profiles.validate_commands(self.root, 'quartus-clocking', value, attempt,
                                                    self.root, 'clocking-nominal', self.tools)
        check(record)
        for mutation in (lambda r: r['commands'][6]['argv'].__setitem__(5, 'CLK0_DIVIDE_BY=1'),
                         lambda r: r['tools']['quartus_sta'].__setitem__('sha256', '0' * 64),
                         lambda r: r['commands'][-1].__setitem__('timed_out', True),
                         lambda r: r['commands'][-1]['argv'].append('other-project')):
            changed = deepcopy(record); mutation(changed)
            changed['fingerprint'] = digest({'inputs': changed['inputs'], 'tools': changed['tools'],
                                             'definition': changed['definition'], 'timeout': 600})
            with self.assertRaises(ValueError): check(changed)


    def fpga_record(self, invalid=False):
        self.target = 'clocking-invalid' if invalid else 'clocking-nominal'
        definition = json.loads((REPO / fpga.REGISTRY).read_text(encoding='utf-8'))['targets'][self.target]
        for name in dependencies(REPO, definition['sources'], synthesis=True) + definition['constraints']:
            self.write(self.root / name, (REPO / name).read_text(encoding='utf-8'))
        self.write(self.root / fpga.REGISTRY, json.dumps({'schema_version': 1, 'targets': {self.target: definition}}))
        self.write(self.root / 'tools/build.py', '# synthetic source\n')
        self.write(self.root / 'tools/n2m/fixture.py', '# synthetic source\n')
        self.write(self.root / '.gitignore', 'workdir/\n')
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True,
                                           stderr=subprocess.DEVNULL).strip()
        git('init', '-b', 'main'); git('config', 'user.name', 'Fixture'); git('config', 'user.email', 'test@example.invalid')
        git('add', '.'); git('commit', '-m', 'Synthetic source')
        self.req = {'sha': git('rev-parse', 'HEAD')}; self.tag = 'fixture'
        self.build = self.root / 'workdir/builds' / self.tag
        self.stage = self.build / 'fpga' / self.target
        self.attempt = self.stage / 'attempts/one'; self.attempt.mkdir(parents=True)
        info = {name: self.binary(name) for name in fpga.TOOLS}
        for name, detail in info.items():
            detail['version'] = '25.1std synthetic'
            self.write(self.attempt / f'{name}-version.log', 'Quartus\nVersion 25.1std synthetic\n')
        self.binary('qmegawiz')
        for name in ('libraries/megafunctions/xml_info/altpll_info.xml', 'libraries/megafunctions/altpll.tdf',
                     'eda/sim_lib/fiftyfivenm_atoms.v', 'eda/sim_lib/altera_primitives.v',
                     'libraries/megafunctions/xml_info/altpll_rules.xml',
                     'libraries/megafunctions/xml_info/altpll_wiz_map.xml'):
            self.write(self.bin.parent / name)
        info['altpll'] = fpga_pll.identity(self.bin)
        argv = [[info[n]['path'], '--version'] for n in fpga.TOOLS]
        argv += [fpga_pll.generation_command(info['altpll'], definition['pll']),
                 [info['quartus_sh']['path'], '--flow', 'compile', 'design']]
        if not invalid:
            argv += [[info['quartus_sta']['path'], '-t', 'audit.tcl'],
                     [info['quartus_eda']['path'], '--simulation', '--tool=modelsim', '--format=verilog', 'design']]
        names = ['design.qpf', 'design.qsf', 'checked.sdc', 'audit.tcl', 'n2m_pixel_pll.v',
                 'generate-pll.log', 'compile.log']
        if invalid: names += ['failure.log']
        else:
            names += ['audit.log', 'netlist.log', 'simulation/questa/design.vo']
            names += ['output/' + n for n in (*fpga.REQUIRED_REPORTS, *fpga_pll.required_reports())]
        for name in names: self.write(self.attempt / name)
        self.write(self.attempt / 'checked.sdc', fpga.checked_constraints(definition))
        if invalid:
            self.write(self.attempt / 'compile.log', 'Error (332000): checked endpoint count mismatch: reset_0\n')
            self.write(self.attempt / 'failure.log', 'Quartus exit 3; see compile.log\n')
        self.record = {'status': 'FAIL' if invalid else 'PASS', 'cache': 'BUILT', 'target': self.target,
                       'provenance': git_state(self.root), 'inputs': profiles.expected_inputs(self.root, 'quartus-clocking', self.target),
                       'definition': definition, 'tools': info,
                       'commands': [{'argv': a, 'cwd': str(self.attempt), 'timed_out': False,
                                     'exit_code': 3 if invalid and i == len(argv)-1 else 0} for i, a in enumerate(argv)],
                       'attempt_result': (self.attempt / 'result.json').relative_to(self.root).as_posix()}
        if invalid: self.record['error'] = 'Quartus exit 3; see compile.log'
        else:
            self.record['evidence_directory'] = self.attempt.relative_to(self.root).as_posix()
            self.record['evidence'] = {'synthetic_timing_stub': True}
        self.fpga_republish()

    def fpga_republish(self):
        self.record['artifacts'] = {p.relative_to(self.root).as_posix(): storage.file_hash(p)
                                   for p in self.attempt.rglob('*') if p.is_file() and p.name != 'result.json'}
        self.record['fingerprint'] = digest({k: self.record[k] for k in ('inputs', 'tools', 'definition')} | {'timeout': 600})
        for p in (self.attempt / 'result.json', self.stage / 'result.json', self.build / 'manifest.json'):
            atomic_json(p, self.record)

    def fpga_check(self):
        return profiles.check_record(self.root, self.req, 'quartus-clocking', self.target, self.tag,
                                     1 if self.target == 'clocking-invalid' else 0, self.record, self.tools)

    def test_full_nominal_admission_requires_inventory_and_delegated_timing(self):
        self.fpga_record()
        # The unchanged timing parser owns report semantics and its own lower-level
        # tests. This fixture exercises the complete controller/cache boundary.
        with patch.object(fpga, 'timing_evidence', return_value={'synthetic_timing_stub': True}):
            self.assertEqual(self.fpga_check()['target'], 'clocking-nominal')
            for name in ('output/design.sof', 'checked.sdc', 'simulation/questa/design.vo',
                         'output/chain_pix_release_hold.rpt', 'generate-pll.log'):
                with self.subTest(name=name):
                    path = self.attempt / name; raw = path.read_bytes()
                    path.unlink(); self.fpga_republish()
                    with self.assertRaises(ValueError): self.fpga_check()
                    path.write_bytes(raw); self.fpga_republish()
        with patch.object(fpga, 'timing_evidence', side_effect=ValueError('timing violated')):
            with self.assertRaises(ValueError): self.fpga_check()

    def test_full_invalid_admission_rejects_missing_pre_failure_evidence(self):
        self.fpga_record(invalid=True)
        self.assertEqual(self.fpga_check()['target'], 'clocking-invalid')
        for name in ('design.qpf', 'design.qsf', 'checked.sdc', 'audit.tcl', 'n2m_pixel_pll.v',
                     'generate-pll.log', 'compile.log', 'failure.log'):
            with self.subTest(name=name):
                path = self.attempt / name; raw = path.read_bytes()
                path.unlink(); self.fpga_republish()
                with self.assertRaises((ValueError, OSError)): self.fpga_check()
                path.write_bytes(raw); self.fpga_republish()
        original = deepcopy(self.record)
        for mutate in (lambda r: r['commands'][-2].__setitem__('exit_code', 3),
                       lambda r: r['commands'][-1].__setitem__('exit_code', 0),
                       lambda r: r.__setitem__('error', 'missing tool'),
                       lambda r: r.__setitem__('status', 'PASS')):
            self.record = deepcopy(original); mutate(self.record); self.fpga_republish()
            with self.assertRaises(ValueError): self.fpga_check()
        self.record = deepcopy(original)
        self.write(self.attempt / 'compile.log', 'Error (999): unrelated failure\n'); self.fpga_republish()
        with self.assertRaises(ValueError): self.fpga_check()


    def test_hidden_execution_source_cannot_be_attested_with_new_hashes(self):
        self.simulation_record()
        subprocess.run(['git', '-C', str(self.root), 'update-index', '--assume-unchanged', 'src/dv/fixture.sv'], check=True)
        self.write(self.root / 'src/dv/fixture.sv', 'module changed; endmodule\n')
        self.record['inputs'] = profiles.expected_inputs(self.root, 'questa-baseline', self.target)
        self.record['provenance'] = git_state(self.root)
        self.republish()
        with self.assertRaisesRegex(ValueError, 'hidden index flags'): self.check()


if __name__ == '__main__': unittest.main()
