"""Collect Git/GitHub statistics and manually publish a standalone HTML snapshot."""

import argparse
import collections
import datetime
import json
import os
from pathlib import Path, PurePosixPath
import statistics
import subprocess
import tempfile


def command(*args, input=None):
    return subprocess.run(args, input=input, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=True, timeout=120).stdout


def git(*args):
    return command('git', *args)


def classify(path):
    ext = PurePosixPath(path).suffix.lower()
    if path.startswith('src/rtl/'):
        return 'RTL HDL' if ext in ('.sv', '.svh', '.v') else 'RTL documentation and provenance'
    if path.startswith('src/fpga/'):
        return {'.sv': 'FPGA integration and proof HDL', '.sdc': 'FPGA timing constraints'}.get(ext, 'FPGA metadata and documentation')
    if path.startswith('src/dv/cpu/singlestep/') and ext in ('.svh', '.json'):
        return 'DV generated vector data and manifest'
    if path.startswith('src/dv/'):
        return 'RTL verification code and program fixtures' if ext in ('.sv', '.svh', '.py', '.c', '.asm', '.do') else 'DV configuration, data and documentation'
    if path.startswith('src/sw/'):
        if ext == '.json' and (path.startswith('src/sw/springtrail/assets/') or path.endswith(('/tiles.json', '/shades.json'))):
            return 'Game pixel assets and pose data'
        return 'Software assembly (including conformance fixtures)' if ext in ('.asm', '.rgbasm', '.inc') else 'Software metadata and documentation'
    if path.startswith('src/'):
        return 'Other source and FPGA integration'
    if path.startswith('tools/'):
        if '/tests/' in path or PurePosixPath(path).name.startswith('test_') or path.endswith('/browser_tests.py'):
            return 'Host tooling tests and fixtures'
        return 'Host tooling implementation' if ext in ('.py', '.js', '.css', '.html') else 'Host tooling data and documentation'
    if path.startswith('wiki/'):
        return 'Wiki generated SVG art' if ext == '.svg' else 'Wiki documentation and presentations'
    if path.startswith('.agents/') or path == 'AGENTS.md':
        return 'Agent skills and instructions'
    return 'Repository configuration and other documentation'


def measure(revision):
    specs, skipped, records = [], [], []
    for entry in git('ls-tree', '-r', '-z', revision).split(b'\0'):
        if not entry:
            continue
        header, path = entry.split(b'\t', 1)
        mode, kind, oid = header.decode().split()
        if kind != 'blob' or mode not in ('100644', '100755'):
            skipped.append(path.decode())
        else:
            specs.append((path.decode(), oid))
    if not specs:
        return records, skipped
    data = command('git', 'cat-file', '--batch', input=('\n'.join(oid for _, oid in specs) + '\n').encode())
    offset = 0
    for path, _ in specs:
        end = data.index(b'\n', offset)
        size = int(data[offset:end].split()[-1])
        blob = data[end + 1:end + 1 + size]
        offset = end + size + 2
        binary = b'\0' in blob
        try:
            decoded = blob.decode('utf-8-sig')
        except UnicodeDecodeError:
            binary, decoded = True, ''
        lines = [] if binary else decoded.splitlines()
        records.append(dict(path=path, bytes=size, binary=binary, lines=len(lines),
                            nonblank=sum(bool(line.strip()) for line in lines),
                            extension=PurePosixPath(path).suffix.lower() or '(none)',
                            top_directory=path.split('/')[0] if '/' in path else '(root)',
                            discipline=classify(path)))
    return records, skipped


def sums(records):
    return dict(files=len(records), text_files=sum(not row['binary'] for row in records),
                binary_files=sum(row['binary'] for row in records),
                **{key: sum(row[key] for row in records) for key in ('bytes', 'lines', 'nonblank')})


def grouped(records, field):
    groups = collections.defaultdict(list)
    for row in records:
        groups[row[field]].append(row)
    return {key: sums(rows) for key, rows in sorted(groups.items())}


