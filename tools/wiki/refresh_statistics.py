"""Refresh the committed statistics snapshot unattended: collect, commit, push, PR, merge.

A scheduled run needs no agent. It does nothing when the snapshot at origin/main
already records origin/main, or when every commit since the recorded revision
touches only wiki/statistics.html (a merged refresh moves origin/main by itself);
otherwise it regenerates wiki/statistics.html in its
own worktree and lands it through the automated PR class that the PR policy
recognises: branch stats-refresh-<utc>, title "stats: refresh snapshot to <sha7>",
body line "Refs #392", changed-file set exactly wiki/statistics.html.
"""

import argparse
import datetime
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = 'wiki/statistics.html'
STANDING_ISSUE = 392
COLLECTOR = ['tools/wiki/repository_stats.py', '--revision', 'origin/main', '--output', 'workdir/repository-stats',
             '--github', '--exclude-closed-issue', '7', '--html', SNAPSHOT]
CHECK_ATTEMPTS = 30
CHECK_DELAY = 10


class RefreshError(Exception):
    """A plain failure message; the run cleans up and exits non-zero."""


def log(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
    print(f'[{stamp}] {message}', flush=True)


def run(args, cwd=ROOT, timeout=120, check=True):
    """Run one git/gh/python command without a shell; return its stdout text."""
    result = subprocess.run([str(a) for a in args], cwd=str(cwd), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding='utf-8', timeout=timeout)
    if check and result.returncode:
        raise RefreshError(f"{' '.join(str(a) for a in args[:3])} failed ({result.returncode}): "
                           f"{(result.stderr or result.stdout).strip()}")
    return result.stdout


def recorded_revision(html):
    match = re.search(r'Source <code>([0-9a-f]{40})</code>', html)
    if not match:
        raise RefreshError(f'{SNAPSHOT} at origin/main records no source revision')
    return match.group(1)


def timestamp(now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    return now.strftime('%Y%m%dT%H%M%SZ')


def title_for(sha):
    return f'stats: refresh snapshot to {sha[:7]}'


def body_for(sha):
    return f'Refresh the repository statistics snapshot to `{sha}`.\n\nRefs #{STANDING_ISSUE}\n'


def watch_checks(number):
    """Wait for the PR policy check; the workflow registers it a few seconds after creation."""
    for attempt in range(CHECK_ATTEMPTS):
        result = subprocess.run(['gh', 'pr', 'checks', str(number), '--watch'], cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding='utf-8', timeout=1800)
        if result.returncode == 0:
            log(result.stdout.strip())
            return
        if 'no checks reported' not in result.stdout.lower():
            raise RefreshError(f'PR #{number} checks failed: {result.stdout.strip()}')
        time.sleep(CHECK_DELAY)
    raise RefreshError(f'PR #{number} reported no checks after {CHECK_ATTEMPTS * CHECK_DELAY} seconds')


MISSING_REF_TEXTS = ('remote ref does not exist', 'unable to resolve reference')


def delete_remote_branch(branch):
    """Remove the pushed branch; one GitHub already auto-deleted after merge is not a failure.

    The repository deletes merged branches itself, so ask origin first; the error text
    of a late push --delete varies between git versions, so both known forms are tolerated.
    """
    if not run(['git', 'ls-remote', '--heads', 'origin', branch], timeout=300).strip():
        log(f'remote branch {branch} was already deleted')
        return
    try:
        run(['git', 'push', 'origin', '--delete', branch], timeout=300)
    except RefreshError as error:
        if not any(text in str(error) for text in MISSING_REF_TEXTS):
            raise
        log(f'remote branch {branch} was already deleted')


def other_changes(recorded, sha):
    """True when a commit after the recorded revision touches anything but the snapshot.

    A merged refresh is itself a commit on origin/main; without this guard every
    hourly run after one would open another PR that records only the previous one.
    """
    return bool(run(['git', 'log', '--oneline', f'{recorded}..{sha}', '--', '.', f':!{SNAPSHOT}']).strip())


class Refresh:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        self.branch = f'stats-refresh-{timestamp()}'
        self.worktree = ROOT / 'worktrees' / self.branch
        self.pr = None
        self.merged = False
        self.pushed = False

    def collect(self, sha):
        """Return True when the collector changed the snapshot in the worktree."""
        log(f'creating worktree {self.worktree.relative_to(ROOT).as_posix()} on {self.branch}')
        run(['git', 'worktree', 'add', '-b', self.branch, self.worktree, 'origin/main'])
        log('running collector: python ' + ' '.join(COLLECTOR))
        run([sys.executable, *COLLECTOR], cwd=self.worktree, timeout=900)
        changed = run(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=self.worktree).splitlines()
        paths = sorted(line[3:].strip() for line in changed)
        if not paths:
            log(f'collector left {SNAPSHOT} unchanged for {sha}; nothing to publish')
            return False
        if paths != [SNAPSHOT]:
            raise RefreshError(f'collector changed unexpected paths: {paths}')
        return True

    def commit(self, sha):
        run(['git', 'add', '--', SNAPSHOT], cwd=self.worktree)
        run(['git', 'commit', '-q', '-m', title_for(sha), '-m', f'Refs #{STANDING_ISSUE}'], cwd=self.worktree)
        files = run(['git', 'diff', '--name-only', 'origin/main..HEAD'], cwd=self.worktree).split()
        if files != [SNAPSHOT]:
            raise RefreshError(f'commit touches unexpected files: {files}')
        head = run(['git', 'rev-parse', 'HEAD'], cwd=self.worktree).strip()
        log(f'committed {head[:7]} on {self.branch}')
        return head

    def publish(self, sha, head):
        run(['git', 'push', '-u', 'origin', self.branch], cwd=self.worktree, timeout=300)
        self.pushed = True
        body = self.worktree / 'workdir' / 'pr-body.md'
        body.parent.mkdir(parents=True, exist_ok=True)
        body.write_text(body_for(sha), encoding='utf-8')
        url = run(['gh', 'pr', 'create', '--base', 'main', '--head', self.branch, '--title', title_for(sha),
                   '--body-file', body], cwd=self.worktree).strip()
        self.pr = url.rstrip('/').rsplit('/', 1)[-1]
        if not self.pr.isdigit():
            raise RefreshError(f'could not read the PR number from: {url}')
        log(f'opened PR #{self.pr}: {url}')
        watch_checks(self.pr)
        run(['gh', 'pr', 'merge', self.pr, '--squash', '--match-head-commit', head], timeout=300)
        state = run(['gh', 'pr', 'view', self.pr, '--json', 'state', '--jq', '.state']).strip()
        if state != 'MERGED':
            raise RefreshError(f'PR #{self.pr} is {state or "unknown"} after merge request')
        self.merged = True
        log(f'merged PR #{self.pr} at head {head[:7]}')
        delete_remote_branch(self.branch)

    def cleanup(self):
        """Leave no half-state: close an unmerged PR, drop the remote branch, worktree and local branch."""
        problems = []
        steps = []
        if self.pr and not self.merged:
            steps.append(['gh', 'pr', 'close', self.pr, '--comment', 'Automated refresh failed; closed by refresh_statistics.py.'])
        if self.pushed and not self.merged:
            steps.append(['git', 'push', 'origin', '--delete', self.branch])
        if self.worktree.exists():
            steps.append(['git', 'worktree', 'remove', '--force', self.worktree])
        steps.append(['git', 'branch', '-D', self.branch])
        for step in steps:
            try:
                if step[:2] == ['git', 'push']:
                    delete_remote_branch(self.branch)
                else:
                    run(step, timeout=300)
            except (RefreshError, subprocess.SubprocessError) as error:
                if step[1] == 'branch' and 'not found' in str(error):
                    continue
                problems.append(str(error))
        run(['git', 'worktree', 'prune'], check=False)
        return problems

    def execute(self):
        log('fetching origin')
        run(['git', 'fetch', 'origin'], timeout=300)
        sha = run(['git', 'rev-parse', 'origin/main']).strip()
        recorded = recorded_revision(run(['git', 'show', f'origin/main:{SNAPSHOT}']))
        if recorded == sha:
            log(f'snapshot already records origin/main {sha}; nothing to do')
            return 0
        if not other_changes(recorded, sha):
            log(f'no changes besides statistics refreshes between {recorded[:7]} and origin/main {sha[:7]}; nothing to do')
            return 0
        log(f'snapshot records {recorded[:7]}; origin/main is {sha[:7]}')
        try:
            if self.collect(sha):
                head = self.commit(sha)
                if self.dry_run:
                    log(f'dry run: would push {self.branch}, open "{title_for(sha)}" and merge {head[:7]}')
                else:
                    self.publish(sha, head)
        finally:
            problems = self.cleanup()
        if problems:
            raise RefreshError('cleanup incomplete: ' + '; '.join(problems))
        log(f'removed worktree and branch {self.branch}')
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='Collect and commit in the worktree; never push, open or merge')
    args = parser.parse_args(argv)
    lock_dir = ROOT / 'workdir'
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / 'stats-refresh.lock'
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f'another refresh holds {lock}; confirm it stopped before removing the lock', file=sys.stderr)
        return 2
    try:
        os.write(fd, f'{os.getpid()}\n'.encode())
        os.close(fd)
        return Refresh(dry_run=args.dry_run).execute()
    except (RefreshError, subprocess.SubprocessError, OSError) as error:
        print(f'statistics refresh failed: {error}', file=sys.stderr)
        return 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    sys.exit(main())
