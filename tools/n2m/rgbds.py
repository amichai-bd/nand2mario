"""Pinned upstream RGBDS installation and a small independent encoding oracle."""
import hashlib
import io
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import uuid
import zipfile

from .records import atomic_json, atomic_text, digest, file_hash


def fetch(item, path, offline):
    """Never replace corrupt cache content silently, including online."""
    if not path.exists():
        if offline:
            raise ValueError(f"offline cache miss: {path.name}")
        with urllib.request.urlopen(item['url'], timeout=60) as response:
            data = response.read(64 * 1024 * 1024 + 1)
        if len(data) > 64 * 1024 * 1024:
            raise ValueError('RGBDS download exceeds 64 MiB')
        if hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError(f"download integrity failure: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    if path.is_symlink() or file_hash(path) != item['sha256']:
        raise ValueError(f"cache integrity failure: {path.name}")
    return path.read_bytes()


def package_tools(data, system):
    """Read two fixed regular members; never extract archive-controlled paths."""
    if system == 'windows-x86_64':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return {name + '.exe': archive.read('bin/' + name + '.exe')
                    for name in ('rgbasm', 'rgblink')}
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:xz') as archive:
        result = {}
        for name in ('rgbasm', 'rgblink'):
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError(f'not a regular RGBDS tool: {name}')
            result[name] = archive.extractfile(member).read()
        return result


def install(root, cache, offline, system=None):
    pin = json.loads((root / 'tools/n2m/dependencies.json').read_text())['rgbds']
    system = system or platform.system().lower() + '-x86_64'
    if platform.machine().lower() not in ('amd64', 'x86_64') or system not in pin['packages']:
        raise ValueError('RGBDS prebuilt installation supports Windows/Linux x86_64 only')
    package = pin['packages'][system]
    data = fetch(package, cache / 'package', offline)
    expected = package_tools(data, system)
    for name, content in expected.items():
        path = cache / 'bin' / name
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                raise ValueError(f'installed tool integrity failure: {name}')
        else:
            # A partial previously installed cache is evidence of loss/corruption.
            if (cache / 'installation.json').exists():
                raise ValueError(f'missing installed tool: {name}')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o755)
    for name, item in pin['notices'].items():
        fetch(item, cache / 'notices' / name, offline)
    provenance = {'kind': 'unmodified upstream prebuilt installation', 'pin': pin,
                  'platform': system, 'tools': {name: file_hash(cache / 'bin' / name) for name in expected},
                  'host': platform.platform(), 'python': platform.python_version(),
                  'local_build_dependencies': [], 'local_changes': 'none'}
    atomic_json(cache / 'installation.json', provenance)
    return pin, {Path(name).stem: cache / 'bin' / name for name in expected}, provenance


def compare(binary, symbols, expected):
    """Literal fixture truth only: no opcode tables or relocation calculations."""
    if (type(expected['size']) is not int or not 1 <= expected['size'] <= 32768
            or type(expected['padding']) is not int or not 0 <= expected['padding'] <= 255):
        raise ValueError('expected fixture size/padding outside supported bounds')
    wanted = bytearray([expected['padding']] * expected['size'])
    occupied = set()
    for region in expected['regions']:
        start, data = region['offset'], bytes.fromhex(region['hex'])
        positions = set(range(start, start + len(data)))
        if start < 0 or start + len(data) > len(wanted) or occupied & positions:
            raise ValueError('invalid or overlapping expected region')
        occupied |= positions
        wanted[start:start + len(data)] = data
    actual_symbols = {}
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) == 2 and not line.startswith(';'):
            actual_symbols[fields[1]] = fields[0].lower()
    mismatch = next((i for i, (a, b) in enumerate(zip(binary, wanted)) if a != b), None)
    if len(binary) != len(wanted) or mismatch is not None:
        raise ValueError(f'expected-byte mismatch: offset={mismatch}, actual_size={len(binary)}, '
                         f'expected_size={len(wanted)}' +
                         (f', actual={binary[mismatch]:02x}, expected={wanted[mismatch]:02x}' if mismatch is not None else ''))
    for name, value in expected['symbols'].items():
        if actual_symbols.get(name) != value.lower():
            raise ValueError(f'symbol mismatch: {name}: actual={actual_symbols.get(name)}, expected={value}')


def oracle(root, build, args, provenance):
    stage = build / 'sw/oracle'
    folder = stage / 'runs' / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    commands = []
    report = {'status': 'FAIL', **provenance, 'commands': commands,
              'scope': 'original encoding/section fixture; no project assembler or CPU conformance claim'}
    def run(command, name):
        commands.append([str(part) for part in command])
        try:
            result = subprocess.run(command, cwd=folder, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', timeout=60)
        except subprocess.TimeoutExpired as error:
            output = error.stdout or b''
            atomic_text(folder / (name + '.log'), output.decode('utf-8', errors='replace') if isinstance(output, bytes) else output)
            atomic_json(folder / (name + '.exit.json'), {'timeout_seconds': 60, 'returncode': None})
            raise ValueError(f'{name} timed out after 60 seconds') from error
        atomic_text(folder / (name + '.log'), result.stdout)
        atomic_json(folder / (name + '.exit.json'), {'returncode': result.returncode})
        if result.returncode:
            raise ValueError(f'{name} exited {result.returncode}; see retained log')
        if 'warning:' in result.stdout.lower():
            raise ValueError(f'{name} emitted a warning; see retained log')
        return result.stdout.strip()
    try:
        pin, tools, installation = install(root, stage / 'cache', args.offline)
        report['installation'] = installation
        for name, executable in tools.items():
            version = run([executable, '--version'], name + '-version')
            if version != name + ' v' + pin['version']:
                raise ValueError(f'{name} version mismatch: {version!r}')
        fixture = root / 'src/sw/oracle'
        expected_path = Path(args.expected).resolve() if args.expected else fixture / 'expected.json'
        inputs = [fixture / 'encoding.asm', fixture / 'helper.asm', expected_path,
                  root / 'tools/n2m/dependencies.json', root / 'tools/n2m/rgbds.py']
        report['inputs'] = {str(path): file_hash(path) for path in inputs}
        report['fingerprint'] = digest({'inputs': report['inputs'], 'installation': installation})
        expected = json.loads(expected_path.read_text(encoding='utf-8'))
        atomic_json(folder / 'expected.json', expected)
        for name in ('encoding', 'helper'):
            run([tools['rgbasm'], '-Wall', '-Werror', '-o', folder / (name + '.o'),
                 fixture / (name + '.asm')], name)
        run([tools['rgblink'], '-p', '255', '-o', folder / 'fixture.gb', '-n', folder / 'fixture.sym',
             '-m', folder / 'fixture.map', folder / 'encoding.o', folder / 'helper.o'], 'link')
        compare((folder / 'fixture.gb').read_bytes(), (folder / 'fixture.sym').read_text(), expected)
        report['status'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    # Cache state may change on a later failed request. Preserve this attempt's
    # exact bytes instead of making old evidence depend on mutable cache paths.
    if (stage / 'cache').exists():
        shutil.copytree(stage / 'cache', folder / 'cache-snapshot')
    report['artifacts'] = {path.relative_to(root).as_posix(): file_hash(path)
                           for path in sorted(folder.rglob('*'))
                           if path.is_file() and path.name != 'result.json'}
    atomic_json(folder / 'result.json', report)
    atomic_json(stage / 'result.json', report)
    return report