def collect_source(revision):
    revision = git('rev-parse', '--verify', revision + '^{commit}').decode().strip()
    if git('rev-parse', '--is-shallow-repository').strip() == b'true':
        raise ValueError('Complete Git history is required; fetch the full history first.')
    records, skipped = measure(revision)
    logs = [dict(zip(('sha', 'committed_at'), line.split('\t'))) for line in
            git('log', '--first-parent', '--format=%H%x09%cI', revision).decode().splitlines()]
    daily, day_shas = collections.Counter(), {}
    for entry in reversed(logs):
        day = datetime.datetime.fromisoformat(entry['committed_at']).astimezone(datetime.timezone.utc).date().isoformat()
        daily[day] += 1
        day_shas[day] = entry['sha']
    growth = []
    for day, sha in sorted(day_shas.items()):
        rows, _ = measure(sha)
        growth.append(dict(date=day, sha=sha, commits=daily[day], **sums(rows)))
    return dict(revision=revision, totals=sums(records), files=records,
                by_top_directory=grouped(records, 'top_directory'),
                by_discipline=grouped(records, 'discipline'), by_extension=grouped(records, 'extension'),
                skipped_nonregular=skipped, history=dict(reachable_commits=int(git('rev-list', '--count', revision)),
                first_parent_commits=len(logs), first_commit=logs[-1] if logs else None,
                last_commit=logs[0] if logs else None, daily=growth))


def seconds(start, end):
    return (datetime.datetime.fromisoformat(end.replace('Z', '+00:00')) -
            datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))).total_seconds()


def duration_stats(values):
    values = sorted(values)
    if not values:
        return {'count': 0}
    def percentile(q):
        index = (len(values) - 1) * q
        low, high = int(index), min(int(index) + 1, len(values) - 1)
        return values[low] + (values[high] - values[low]) * (index - low)
    return dict(count=len(values), median_seconds=statistics.median(values), p75_seconds=percentile(.75),
                p90_seconds=percentile(.90), min_seconds=min(values), max_seconds=max(values),
                at_most_1h=sum(value <= 3600 for value in values))


def graphql(repo, connection, fields):
    owner, name = repo.split('/')
    cursor, nodes = None, []
    seen = set()
    while True:
        args = 'first:100' + (',after:' + json.dumps(cursor) if cursor else '')
        query = '{repository(owner:' + json.dumps(owner) + ',name:' + json.dumps(name) + '){' + connection + '(' + args + '){nodes{' + fields + '}pageInfo{hasNextPage endCursor}}}}'
        response = json.loads(command('gh', 'api', 'graphql', '-f', 'query=' + query))
        if response.get('errors'):
            raise ValueError('GitHub returned GraphQL errors; no report published.')
        page = response['data']['repository'][connection]
        nodes.extend(page['nodes'])
        if not page['pageInfo']['hasNextPage']:
            return nodes
        cursor = page['pageInfo']['endCursor']
        if not cursor or cursor in seen:
            raise ValueError('GitHub pagination did not advance.')
        seen.add(cursor)


