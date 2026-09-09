"""Read-only fixed-revision repository and live GitHub statistics. Python stdlib + git/gh."""
import argparse, collections, datetime, json, pathlib, statistics, subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision', default='HEAD', help='Git snapshot; resolved to an immutable commit')
parser.add_argument('--output', required=True, type=pathlib.Path, help='Artifact directory, normally under workdir')
parser.add_argument('--github', action='store_true', help='Also read live GitHub metadata using authenticated gh')
parser.add_argument('--repo', help='GitHub owner/name; otherwise gh resolves current repository')
parser.add_argument('--exclude-closed-issue', type=int, action='append', default=[], help='Exclude this issue from issue lead-time summary; repeatable')
args = parser.parse_args()
OUT = args.output
OUT.mkdir(parents=True, exist_ok=True)
def command(*args):
    return subprocess.check_output(args)
def git(*args):
    return command('git', *args)
REV = git('rev-parse', '--verify', args.revision+'^{commit}').decode().strip()
def classify(p):
    ext=pathlib.PurePosixPath(p).suffix.lower()
    if p.startswith('src/rtl/') and ext in ('.sv','.svh','.v'): return 'RTL HDL'
    if p.startswith('src/rtl/'): return 'RTL documentation and provenance'
    if p.startswith('src/fpga/') and ext=='.sv': return 'FPGA integration and proof HDL'
    if p.startswith('src/fpga/') and ext=='.sdc': return 'FPGA timing constraints'
    if p.startswith('src/fpga/'): return 'FPGA metadata and documentation'
    if p.startswith('src/dv/cpu/singlestep/') and ext in ('.svh','.json'): return 'DV generated vector data and manifest'
    if p.startswith('src/dv/') and ext in ('.sv','.svh','.py','.c','.asm','.do'): return 'RTL verification code and program fixtures'
    if p.startswith('src/dv/'): return 'DV configuration, data and documentation'
    if p.startswith('src/sw/') and ext=='.json' and (p.startswith('src/sw/springtrail/assets/') or p.endswith(('/tiles.json','/shades.json'))): return 'Game pixel assets and pose data'
    if p.startswith('src/sw/') and ext in ('.asm','.rgbasm','.inc'): return 'Software assembly (including conformance fixtures)'
    if p.startswith('src/sw/'): return 'Software metadata and documentation'
    if p.startswith('src/'): return 'Other source and FPGA integration'
    if p.startswith('tools/') and ('/tests/' in p or pathlib.PurePosixPath(p).name.startswith('test_') or p.endswith('/browser_tests.py')): return 'Host tooling tests and fixtures'
    if p.startswith('tools/') and ext in ('.py','.js','.css','.html'): return 'Host tooling implementation'
    if p.startswith('tools/'): return 'Host tooling data and documentation'
    if p.startswith('wiki/') and ext=='.svg': return 'Wiki generated SVG art'
    if p.startswith('wiki/'): return 'Wiki documentation and presentations'
    if p.startswith('.agents/') or p=='AGENTS.md': return 'Agent skills and instructions'
    return 'Repository configuration and other documentation'
def measure(rev):
    entries=git('ls-tree','-r','-z',rev).split(b'\0')
    records=[]
    specs=[]
    skipped=[]
    for entry in entries:
        if not entry: continue
        head,path=entry.split(b'\t',1)
        mode,kind,oid=head.decode().split()
        if kind!='blob' or mode not in ('100644','100755'):
            skipped.append(path.decode());continue
        specs.append((path.decode(),oid))
    data=subprocess.run(['git','cat-file','--batch'],input=('\n'.join(oid for _,oid in specs)+'\n').encode(),stdout=subprocess.PIPE,check=True).stdout
    offset=0
    for path,oid in specs:
        end=data.index(b'\n',offset)
        size=int(data[offset:end].split()[-1]); start=end+1
        blob=data[start:start+size]; offset=start+size+1
        binary=b'\0' in blob
        try: decoded=blob.decode('utf-8-sig')
        except UnicodeDecodeError: binary=True;decoded=''
        lines=decoded.splitlines() if not binary else []
        records.append(dict(path=path,bytes=size,binary=binary,lines=len(lines),nonblank=sum(bool(s.strip()) for s in lines),extension=pathlib.PurePosixPath(path).suffix.lower() or '(none)',top_directory=path.split('/')[0] if '/' in path else '(root)',discipline=classify(path)))
    return records,skipped
def sums(records):
    return dict(files=len(records),text_files=sum(not x['binary'] for x in records),binary_files=sum(x['binary'] for x in records),bytes=sum(x['bytes'] for x in records),lines=sum(x['lines'] for x in records),nonblank=sum(x['nonblank'] for x in records))
def grouped(records,field):
    return {key:sums([x for x in records if x[field]==key]) for key in sorted(set(x[field] for x in records))}
