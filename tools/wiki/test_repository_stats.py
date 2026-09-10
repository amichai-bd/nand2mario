"""Offline collector/report contracts; never collect live project statistics in CI."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.wiki import repository_stats as stats
from tools.wiki.statistics_report import render


def empty_source():
    return dict(revision='a' * 40, totals=stats.sums([]), files=[], by_discipline={}, by_extension={},
                by_top_directory={}, skipped_nonregular=[], history=dict(reachable_commits=0,
                first_parent_commits=0, first_commit=None, last_commit=None, daily=[]))


def pr(number=1, state='MERGED', base='main', area='area:rtl'):
    return dict(number=number, state=state, createdAt='2026-01-01T00:00:00Z',
                closedAt='2026-01-01T00:10:00Z' if state != 'OPEN' else None,
                mergedAt='2026-01-01T00:10:00Z' if state == 'MERGED' else None,
                baseRefName=base, labels={'nodes': [{'name': area}], 'pageInfo': {'hasNextPage': False}},
                closingIssuesReferences={'nodes': [{'number': 1}], 'pageInfo': {'hasNextPage': False}})


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.scratch = Path(__file__).resolve().parents[2] / 'workdir/wiki/tests'
        self.scratch.mkdir(parents=True, exist_ok=True)

    def temporary(self, **kwargs):
        return tempfile.TemporaryDirectory(dir=self.scratch, **kwargs)

    def test_empty_data_and_safe_offline_html(self):
        github = stats.summarize_github([], [], '2026-01-02T00:00:00Z')
        self.assertEqual(github['pr_created_to_merge'], {'count': 0})
        self.assertIsNone(github['first_pr_merge'])
        html = render(empty_source(), github)
        self.assertIn('No samples', html)
        self.assertIn('No history available', html)
        self.assertNotIn('<script', html)
        self.assertNotIn('<link', html)
        self.assertIn('GitHub metadata was not collected', render(empty_source()))

    def test_elapsed_and_branch_scope(self):
        prs = [pr(), pr(2, base='experiment'), pr(3, 'OPEN'), pr(4, 'CLOSED')]
        github = stats.summarize_github([], prs, '2026-01-02T00:00:00Z')
        self.assertEqual(github['merged_prs'], 2)
        self.assertEqual(github['merged_prs_to_main'], 1)
        self.assertEqual(github['pr_created_to_merge']['median_seconds'], 600)
        self.assertEqual(github['open_pr_age']['median_seconds'], 86400)
        self.assertEqual(github['by_area']['area:rtl']['merged'], 2)
        self.assertEqual(github['prs_by_state']['CLOSED'], 1)
        self.assertEqual(stats.duration_stats([0, 10, 20, 30])['p75_seconds'], 22.5)

    def test_untrusted_labels_and_paths_are_escaped(self):
        source = empty_source()
        source['by_extension']['<script>alert(1)</script>'] = stats.sums([])
        github = stats.summarize_github([], [pr(area='area:<img src=x onerror="alert(1)">')], '2026-01-02T00:00:00Z')
        html = render(source, github)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img src=x', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('&lt;img src=x', html)

    def test_truncated_or_failed_graphql_rejected(self):
        item = pr()
        item['closingIssuesReferences']['pageInfo']['hasNextPage'] = True
        with self.assertRaisesRegex(ValueError, 'truncated'):
            stats.summarize_github([], [item], '2026-01-02T00:00:00Z')
        with patch.object(stats, 'command', return_value=b'{"errors":[{"message":"denied"}]}'):
            with self.assertRaisesRegex(ValueError, 'GraphQL errors'):
                stats.graphql('owner/repo', 'issues', 'number')
        page = {'data': {'repository': {'issues': {'nodes': [], 'pageInfo': {'hasNextPage': True, 'endCursor': 'same'}}}}}
        with patch.object(stats, 'command', return_value=json.dumps(page).encode()):
            with self.assertRaisesRegex(ValueError, 'did not advance'):
                stats.graphql('owner/repo', 'issues', 'number')

    def test_collection_failure_preserves_previous_report(self):
        with self.temporary() as directory:
            path = Path(directory) / 'report.html'
            path.write_text('previous', encoding='utf-8')
            with patch.object(stats, 'collect_source', return_value=empty_source()), patch.object(stats, 'collect_github', side_effect=ValueError('offline')), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    stats.main(['--output', str(Path(directory) / 'json'), '--html', str(path), '--github'])
            self.assertEqual(result.exception.code, 1)
            self.assertEqual(path.read_text(), 'previous')
            self.assertFalse((Path(directory) / 'json').exists())

    def test_atomic_replace_failure_preserves_previous_file(self):
        with self.temporary() as directory:
            path = Path(directory) / 'report.html'
            path.write_text('previous')
            with patch.object(stats.os, 'replace', side_effect=OSError('locked')):
                with self.assertRaises(OSError):
                    stats.atomic_write(path, 'new')
            self.assertEqual(path.read_text(), 'previous')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_real_git_snapshot_ignores_working_changes(self):
        previous = Path.cwd()
        with self.temporary(prefix='statistics fixture ') as directory:
            try:
                os.chdir(directory)
                def git(*args):
                    return subprocess.check_output(['git', *args], stderr=subprocess.PIPE)
                git('init', '-q')
                git('config', 'user.email', 'fixture@example.invalid')
                git('config', 'user.name', 'Fixture')
                git('commit', '--allow-empty', '-qm', 'empty')
                self.assertEqual(stats.collect_source('HEAD')['totals']['files'], 0)
                path = Path('src/rtl/example.sv')
                path.parent.mkdir(parents=True)
                path.write_bytes(b'\xef\xbb\xbfmodule example;\r\n\r\nendmodule')
                Path('pixels.dat').write_bytes(b'\0binary')
                git('add', '.')
                git('commit', '-qm', 'fixture')
                path.write_text('uncommitted')
                source = stats.collect_source('HEAD')
                self.assertEqual(source['totals']['files'], 2)
                self.assertEqual(source['totals']['lines'], 3)
                self.assertEqual(source['totals']['nonblank'], 2)
                self.assertEqual(source['totals']['binary_files'], 1)
                self.assertEqual(source['by_discipline']['RTL HDL']['lines'], 3)
                self.assertEqual(source['history']['reachable_commits'], 2)
            finally:
                os.chdir(previous)

    def test_shallow_history_is_not_reported_as_complete(self):
        with patch.object(stats, 'git', side_effect=[b'a' * 40, b'true\n']):
            with self.assertRaisesRegex(ValueError, 'Complete Git history'):
                stats.collect_source('HEAD')

    def test_area_fallback_uses_linked_issue_labels_without_double_counting(self):
        item = pr()
        item['labels']['nodes'] = []
        item['closingIssuesReferences']['nodes'] = [{'number': 1}, {'number': 2}]
        issues = [dict(number=value, state='OPEN', createdAt='2026-01-01T00:00:00Z', closedAt=None,
                       labels={'nodes': [{'name': 'area:rtl'}], 'pageInfo': {'hasNextPage': False}})
                  for value in (1, 2)]
        github = stats.summarize_github(issues, [item], '2026-01-02T00:00:00Z')
        self.assertEqual(github['by_area']['area:rtl']['merged'], 1)
        item['labels']['nodes'] = [{'name': 'area:tools'}]
        github = stats.summarize_github(issues, [item], '2026-01-02T00:00:00Z')
        self.assertNotIn('area:rtl', github['by_area'])
        item['labels']['nodes'] = []
        item['closingIssuesReferences']['nodes'] = [{'number': 1, 'repository': {'nameWithOwner': 'other/repo'}}]
        github = stats.summarize_github(issues, [item], '2026-01-02T00:00:00Z', repo='owner/repo')
        self.assertEqual(github['by_area']['unlabeled']['merged'], 1)
        self.assertEqual(github['merged_prs_with_closing_issue_reference'], 0)


if __name__ == '__main__':
    unittest.main()
