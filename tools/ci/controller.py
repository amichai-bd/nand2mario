"""Explicit local controller; the checked-in bootstrap always exits inactive."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from .github import GitHub
from .model import admit, canonical, config, context, digest, request, require, PROFILES
from .profiles import child_command, check_record
from .storage import consume, file_hash, freeze, inventory, machine_lock, machine_state

ROOT = Path(__file__).resolve().parents[2]


def now():
    return datetime.now(timezone.utc).isoformat()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def sources(root, cfg, req):
    require(git(root, 'rev-parse', 'HEAD') == req['sha'], 'controller source SHA')
    require(not git(root, 'status', '--porcelain', '--untracked-files=all'), 'controller checkout is not clean')
    require(git(root, 'hash-object', cfg['workflow_path']) == cfg['workflow_blob'], 'local workflow blob')
    require(json.loads((root / 'cfg/trusted-ci.json').read_text(encoding='utf-8')) == cfg,
            'fixed tracked configuration')
    flags = git(root, 'ls-files', '-v', '-z').split('\0')
    require(all(item.startswith('H ') for item in flags if item), 'hidden index flags are unsupported')
    tree = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-rz', '--full-tree', req['sha']])
    entries = []
    for entry in tree.split(b'\0'):
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode('ascii').split()
        require(mode in ('100644', '100755') and kind == 'blob', 'non-file controller source')
        entries.append((name.decode('utf-8'), blob))
    require({item[2:] for item in flags if item} == {name for name, _ in entries}, 'index/commit file inventory')
    batch = subprocess.run(['git', '-C', str(root), 'cat-file', '--batch'],
                           input=('\n'.join(blob for _, blob in entries) + '\n').encode('ascii'),
                           capture_output=True, check=True).stdout
    offset = 0
    hashes = {}
    for name, expected_blob in entries:
        end = batch.index(b'\n', offset)
        blob, kind, size = batch[offset:end].decode('ascii').split()
        require(blob == expected_blob and kind == 'blob', 'authorized Git blob identity')
        start = end + 1; offset = start + int(size) + 1
        expected = batch[start:offset - 1]
        path = root / name
        require(not path.is_symlink() and path.resolve().is_relative_to(root.resolve()), 'source path boundary')
        actual = path.read_bytes()
        require(actual == expected or (b'\0' not in expected and actual.replace(b'\r\n', b'\n') == expected),
                'source bytes differ from authorized Git blob: ' + name)
        hashes[name] = file_hash(path)
    require(offset == len(batch), 'complete Git blob stream')
    return hashes


def child_environment():
    # Explicit OS/license data only. In particular no GH/GITHUB token is inherited.
    names = ('SystemRoot', 'WINDIR', 'COMSPEC', 'PATH', 'PATHEXT', 'TEMP', 'TMP',
             'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'LM_LICENSE_FILE',
             'MGLS_LICENSE_FILE', 'SALT_LICENSE_SERVER')
    return {k: os.environ[k] for k in names if k in os.environ}


def run_profile(root, cfg, req, invocation, folder, tools, recheck):
    checkout = folder / 'checkout'
    # Leave the checkout and complete evidence retained for audit after success/failure.
    subprocess.run(['git', '-C', str(root), 'worktree', 'add', '--detach', str(checkout), req['sha']],
                   check=True, capture_output=True, text=True)
    require(git(checkout, 'rev-parse', 'HEAD') == req['sha'], 'isolated checkout identity')
    results = []
    for index, target in enumerate(PROFILES[req['profile']]):
        recheck()
        tag = 'trusted-' + invocation + '-' + str(index)
        argv = child_command(checkout, req['profile'], target, tag, tools, sys.executable)
        output = folder / f'child-{index}'
        output.mkdir()
        freeze(output / 'command.json', {'argv': argv, 'cwd': str(checkout), 'started': now()})
        # Existing fixed builder stages own bounded tool timeouts. Finish the running
        # bounded stage before rechecking cancellation; never launch another after it.
        result = subprocess.run(argv, cwd=checkout, env=child_environment(), capture_output=True, text=True)
        (output / 'stdout.json').write_text(result.stdout, encoding='utf-8')
        (output / 'stderr.log').write_text(result.stderr, encoding='utf-8')
        freeze(output / 'exit.json', {'exit_code': result.returncode, 'finished': now()})
        require(not result.stderr.strip(), 'unexpected child stderr')
        record = json.loads(result.stdout)
        checked = check_record(checkout, req, req['profile'], target, tag, result.returncode, record, tools)
        results.append({'argv': argv, 'raw_exit': result.returncode, **checked})
    return results


def execute(root, cfg, req, api, tools, runner=run_profile, locker=machine_lock):
    config(cfg); request(req)
    require(cfg['enabled'], 'trusted CI bootstrap is inactive')
    with locker(cfg['repository_id']):
        source_inventory = sources(root, cfg, req)
        bound = admit(cfg, req, api.snapshot(cfg, req), initial=True)
        require(not any(s['context'] == context(req) for s in api.statuses(cfg, req)),
                'remote attempt already consumed')
        invocation = uuid.uuid4().hex
        state = root / 'workdir/ci'
        consume(machine_state(cfg['repository_id']), cfg, req, invocation)
        folder = state / 'attempts' / invocation
        folder.mkdir(parents=True, exist_ok=False)
        envelope = {'schema': 1, 'request': req, 'admission': bound, 'invocation': invocation,
                    'configuration': cfg, 'controller_sources': source_inventory,
                    'profile': list(PROFILES[req['profile']]), 'started': now(), 'status': 'FAIL'}
        freeze(folder / 'admission.json', envelope)

        def recheck():
            require(sources(root, cfg, req) == source_inventory, 'controller sources changed during execution')
            current = admit(cfg, req, api.snapshot(cfg, req), initial=False)
            require(current == bound, 'admission changed during execution')

        try:
            pending = api.post(cfg, req, 'pending', 'explicit local invocation ' + invocation,
                               bound['context'], bound['url'])
            freeze(folder / 'pending-status.json', pending)
            envelope['runs'] = runner(root, cfg, req, invocation, folder, tools, recheck)
            require(len(envelope['runs']) == len(PROFILES[req['profile']]), 'complete fixed profile')
            recheck()
            envelope['status'] = 'PASS'
        except Exception as error:
            envelope['error'] = str(error)
        envelope['finished'] = now()
        envelope['retained_files'] = inventory(folder)
        envelope_digest = freeze(folder / 'envelope.json', envelope)
        # Failed revalidation suppresses publication, leaving the consumed journal
        # and full evidence. The hosted waiter will fail on cancellation/timeout.
        recheck()
        final = api.post(cfg, req, 'success' if envelope['status'] == 'PASS' else 'failure',
                         'attested sha256:' + envelope_digest, bound['context'], bound['url'])
        freeze(folder / 'final-status.json', final)
        return {'status': envelope['status'], 'envelope': str(folder / 'envelope.json'),
                'sha256': envelope_digest}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--run-id', type=int, required=True)
    parser.add_argument('--attempt', type=int, required=True)
    parser.add_argument('--profile', choices=tuple(PROFILES), required=True)
    parser.add_argument('--questa-bin')
    parser.add_argument('--quartus-bin')
    args = parser.parse_args(argv)
    try:
        cfg = config(json.loads((ROOT / 'cfg/trusted-ci.json').read_text(encoding='utf-8')))
        require(cfg['enabled'], 'trusted CI bootstrap is inactive; activation belongs to #32')
        req = request({'sha': args.sha, 'run_id': args.run_id, 'attempt': args.attempt, 'profile': args.profile})
        tools = {'questa': args.questa_bin, 'quartus': args.quartus_bin}
        needed = 'questa' if req['profile'] == 'questa-baseline' else 'quartus'
        require(tools[needed] and Path(tools[needed]).is_absolute(), 'explicit local tool directory required')
        token = os.environ.pop('GH_TOKEN', None)
        result = execute(ROOT, cfg, req, GitHub(token), tools)
        print(json.dumps(result))
        return 0 if result['status'] == 'PASS' else 1
    except Exception as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