records,skipped=measure(REV)
logs=[dict(zip(('sha','committed_at','subject'),line.split('\t',2))) for line in git('log','--first-parent','--format=%H%x09%cI%x09%s',REV).decode().splitlines()]
daily=collections.Counter()
day_shas={}
for entry in reversed(logs):
    day=datetime.datetime.fromisoformat(entry['committed_at']).astimezone(datetime.timezone.utc).date().isoformat()
    daily[day]+=1;day_shas[day]=entry['sha']
growth=[]
for day,sha in sorted(day_shas.items()):
    rows,_=measure(sha)
    growth.append(dict(date=day,sha=sha,commits=daily[day],**sums(rows)))
result=dict(revision=REV,totals=sums(records),by_top_directory=grouped(records,'top_directory'),by_discipline=grouped(records,'discipline'),by_extension=grouped(records,'extension'),skipped_nonregular=skipped,history=dict(reachable_commits=int(git('rev-list','--count',REV)),first_parent_commits=len(logs),first_commit=logs[-1],last_commit=logs[0],daily=growth),files=records)
OUT.joinpath('repository-stats.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ('files','history')},indent=2),flush=True)
if not args.github: raise SystemExit(0)
REPO = args.repo or json.loads(command('gh','repo','view','--json','nameWithOwner'))['nameWithOwner']
owner, name = REPO.split('/')
def graphql(connection,fields):
    cursor=None;nodes=[]
    while True:
        args='first:100'+(',after:'+json.dumps(cursor) if cursor else '')
        query='{repository(owner:'+json.dumps(owner)+',name:'+json.dumps(name)+'){'+connection+'('+args+'){nodes{'+fields+'}pageInfo{hasNextPage endCursor}}}}'
        page=json.loads(command('gh','api','graphql','-f','query='+query))['data']['repository'][connection]
        nodes.extend(page['nodes'])
        if not page['pageInfo']['hasNextPage']:return nodes
        cursor=page['pageInfo']['endCursor']
issues=graphql('issues','number title state createdAt closedAt url')
prs=graphql('pullRequests','number title state createdAt mergedAt closedAt url baseRefName closingIssuesReferences(first:100){nodes{number}pageInfo{hasNextPage}}')
observed=datetime.datetime.now(datetime.timezone.utc).isoformat()
merged=[p for p in prs if p['mergedAt']]
def seconds(a,b):return (datetime.datetime.fromisoformat(b.replace('Z','+00:00'))-datetime.datetime.fromisoformat(a.replace('Z','+00:00'))).total_seconds()
def duration_stats(values):
    values=sorted(values)
    def percentile(q):
        index=(len(values)-1)*q;lo=int(index);hi=min(lo+1,len(values)-1)
        return values[lo]+(values[hi]-values[lo])*(index-lo)
    return dict(count=len(values),median_seconds=statistics.median(values),p75_seconds=percentile(.75),p90_seconds=percentile(.90),min_seconds=min(values),max_seconds=max(values),at_most_1h=sum(v<=3600 for v in values)) if values else {}
closed=[i for i in issues if i['state']=='CLOSED' and i['closedAt'] and i['number'] not in args.exclude_closed_issue]
event_days=collections.defaultdict(collections.Counter)
for i in issues:
    event_days[i['createdAt'][:10]]['issues_created']+=1
    if i['state']=='CLOSED' and i['closedAt']:event_days[i['closedAt'][:10]]['currently_closed_issues_closed']+=1
for p in prs:
    event_days[p['createdAt'][:10]]['prs_created']+=1
    if p['mergedAt']:event_days[p['mergedAt'][:10]]['prs_merged']+=1
linked=[p for p in merged if p['closingIssuesReferences']['nodes']]
github=dict(observed_at=observed,issues_total=len(issues),issues_by_state=dict(collections.Counter(i['state'] for i in issues)),prs_total=len(prs),prs_by_state=dict(collections.Counter(p['state'] for p in prs)),merged_prs=len(merged),merged_prs_to_main=sum(p['baseRefName']=='main' for p in merged),first_pr_merge=min(p['mergedAt'] for p in merged),last_pr_merge=max(p['mergedAt'] for p in merged),pr_created_to_merge=duration_stats([seconds(p['createdAt'],p['mergedAt']) for p in merged]),closed_issue_created_to_close_excluding_7=duration_stats([seconds(i['createdAt'],i['closedAt']) for i in closed]),merged_prs_with_closing_issue_reference=len(linked),distinct_closing_issue_references=len(set(i['number'] for p in linked for i in p['closingIssuesReferences']['nodes'])),closing_reference_truncation=any(p['closingIssuesReferences']['pageInfo']['hasNextPage'] for p in prs),daily=[dict(date=d,**counts) for d,counts in sorted(event_days.items())],issues=issues,prs=prs)
github['closed_issue_created_to_close']=github.pop('closed_issue_created_to_close_excluding_7')
github['excluded_closed_issue_numbers']=args.exclude_closed_issue
OUT.joinpath('github-stats.json').write_text(json.dumps(github,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in github.items() if k not in ('issues','prs')},indent=2))
