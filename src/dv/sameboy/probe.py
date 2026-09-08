"""Build the pinned Core and retain unprojected observations of one original ROM."""
import argparse
import hashlib
import json
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
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {'status': 'FAIL', 'scope': 'native Core probe; no ABI/PPU equivalence claim',
              'commands': [], 'inputs': {}}
    prefix = ['wsl', '-d', 'Ubuntu-24.04', '--'] if sys.platform == 'win32' else []

    def run(command, name, cwd=None):
        remaining = max(0.001, 600 - (time.monotonic() - started))
        command = ['timeout', '--kill-after=1s', f'{max(0.001, remaining-2):.3f}s', *command]
        actual = prefix + command
        if sys.platform == 'win32' and cwd:
            actual = prefix[:-1] + ['--cd', linux_path(cwd), '--'] + command
        with (output / (name + '.log')).open('wb') as log:
            completed = subprocess.run(actual, cwd=cwd if not prefix else None,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       timeout=max(0.001, 600 - (time.monotonic() - started)))
        result['commands'].append({'argv': actual, 'returncode': completed.returncode,
                                   'log': name + '.log'})
        completed.check_returncode()
        return (output / (name + '.log')).read_text(encoding='utf-8')

    try:
        manifest = json.loads((HERE / 'sources.json').read_text())
        result['pin'] = manifest['pin']
        image = args.rom.read_bytes()
        if len(image) != manifest['image']['length'] or digest(args.rom) != manifest['image']['sha256']:
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
        # Apply only the recorded original observer; pristine inputs remain elsewhere.
        patch = (HERE / 'observe.patch').read_text(encoding='utf-8')
        if b'\r\n' in (observed / 'Core/display.c').read_bytes():
            patch = patch.replace('\n', '\r\n')
        (output / 'observe.patch').write_bytes(patch.encode('utf-8'))
        result['applied_patch_sha256'] = digest(output / 'observe.patch')
        if not args.baseline:
            run(['patch', '--binary', '-p1', '-i', linux_path(output / 'observe.patch')], 'patch', observed)
        result['observation_mode'] = 'untouched-baseline' if args.baseline else 'observed-cycle-path'
        config = json.loads((ROOT / 'cfg/interfaces.json').read_text())
        header = '/* Generated from cfg/interfaces.json for this attempt. */\n'
        header += ''.join(f'#define PROFILE_{v["name"]} {v["value"]}\n'
                          for v in config['groups']['profile'])
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
             linux_path(HERE / 'profile.c'), linux_path(HERE / 'probe.c'),
             linux_path(observed / 'build/probe-lib/libsameboy.a'), '-lm',
             '-o', linux_path(output / 'probe')], 'link')
        result['executable_sha256'] = digest(output / 'probe')
        run([linux_path(output / 'probe'), linux_path(args.rom)], 'observations')
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