def summarize_github(issues, prs, observed, excluded=(), repo=None):
    for item in [*issues, *prs]:
        for key in ('labels', 'closingIssuesReferences'):
            if item.get(key, {}).get('pageInfo', {}).get('hasNextPage'):
                raise ValueError('GitHub nested metadata is truncated; no report published.')
    merged = [item for item in prs if item['mergedAt']]
    closed = [item for item in issues if item['state'] == 'CLOSED' and item['closedAt'] and item['number'] not in excluded]
    days = collections.defaultdict(collections.Counter)
    for item in issues:
        days[item['createdAt'][:10]]['issues_created'] += 1
        if item['state'] == 'CLOSED' and item['closedAt']:
            days[item['closedAt'][:10]]['currently_closed_issues_closed'] += 1
    for item in prs:
        days[item['createdAt'][:10]]['prs_created'] += 1
        if item['mergedAt']:
            days[item['mergedAt'][:10]]['prs_merged'] += 1
    areas = collections.defaultdict(list)
    def local_refs(item):
        return [ref for ref in item['closingIssuesReferences']['nodes']
                if repo is None or ref.get('repository', {}).get('nameWithOwner') == repo]
    issue_areas = {item['number']: [label['name'] for label in item.get('labels', {}).get('nodes', [])
                                   if label['name'].startswith('area:')] for item in issues}
    for item in prs:
        labels = [label['name'] for label in item.get('labels', {}).get('nodes', []) if label['name'].startswith('area:')]
        if not labels:
            labels = sorted({label for ref in local_refs(item)
                             for label in issue_areas.get(ref['number'], [])})
        for label in labels or ['unlabeled']:
            areas[label].append(item)
    by_area = {area: dict(total=len(items), open=sum(item['state'] == 'OPEN' for item in items),
                         merged=sum(bool(item['mergedAt']) for item in items),
                         elapsed=duration_stats([seconds(item['createdAt'], item['mergedAt']) for item in items if item['mergedAt']]))
               for area, items in sorted(areas.items())}
    linked = [item for item in merged if local_refs(item)]
    merge_dates = [item['mergedAt'] for item in merged]
    return dict(observed_at=observed, issues_total=len(issues),
                issues_by_state=dict(collections.Counter(item['state'] for item in issues)),
                prs_total=len(prs), prs_by_state=dict(collections.Counter(item['state'] for item in prs)),
                merged_prs=len(merged), merged_prs_to_main=sum(item['baseRefName'] == 'main' for item in merged),
                first_pr_merge=min(merge_dates, default=None), last_pr_merge=max(merge_dates, default=None),
                pr_created_to_merge=duration_stats([seconds(item['createdAt'], item['mergedAt']) for item in merged]),
                open_pr_age=duration_stats([seconds(item['createdAt'], observed) for item in prs if item['state'] == 'OPEN']),
                closed_issue_created_to_close=duration_stats([seconds(item['createdAt'], item['closedAt']) for item in closed]),
                excluded_closed_issue_numbers=list(excluded), by_area=by_area,
                merged_prs_with_closing_issue_reference=len(linked),
                distinct_closing_issue_references=len({ref['number'] for item in linked for ref in local_refs(item)}),
                closing_reference_truncation=False, daily=[dict(date=day, **values) for day, values in sorted(days.items())],
                issues=issues, prs=prs)


def collect_github(repo=None, excluded=()):
    repo = repo or json.loads(command('gh', 'repo', 'view', '--json', 'nameWithOwner'))['nameWithOwner']
    labels = 'labels(first:100){nodes{name}pageInfo{hasNextPage}}'
    issues = graphql(repo, 'issues', 'number state createdAt closedAt ' + labels)
    prs = graphql(repo, 'pullRequests', 'number state createdAt mergedAt closedAt baseRefName ' + labels + ' closingIssuesReferences(first:100){nodes{number repository{nameWithOwner}}pageInfo{hasNextPage}}')
    return summarize_github(issues, prs, datetime.datetime.now(datetime.timezone.utc).isoformat(), excluded, repo)


def atomic_write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='HEAD', help='Resolve a fixed Git commit; requires full history')
    parser.add_argument('--output', required=True, type=Path, help='JSON artifact directory under workdir')
    parser.add_argument('--html', type=Path, help='Explicit standalone HTML destination, e.g. wiki/statistics.html')
    parser.add_argument('--github', action='store_true', help='Read live GitHub metadata using authenticated gh')
    parser.add_argument('--repo', help='GitHub owner/name, otherwise discovered by gh')
    parser.add_argument('--exclude-closed-issue', type=int, action='append', default=[])
    args = parser.parse_args(argv)
    try:
        source = collect_source(args.revision)
        github = collect_github(args.repo, args.exclude_closed_issue) if args.github else None
        if args.html:
            try:
                from .statistics_report import render
            except ImportError:
                from statistics_report import render
            report = render(source, github)
        # Collection and rendering finish before the previous report is touched.
        atomic_write(args.output / 'repository-stats.json', json.dumps(source, indent=2) + '\n')
        if github is not None:
            atomic_write(args.output / 'github-stats.json', json.dumps(github, indent=2) + '\n')
        if args.html:
            atomic_write(args.html, report)
        print(json.dumps(dict(revision=source['revision'], totals=source['totals'], html=str(args.html) if args.html else None)))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(1, f'Statistics generation failed; previous HTML preserved: {error}\n')


if __name__ == '__main__':
    main()
