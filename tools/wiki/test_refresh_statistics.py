"""Unattended refresh contracts with git/gh stubbed; never pushes, opens or merges."""

import contextlib
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.wiki import refresh_statistics as refresh

OLD = 'f' * 40
NEW = '0123abc' + 'e' * 33
HTML = f'<p class="muted">Source <code>{OLD}</code><br>GitHub observed: x</p>'
BRANCH = 'stats-refresh-20260911T120000Z'


class FakeCommands:
    """Answer the script's git/gh calls from a scripted repository state."""

    def __init__(self, root, main=NEW, recorded=OLD, status=' M wiki/statistics.html\n',
                 diff='wiki/statistics.html\n', fail=None, merged='MERGED'):
        self.root, self.main, self.recorded = root, main, recorded
        self.status, self.diff, self.fail, self.merged = status, diff, fail, merged
        self.calls = []

    def __call__(self, args, cwd=None, timeout=120, check=True):
        args = [str(a) for a in args]
        key = ' '.join(args[:3]) if args[0] == 'gh' else ' '.join(args[:2])
        self.calls.append((key, args, Path(cwd) if cwd else None))
        if self.fail and key == self.fail:
            raise refresh.RefreshError(f'{key} exploded')
        if key == 'git rev-parse':
            return self.main + '\n'
        if key == 'git show':
            return HTML.replace(OLD, self.recorded)
        if key == 'git worktree' and args[2] == 'add':
            Path(args[5]).mkdir(parents=True)
            return ''
        if key == 'git worktree' and args[2] == 'remove':
            shutil.rmtree(args[4])
            return ''
        if key == 'git status':
            return self.status
        if key == 'git diff':
            return self.diff
        if key == 'gh pr create':
            self.body = Path(args[args.index('--body-file') + 1]).read_text(encoding='utf-8')
            return 'https://github.com/example/repo/pull/77\n'
        if key == 'gh pr view':
            return self.merged + '\n'
        if key == 'git branch' and not any(k == 'git worktree' for k, _, _ in self.calls):
            raise refresh.RefreshError("git branch -D failed (1): error: branch 'x' not found")
        return ''

    def keys(self):
        return [key for key, _, _ in self.calls]


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(__file__).resolve().parents[2] / 'workdir/wiki/tests'
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.scratch, prefix='refresh ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def execute(self, fake, argv=()):
        out = io.StringIO()
        with patch.object(refresh, 'ROOT', self.root), patch.object(refresh, 'run', fake), \
                patch.object(refresh, 'watch_checks', lambda number: fake.calls.append(('watch', [number], None))), \
                patch.object(refresh, 'timestamp', lambda now=None: '20260911T120000Z'), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = refresh.main(list(argv))
        return code, out.getvalue()

    def test_no_change_exits_without_a_worktree(self):
        fake = FakeCommands(self.root, recorded=NEW)
        code, out = self.execute(fake)
        self.assertEqual(0, code)
        self.assertEqual(['git fetch', 'git rev-parse', 'git show'], fake.keys())
        self.assertIn(f'already records origin/main {NEW}', out)
        self.assertFalse((self.root / 'worktrees').exists())
        self.assertFalse((self.root / 'workdir/stats-refresh.lock').exists())

    def test_collector_without_diff_cleans_up_and_exits_zero(self):
        fake = FakeCommands(self.root, status='')
        code, out = self.execute(fake)
        self.assertEqual(0, code)
        self.assertNotIn('git commit', fake.keys())
        self.assertNotIn('git push', fake.keys())
        self.assertEqual(['git worktree', 'git branch', 'git worktree'], fake.keys()[-3:])
        self.assertFalse((self.root / 'worktrees' / BRANCH).exists())
        self.assertIn('nothing to publish', out)

    def test_full_run_forms_and_order(self):
        fake = FakeCommands(self.root)
        code, out = self.execute(fake)
        self.assertEqual(0, code, out)
        keys = fake.keys()
        for earlier, later in (('git commit', 'git push'), ('git push', 'gh pr create'), ('gh pr create', 'watch'),
                               ('watch', 'gh pr merge'), ('gh pr merge', 'gh pr view'), ('gh pr view', 'git branch')):
            self.assertLess(keys.index(earlier), keys.index(later))
        add = next(args for key, args, _ in fake.calls if key == 'git worktree')
        self.assertEqual(['git', 'worktree', 'add', '-b', BRANCH, str(self.root / 'worktrees' / BRANCH), 'origin/main'], add)
        collector = next((args, cwd) for key, args, cwd in fake.calls if key.endswith('repository_stats.py'))
        self.assertEqual(collector[0][1:], refresh.COLLECTOR)
        self.assertEqual(collector[1], self.root / 'worktrees' / BRANCH)
        create = next(args for key, args, _ in fake.calls if key == 'gh pr create')
        self.assertIn('stats: refresh snapshot to 0123abc', create)
        self.assertNotIn('--draft', create)
        self.assertEqual('Refresh the repository statistics snapshot to `%s`.\n\nRefs #392\n' % NEW, fake.body)
        merge = next(args for key, args, _ in fake.calls if key == 'gh pr merge')
        self.assertEqual(['gh', 'pr', 'merge', '77', '--squash', '--match-head-commit', NEW], merge)
        self.assertEqual(['git', 'push', 'origin', '--delete', BRANCH],
                         [args for key, args, _ in fake.calls if key == 'git push'][-1])
        self.assertNotIn('gh pr close', keys)
        self.assertFalse((self.root / 'worktrees' / BRANCH).exists())

    def test_unexpected_changed_files_fail_before_commit(self):
        for status in (' M wiki/statistics.html\n?? wiki/extra.md\n', ' M wiki/index.md\n'):
            with self.subTest(status=status):
                fake = FakeCommands(self.root, status=status)
                code, out = self.execute(fake)
                self.assertEqual(1, code)
                self.assertIn('unexpected paths', out)
                self.assertNotIn('git commit', fake.keys())
                self.assertFalse((self.root / 'worktrees' / BRANCH).exists())
        fake = FakeCommands(self.root, diff='wiki/statistics.html\ntools/x.py\n')
        code, out = self.execute(fake)
        self.assertEqual(1, code)
        self.assertIn('unexpected files', out)
        self.assertNotIn('git push', fake.keys())

    def test_failure_after_pr_closes_it_and_removes_everything(self):
        fake = FakeCommands(self.root, fail='gh pr merge')
        code, out = self.execute(fake)
        self.assertEqual(1, code)
        self.assertIn('gh pr merge exploded', out)
        keys = fake.keys()
        self.assertIn('gh pr close', keys)
        self.assertEqual(['git', 'push', 'origin', '--delete', BRANCH],
                         [args for key, args, _ in fake.calls if key == 'git push'][-1])
        self.assertLess(keys.index('gh pr close'), keys.index('git branch'))
        self.assertFalse((self.root / 'worktrees' / BRANCH).exists())
        self.assertFalse((self.root / 'workdir/stats-refresh.lock').exists())

    def test_unmerged_state_after_merge_request_is_a_failure(self):
        fake = FakeCommands(self.root, merged='OPEN')
        code, out = self.execute(fake)
        self.assertEqual(1, code)
        self.assertIn('is OPEN after merge request', out)
        self.assertIn('gh pr close', fake.keys())

    def test_failure_before_push_touches_no_remote(self):
        fake = FakeCommands(self.root, fail='git commit')
        code, out = self.execute(fake)
        self.assertEqual(1, code)
        self.assertNotIn('git push', fake.keys())
        self.assertNotIn('gh pr close', fake.keys())
        self.assertFalse((self.root / 'worktrees' / BRANCH).exists())

    def test_dry_run_commits_locally_and_never_publishes(self):
        fake = FakeCommands(self.root)
        code, out = self.execute(fake, ['--dry-run'])
        self.assertEqual(0, code)
        keys = fake.keys()
        self.assertIn('git commit', keys)
        for forbidden in ('git push', 'gh pr create', 'gh pr merge', 'gh pr close', 'watch'):
            self.assertNotIn(forbidden, keys)
        self.assertIn('dry run: would push', out)
        self.assertFalse((self.root / 'worktrees' / BRANCH).exists())

    def test_lock_refuses_a_second_run(self):
        lock = self.root / 'workdir/stats-refresh.lock'
        lock.parent.mkdir(parents=True)
        lock.write_text('1\n')
        fake = FakeCommands(self.root)
        code, out = self.execute(fake)
        self.assertEqual(2, code)
        self.assertEqual([], fake.keys())
        self.assertTrue(lock.exists())

    def test_snapshot_without_revision_fails(self):
        with self.assertRaisesRegex(refresh.RefreshError, 'records no source revision'):
            refresh.recorded_revision('<p>nothing</p>')


if __name__ == '__main__':
    unittest.main()
