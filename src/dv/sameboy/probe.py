"""Build the pinned Core and retain unprojected observations of one original ROM."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.n2m.records import digest as record_digest

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
FLAGS = ['-DGB_INTERNAL', '-DGB_DISABLE_TIMEKEEPING', '-DGB_DISABLE_REWIND',
         '-DGB_DISABLE_DEBUGGER', '-DGB_DISABLE_CHEATS', '-DGB_DISABLE_CHEAT_SEARCH']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def linux_path(path):
    path = path.resolve()
    if sys.platform != 'win32':
        return str(path)
    return '/mnt/' + path.drive[0].lower() + str(path)[2:].replace('\\', '/')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', action='store_true', help='Build untouched Core for observer equivalence')
    parser.add_argument('--case', choices=('integration','palette-fc','palette-00','springtrail-short','springtrail','springtrail-settled-short','springtrail-settled','springtrail-milestone-short','springtrail-milestone'), default='integration')
    parser.add_argument('--fault', choices=('none','frame','input','progress'), default='none')
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    springtrail = args.case.startswith('springtrail')
    if args.fault != 'none' and not springtrail:
        parser.error('fault selection belongs only to the Springtrail reference')
    if springtrail and 'N2M_TEST_EXECUTION_DEADLINE' not in os.environ:
        # The existing supervisor owns the whole native build/run/check invocation.
        relative = args.output.resolve().relative_to(ROOT/'workdir/builds')
        if len(relative.parts) != 2 or relative.parts[1] != 'reference':
            parser.error('Springtrail output must be workdir/builds/<tag>/reference')
        sys.path.insert(0, str(ROOT/'tools'))
        from n2m.test_budget import supervise
        code, text = supervise([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
                               ROOT, relative.parts[0], target='sameboy-springtrail')
        print(text, end='')
        if code:
            raise SystemExit(code)
        return
    started = time.monotonic()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'FAIL', 'scope': 'native Core probe; no ABI/PPU equivalence claim',
              'commands': [], 'inputs': {}}
    prefix = ['wsl', '-d', 'Ubuntu-24.04', '--'] if sys.platform == 'win32' else []

    def remaining():
        if springtrail:
            return max(0.001, float(os.environ['N2M_TEST_EXECUTION_DEADLINE'])-time.time())
        return max(0.001, 600-(time.monotonic()-started))

    def run(command, name, cwd=None):
        command = ['timeout', '--kill-after=1s', f'{max(0.001, remaining()-2):.3f}s', *command]
        actual = prefix + command
        if sys.platform == 'win32' and cwd:
            actual = prefix[:-1] + ['--cd', linux_path(cwd), '--'] + command
        with (output / (name + '.log')).open('wb') as log:
            completed = subprocess.run(actual, cwd=cwd if not prefix else None,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       timeout=remaining())
        result['commands'].append({'argv': actual, 'returncode': completed.returncode,
                                   'log': name + '.log'})
        completed.check_returncode()
        return (output / (name + '.log')).read_text(encoding='utf-8')

    try:
        manifest = json.loads((HERE / 'sources.json').read_text())
        result['pin'] = manifest['pin']
        case_path=HERE/'springtrail.json' if springtrail else ROOT/'src/dv/ppu/palette194.json'
        case=json.loads(case_path.read_text()) if args.case!='integration' else None
        if 'milestone' in args.case:
            from src.dv.sameboy.milestone import contract
            case=contract(case,args.case)
        image_contract=case['settled_image' if any(x in args.case for x in ('settled','milestone')) else 'image'] if springtrail else case['images'][args.case] if case else manifest['image']
        result['case']=args.case
        result['fault']=args.fault
        image = args.rom.read_bytes()
        if len(image) != image_contract['length'] or digest(args.rom) != image_contract['sha256']:
            raise ValueError('Original integration image length/hash mismatch before Core load')
        observed = output / 'core'
        for name, expected in manifest['files'].items():
            path = args.source / name
            if digest(path) != expected:
                raise ValueError('Pinned source mismatch: ' + name)
            target = observed / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            result['inputs']['Core/' + name] = expected
        for path in [HERE / 'profile.c', HERE / 'probe.c', HERE / 'observe.patch',
                     HERE / 'sources.json', HERE / 'scenario.json', HERE / 'retirement.py', Path(__file__), ROOT / 'cfg/interfaces.json', args.rom]:
            result['inputs'][str(path.resolve())] = digest(path)
        if case:result['inputs'][str(case_path.resolve())]=digest(case_path)
        if springtrail:
            for path in (HERE/'springtrail.c', HERE/'springtrail.py', ROOT/'tools/n2m/test_budget.py'):
                result['inputs'][str(path.resolve())]=digest(path)
            if any(x in args.case for x in ('settled','milestone')):
                for name in ('flow_frames.py','interactions_reference.py','movement_reference.py',
                             'reference.py','scene_reference.py','scene_art.py'):
                    path=ROOT/'src/dv/springtrail'/name
                    result['inputs'][str(path.resolve())]=digest(path)
            if 'milestone' in args.case:
                for path in (HERE/'milestone.py',ROOT/'src/dv/springtrail/milestone.py',ROOT/'src/dv/springtrail/interaction_routes.py'):
                    result['inputs'][str(path.resolve())]=digest(path)
                (output/'schedule.json').write_text(json.dumps(case['milestone'],indent=2)+'\n',encoding='utf-8')
        # Apply only the recorded original observer; pristine inputs remain elsewhere.
        patch = (HERE / 'observe.patch').read_text(encoding='utf-8')
        if b'\r\n' in (observed / 'Core/display.c').read_bytes():
            patch = patch.replace('\n', '\r\n')
        (output / 'observe.patch').write_bytes(patch.encode('utf-8'))
        result['applied_patch_sha256'] = digest(output / 'observe.patch')
        if not args.baseline and not springtrail:
            run(['patch', '--binary', '-p1', '-i', linux_path(output / 'observe.patch')], 'patch', observed)
        result['observation_mode'] = 'untouched-baseline' if args.baseline or springtrail else 'observed-cycle-path'
        config = json.loads((ROOT / 'cfg/interfaces.json').read_text())
        header = '/* Generated from cfg/interfaces.json for this attempt. */\n'
        header += ''.join(f'#define PROFILE_{v["name"]} {v["value"]}\n'
                          for v in config['groups']['profile'])
        if springtrail:
            header += f'#define PROBE_FRAME_COUNT {case["cases"][args.case]}\n'
            header += f'#define PROBE_BUTTONS {int(any(x in args.case for x in ("settled","milestone")))}\n'
            header += f'#define PROBE_DOT_BOUND {case["dot_bound"]}\n'
            header += f'#define PROBE_END_DOT {case.get("end_dot",0)}\n#define PROBE_INPUT_COUNT {len(case["inputs"])}\n'
            header += '#define INPUT_DOTS {'+','.join(str(e['dot']) for e in case['inputs'])+'}\n'
            header += '#define INPUT_MASKS {'+','.join(str(e['buttons']) for e in case['inputs'])+'}\n'
        else:
            header += f'#define PROBE_EVENT_BOUND {case["native_event_bound"] if case else 100}\n'
            header += f'#define PROBE_DOT_BOUND {case["native_bound_dots"] if case else 140600}\n'
        (output / 'n2m_profile.h').write_text(header, encoding='utf-8')
        result['profile_header_sha256'] = digest(output / 'n2m_profile.h')
        result['tool_versions'] = run(['clang', '--version'], 'clang-version')
        paths = run(['which', 'clang', 'make', 'ar', 'ld'], 'tool-paths').splitlines()
        result['tool_hashes'] = run(['sha256sum', *paths], 'tool-hashes')
        run(['make', 'build/probe-lib/libsameboy.a', 'OBJ=build/probe-obj',
             'LIBDIR=build/probe-lib', 'CONF=release', 'DISABLE_TIMEKEEPING=1',
             'DISABLE_REWIND=1', 'DISABLE_DEBUGGER=1', 'DISABLE_CHEATS=1', '-j2'],
            'build', observed)
        run(['clang', *FLAGS, '-I' + linux_path(observed), '-I' + linux_path(output),
             linux_path(HERE / 'profile.c'), linux_path(HERE / ('springtrail.c' if springtrail else 'probe.c')),
             linux_path(observed / 'build/probe-lib/libsameboy.a'), '-lm',
             '-o', linux_path(output / 'probe')], 'link')
        result['executable_sha256'] = digest(output / 'probe')
        command = [linux_path(output / 'probe'), linux_path(args.rom)]
        if springtrail:
            command += [linux_path(output/'frames.shades'), args.fault]
        run(command, 'observations')
        if springtrail:
            from src.dv.sameboy.springtrail import check
            ledger = check(output, case, args.case)
            (output/'ledger.json').write_text(json.dumps(ledger, indent=2)+'\n', encoding='utf-8')
        result['status'] = 'PASS'
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        result['elapsed_seconds'] = time.monotonic() - started
        result['artifacts'] = {path.name:digest(path) for path in output.iterdir()
                               if path.is_file() and path.name!='result.json'}
        result['fingerprint'] = record_digest(result['inputs'])
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
