"""Build the single locked reg_f fixture; no upstream source or ROM rewriting."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import urllib.request
import zipfile

from .records import file_hash


def pins(root):
    return json.loads((root / 'src/dv/mooneye/pins.json').read_text())


def checked(path, expected):
    if not path.is_file() or file_hash(path) != expected:
        raise ValueError(f'MOONEYE_HASH {path.name}')
    return path


def tool_identity(root, installation):
    """The selected installed compiler/build tools enter the simulation identity."""
    lock = pins(root)
    backend = os.environ.get('N2M_MOONEYE_BUILD_HOST', 'windows')
    if backend == 'wsl':
        from .mooneye_wsl import identity, identity_hash
        result = identity()
        if identity_hash(result) != lock['wsl_host']['sha256']:
            raise ValueError('MOONEYE_WSL_HOST_HASH')
        return result
    if backend != 'windows':
        raise ValueError('MOONEYE_BUILD_HOST')
    tools = {name: str(checked(installation / spec['path'], spec['sha256']))
             for name, spec in lock['host_tools'].items()}
    # Include compiler headers/libraries and CMake modules, not only launchers.
    trees = (installation / 'questa_fse/gcc-7.4.0-mingw64vc16',
             installation / 'riscfree/build_tools/cmake')
    files = {str(path): file_hash(path) for tree in trees for path in tree.rglob('*') if path.is_file()}
    files.update({path: file_hash(Path(path)) for path in tools.values()})
    return {'tools': tools, 'files': files}


def verify_tools(identity):
    if identity.get('backend') == 'wsl':
        from .mooneye_wsl import identity as current
        if current() != identity:
            raise ValueError('MOONEYE_WSL_HOST_CHANGED')
        return
    for path, digest in identity['files'].items():
        checked(Path(path), digest)


def download(spec, destination):
    if destination.exists():
        return checked(destination, spec['sha256'])
    deadline = time.monotonic() + 180
    temporary = destination.with_suffix('.part')
    try:
        with urllib.request.urlopen(spec['url'], timeout=30) as reply, temporary.open('wb') as output:
            count = 0
            while chunk := reply.read(65536):
                count += len(chunk)
                if count > 32 * 1024 * 1024 or time.monotonic() > deadline:
                    raise ValueError('MOONEYE_DOWNLOAD_BOUND')
                output.write(chunk)
        checked(temporary, spec['sha256'])
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def extract(archive, destination, prefix='', *, omit_tests=False):
    """Never execute or extract paths before verifying the locked archive."""
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > 6000 or sum(row.file_size for row in entries) > 64 * 1024 * 1024:
            raise ValueError('MOONEYE_ARCHIVE_BOUND')
        for row in entries:
            if prefix and not row.filename.startswith(prefix):
                raise ValueError('MOONEYE_ARCHIVE_PREFIX')
            name = row.filename[len(prefix):]
            path = (destination / name).resolve()
            if not path.is_relative_to(destination.resolve()) or stat.S_ISLNK(row.external_attr >> 16):
                raise ValueError('MOONEYE_ARCHIVE_PATH')
            # WLA's unused long-filename regression fixtures exceed MAX_PATH.
            # Keep their complete locked archive; CMake does not build this tree.
            if omit_tests and (name == 'tests/' or name.startswith('tests/')):
                continue
            if row.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            elif name:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(source.read(row))


def validate_image(root, image, symbols, *, backend='windows'):
    lock = pins(root)
    selection = dict(lock['selection'])
    if backend == 'wsl':
        selection['image_sha256'] = lock['wsl_host']['image_sha256']
    elif backend != 'windows':
        raise ValueError('MOONEYE_BUILD_HOST')
    if len(image) != 32768 or hashlib.sha256(image).hexdigest() != selection['image_sha256']:
        raise ValueError('MOONEYE_IMAGE_HASH')
    if image[0x100:0x104] != bytes.fromhex('00c35001') or any(image[a] for a in (0x143, 0x146, 0x147, 0x148, 0x149)):
        raise ValueError('MOONEYE_HEADER')
    if image[0x14d] != (-sum(image[0x134:0x14d])-25) & 255:
        raise ValueError('MOONEYE_HEADER_CHECKSUM')
    if int.from_bytes(image[0x14e:0x150], 'big') != (sum(image[:0x14e])+sum(image[0x150:])) & 65535:
        raise ValueError('MOONEYE_GLOBAL_CHECKSUM')
    matches = re.findall(r'^([0-9a-fA-F]{2}):([0-9a-fA-F]{4}) quit@serial_dump$', symbols, re.M)
    if matches != [('01', '4a81')] or image[0x4a81] != 0x40:
        raise ValueError('MOONEYE_COMPLETION_SYMBOL')
    return selection


def prepare(root, attempt, identity):
    from .preload import emit, verify

    verify_tools(identity)
    lock = pins(root)
    dependencies = attempt / 'deps'
    dependencies.mkdir()
    commands = []

    def run(argv, name):
        if identity.get('backend') == 'wsl':
            from .mooneye_wsl import command
            argv = command(argv, attempt)
        expired = None
        try:
            result = subprocess.run([str(value) for value in argv], cwd=attempt,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=120)
            output, code = result.stdout, result.returncode
        except subprocess.TimeoutExpired as error:
            expired = error
            output, code = error.stdout or b'', None
            if isinstance(output, bytes):
                output = output.decode('utf-8', errors='replace')
        (attempt / (name+'.log')).write_text(output)
        linux_timeout = identity.get('backend') == 'wsl' and code in (124, 137)
        commands.append({'argv': [str(value) for value in argv], 'cwd': str(attempt),
                         'exit_code': code, 'timed_out': expired is not None or linux_timeout})
        (attempt / 'mooneye-build-commands.json').write_text(json.dumps(commands, indent=2))
        if expired is not None or linux_timeout:
            raise ValueError(f'MOONEYE_BUILD_TIMEOUT {name}') from expired
        if code:
            raise ValueError(f'MOONEYE_BUILD {name}')
        # This exact upstream minimum-CMake warning is explained in the owner notice.
        notice = ('CMake Deprecation Warning at CMakeLists.txt:1 (cmake_minimum_required):\n'
                  '  Compatibility with CMake < 3.10 will be removed from a future version of\n'
                  '  CMake.\n\n'
                  '  Update the VERSION argument <min> value.  Or, use the <min>...<max> syntax\n'
                  '  to tell CMake that the project requires at least <min> but has been updated\n'
                  '  to work with policies introduced by <max> or earlier.\n')
        output = output.replace(notice, '')
        wsl_notice = ('CMake Deprecation Warning at CMakeLists.txt:1 (cmake_minimum_required):\n'
                      '  Compatibility with CMake < 3.5 will be removed from a future version of\n'
                      '  CMake.\n\n'
                      '  Update the VERSION argument <min> value or use a ...<max> suffix to tell\n'
                      '  CMake that the project does not need compatibility with older versions.\n')
        output = output.replace(wsl_notice, '')
        if re.search(r'\b(warning|error)\b', output, re.I):
            raise ValueError(f'MOONEYE_BUILD_DIAGNOSTIC {name}')

    for name in ('mooneye', 'wla_dx', 'font'):
        archive = download(lock[name], dependencies / (name+'.zip'))
        prefix = {'mooneye': 'mooneye-test-suite-'+lock['mooneye']['commit']+'/',
                  'wla_dx': 'wla-dx-'+lock['wla_dx']['commit']+'/', 'font': ''}[name]
        extract(archive, dependencies / name, prefix, omit_tests=name == 'wla_dx')
    source = dependencies / 'mooneye'
    wla = dependencies / 'wla_dx'
    checked(source/'LICENSE', lock['mooneye']['license_sha256'])
    checked(wla/'LICENSE', lock['wla_dx']['license_sha256'])
    checked(source/'common/font.bin', lock['font']['mooneye_font_sha256'])
    checked(dependencies/'font/font.c', lock['font']['source_sha256'])
    shutil.copyfile(root/'src/rtl/ppu/GPL-3.0.txt', dependencies/'font/GPL-3.0.txt')
    shutil.copyfile(root/'src/dv/mooneye/THIRD_PARTY.md', dependencies/'THIRD_PARTY.md')
    tools = identity['tools']
    build = attempt/'w'
    is_wsl = identity.get('backend') == 'wsl'
    run([tools['cmake'], '-S', wla, '-B', build, '-G', 'Unix Makefiles' if is_wsl else 'MinGW Makefiles',
         '-DCMAKE_MAKE_PROGRAM='+tools['make'], '-DCMAKE_C_COMPILER='+tools['gcc'],
         '-DCMAKE_AR='+tools['ar'], '-DCMAKE_BUILD_TYPE=Release'], 'mooneye-configure')
    run([tools['cmake'], '--build', build, '--target', 'wla-gb', 'wlalink', '--parallel', '2'], 'mooneye-tools')
    suffix = '' if is_wsl else '.exe'
    assembler, linker = build/('binaries/wla-gb'+suffix), build/('binaries/wlalink'+suffix)
    run([assembler, '-I', source/'common', '-o', attempt/'reg_f.o', source/lock['selection']['source']], 'mooneye-assemble')
    object_path = (attempt/'reg_f.o').as_posix()
    if is_wsl:
        from .mooneye_wsl import linux_path
        object_path = linux_path(attempt/'reg_f.o')
    (attempt/'reg_f.link').write_text('[objects]\n"'+object_path+'"\n')
    run([linker, '-d', '-S', attempt/'reg_f.link', attempt/'program.gb'], 'mooneye-link')
    image = (attempt/'program.gb').read_bytes()
    verify_tools(identity)
    selection = validate_image(root, image, (attempt/'program.sym').read_text(),
                               backend=identity.get('backend', 'windows'))
    record = {'selection': selection, 'pins': lock, 'commands': commands,
              'extraction': {'wla_dx_omitted': ['tests/'],
                             'reason': 'Unused upstream filename-regression fixtures exceed Windows MAX_PATH; complete archive retained.'},
              'host_tools': identity, 'built_tools': {str(p): file_hash(p) for p in (assembler, linker)},
              'source_files': {str(p.relative_to(dependencies)): file_hash(p)
                               for p in dependencies.rglob('*') if p.is_file()}}
    (attempt/'mooneye-build.json').write_text(json.dumps(record, indent=2))
    emit(image, attempt, selection['image_sha256'], 0x150,
         image[0x134:0x144].rstrip(b'\0').decode('ascii'), image[0x14c], fixture='mooneye-reg-f')
    verify(attempt)
