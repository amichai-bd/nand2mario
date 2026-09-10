"""Pure, escaped HTML/SVG rendering for the manual repository snapshot."""

from html import escape
from pathlib import Path

CODE = ('RTL HDL', 'FPGA integration and proof HDL', 'RTL verification code and program fixtures',
        'Software assembly (including conformance fixtures)', 'Host tooling implementation', 'Host tooling tests and fixtures')
STYLE = '''
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--text);font-family:var(--font);line-height:1.55}
main{max-width:1240px;margin:auto;padding:40px 30px 70px}a{color:var(--accent)}:focus-visible{outline:3px solid var(--accent);outline-offset:4px}
header{border-bottom:1px solid var(--border);padding-bottom:24px}h1{font-size:clamp(2rem,5vw,3.7rem);line-height:1.05;margin:8px 0 20px;letter-spacing:-.04em}
h2{font-size:1.65rem;margin:0 0 12px}h3{font-size:1.05rem;margin:0 0 12px}.eyebrow{color:var(--accent);font-size:.8rem;letter-spacing:.15em;text-transform:uppercase}
p{max-width:85ch;margin:10px 0}.muted,small{color:var(--muted)}code{font-family:var(--mono);overflow-wrap:anywhere}nav{display:flex;flex-wrap:wrap;gap:12px 24px;margin:24px 0}
.project-nav{margin:20px 0 8px;padding:12px 16px;border:1px solid var(--border);border-radius:var(--radius);background:var(--panel)}.report-nav{margin-top:12px}.snapshot{max-width:90ch;border-left:3px solid var(--accent);padding:10px 16px;background:var(--panel);border-radius:0 var(--radius) var(--radius) 0}.snapshot strong{color:var(--text)}
section{margin-top:38px;scroll-margin-top:20px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:26px 0}
.card,.chart{border:1px solid var(--border);background:var(--panel);border-radius:var(--radius);padding:20px}.value{font-size:clamp(1.6rem,3vw,2.6rem);font-weight:700;letter-spacing:-.025em}.label{color:var(--muted);font-size:.9rem}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.chart{min-width:0}.scroll,.chart-scroll{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius);margin:18px 0}.chart-scroll{border:0;margin:12px 0 8px}
table{border-collapse:collapse;width:100%;font-size:.92rem}caption{text-align:left;padding:14px 16px;font-weight:600;background:var(--panel)}th,td{padding:10px 16px;border-bottom:1px solid var(--border);text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}th:first-child,td:first-child{text-align:left;white-space:normal;min-width:180px}thead{background:var(--panel);color:var(--muted)}tbody tr:last-child td{border-bottom:0}tbody tr:hover{background:var(--surface)}
svg{display:block;width:100%;height:auto;color:var(--text)}svg text{fill:currentColor;font-family:var(--font)}.note{border-left:3px solid var(--accent);padding:8px 16px;background:var(--panel);margin:20px 0}.legend{display:flex;flex-wrap:wrap;gap:10px 20px;margin-top:12px}.dot{display:inline-block;width:10px;height:10px;margin-right:7px;border-radius:50%}footer{margin-top:40px;border-top:1px solid var(--border);padding-top:18px;color:var(--muted);font-size:.9rem}
@media(max-width:700px){main{padding:24px 16px 40px}.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.grid{grid-template-columns:minmax(0,1fr)}th,td{padding:9px 12px}.card{padding:14px}.chart{padding:14px}.project-nav{gap:8px 16px}.chart-scroll{margin-inline:-6px}.chart-scroll svg{min-width:680px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{body{background:white;color:black}main{padding:0}.cards,.grid{break-inside:avoid}.scroll,.chart-scroll{overflow:visible}.chart-scroll svg{min-width:0}.project-nav{display:none}a{color:inherit}}
'''


def text(value):
    return escape(str(value), quote=True)


def number(value):
    return f'{value:,}'


def duration(value):
    if value is None:
        return 'No samples'
    value = round(value)
    if value < 60:
        return f'{value}s'
    if value < 3600:
        return f'{value // 60}m {value % 60:02}s'
    return f'{value // 3600}h {value % 3600 // 60:02}m'


def table(caption, columns, rows):
    header = ''.join(f'<th scope="col">{text(column)}</th>' for column in columns)
    body = ''.join('<tr>' + ''.join(f'<td>{text(cell)}</td>' for cell in row) + '</tr>' for row in rows)
    if not body:
        body = f'<tr><td colspan="{len(columns)}">No data in this snapshot.</td></tr>'
    return f'<div class="scroll" tabindex="0" role="region" aria-label="{text(caption)}"><table><caption>{text(caption)}</caption><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'


def size_table(caption, groups):
    return table(caption, ('Category', 'Files', 'Physical lines', 'Nonblank lines', 'Bytes'),
                 [(key, *(number(row[field]) for field in ('files', 'lines', 'nonblank', 'bytes'))) for key, row in groups.items()])


def card(value, label):
    return f'<div class="card"><div class="value">{text(value)}</div><div class="label">{text(label)}</div></div>'


def chart(title, rows, field, color):
    rows = rows[-14:]
    if not rows:
        return f'<div class="chart"><h3>{text(title)}</h3><p>No history available.</p></div>'
    maximum = max((row.get(field, 0) for row in rows), default=0) or 1
    step = 780 / len(rows)
    shapes = []
    for index, row in enumerate(rows):
        value = row.get(field, 0)
        height = 165 * value / maximum
        x = 30 + index * step
        shapes.append(f'<rect x="{x:.1f}" y="{215-height:.1f}" width="{step*.66:.1f}" height="{height:.1f}" rx="4" fill="{color}"/>'
                      f'<text x="{x+step*.33:.1f}" y="{202-height:.1f}" text-anchor="middle" font-size="20">{value}</text>'
                      f'<text x="{x+step*.33:.1f}" y="245" text-anchor="middle" font-size="17">{text(row["date"][5:])}</text>')
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="840" height="270" viewBox="0 0 840 270" role="img" aria-label="{text(title)}; values also in the timeline table"><title>{text(title)}</title>{"".join(shapes)}</svg>'
    return f'<div class="chart"><h3>{text(title)}</h3><div class="chart-scroll" tabindex="0" role="region" aria-label="{text(title)} chart">{svg}</div><small>UTC dates; last 14 active dates at most. Full values below.</small></div>'


def github_section(data):
    if data is None:
        return '<section id="delivery"><h2>Delivery</h2><p>GitHub metadata was not collected. Rerun manually with <code>--github</code> to include issue and PR statistics.</p></section>'
    elapsed = data['pr_created_to_merge']
    merged = data['merged_prs']
    ratio = f'{elapsed.get("at_most_1h", 0) / merged:.1%}' if merged else 'No samples'
    cards = card(number(merged), 'Merged PRs · all base branches') + card(duration(elapsed.get('median_seconds')), 'Median opening → merge') + card(ratio, 'Merged within one hour of opening') + card(number(data['prs_by_state'].get('OPEN', 0)), 'Open PRs at collection')
    inventory = [
        ('Issues · excluding PRs', number(data['issues_total'])),
        ('Open / closed issues', f'{data["issues_by_state"].get("OPEN", 0)} / {data["issues_by_state"].get("CLOSED", 0)}'),
        ('PRs · all states', number(data['prs_total'])),
        ('PRs merged / closed without merge / open', f'{merged} / {data["prs_by_state"].get("CLOSED", 0)} / {data["prs_by_state"].get("OPEN", 0)}'),
        ('Merged PRs targeting main', number(data['merged_prs_to_main'])),
        ('Merged PRs with same-repository closing references', f'{data["merged_prs_with_closing_issue_reference"]} / {merged}'),
        ('Distinct same-repository closing references', number(data['distinct_closing_issue_references'])),
        ('PR opening → merge · p75 / p90', f'{duration(elapsed.get("p75_seconds"))} / {duration(elapsed.get("p90_seconds"))}'),
        ('Longest merged PR lifetime', duration(elapsed.get('max_seconds'))),
        ('Median open PR age at collection', duration(data['open_pr_age'].get('median_seconds'))),
        ('Closed issue median creation → current closure', duration(data['closed_issue_created_to_close'].get('median_seconds'))),
        ('Closed issue duration sample size', number(data['closed_issue_created_to_close']['count'])),
        ('Excluded issue duration samples', ', '.join(str(value) for value in data['excluded_closed_issue_numbers']) or 'None'),
    ]
    areas = [(name, number(row['total']), number(row['open']), number(row['merged']), duration(row['elapsed'].get('median_seconds')))
             for name, row in data['by_area'].items()]
    return f'''<section id="delivery"><h2>Delivery at collection</h2><p class="muted">GitHub observed {text(data['observed_at'])}. Sequential API requests are not an atomic snapshot.</p>
<div class="cards">{cards}</div><p class="note">Elapsed PR time includes waiting and review but excludes coding before opening. It is not active agent time or test runtime. Open/closed counts are not a completion percentage.</p>
{table('Work inventory and elapsed intervals', ('Measure', 'Value'), inventory)}
<h3>Delivery by declared discipline</h3><p>Groups use current PR <code>area:</code> labels, falling back to current same-repository closing-issue area labels when a PR has none. They do not infer source ownership or complexity. Unlabeled PRs remain visible; multi-area PRs occur in each matching group. Durations include all base branches.</p>
{table('PR area labels', ('PR area', 'All PRs', 'Open', 'Merged', 'Median opening → merge'), areas)}</section>'''


def render(source, github=None):
    totals, history = source['totals'], source['history']
    code_lines = sum(source['by_discipline'].get(key, {}).get('lines', 0) for key in CODE)
    cards = card(number(totals['files']), 'Tracked regular files') + card(number(totals['lines']), 'Physical text lines') + card(number(code_lines), 'Implementation + tests + fixtures') + card(number(history['reachable_commits']), 'Reachable Git commits')
    daily = {row['date']: dict(row) for row in history['daily']}
    for row in github['daily'] if github else []:
        daily.setdefault(row['date'], {'date': row['date']}).update(row)
    rows = [(day, number(row.get('commits', 0)), number(row['files']) if 'files' in row else '—',
             number(row['lines']) if 'lines' in row else '—',
             number(row.get('prs_created', 0)) if github else 'Not collected',
             number(row.get('prs_merged', 0)) if github else 'Not collected',
             number(row.get('issues_created', 0)) if github else 'Not collected',
             number(row.get('currently_closed_issues_closed', 0)) if github else 'Not collected')
            for day, row in sorted(daily.items())]
    tokens = Path(__file__).with_name('assets').joinpath('tokens.css').read_text(encoding='utf-8')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Repository statistics · nand2mario</title>
<style>{tokens}\n{STYLE}</style></head><body><main>
<header><div class="eyebrow">nand2mario · source and delivery snapshot</div><h1>Repository statistics</h1>
<p>Game Boy RTL, independent verification, FPGA integration, host tooling and original game software in one measured repository.</p>
<p class="snapshot"><strong>Frozen manual snapshot.</strong> These values do not update when you open this page. The source commit and GitHub observation time below identify exactly what was measured.</p>
<p class="muted">Source <code>{text(source['revision'])}</code><br>GitHub observed: {text(github['observed_at']) if github else 'not collected'}</p></header>
<nav class="project-nav" aria-label="Project documentation"><a href="index.md">Documentation home</a><a href="presentations/README.md">Presentation library</a><a href="project-statistics.md">How to read this snapshot</a></nav>
<nav class="report-nav" aria-label="Report sections"><a href="#source">Source</a><a href="#delivery">Delivery</a><a href="#timeline">Timeline</a><a href="#files">File types</a><a href="#method">Method</a></nav>
<section id="source"><h2>Size and disciplines</h2><div class="cards">{cards}</div>
<p>{number(totals['nonblank'])} nonblank lines · {number(totals['bytes'])} bytes · {number(totals['text_files'])} text files · {number(totals['binary_files'])} binary files.</p>
<p class="note">Repository lines include comments, generated vectors, JSON pixels and SVG artwork. They do not measure executable complexity, feature completeness, correctness or authorship.</p>
{size_table('Exclusive source disciplines', source['by_discipline'])}</section>
{github_section(github)}
<section id="timeline"><h2>Timeline</h2><p>Source size uses the last first-parent commit on each active UTC date, bounded by the source SHA. GitHub events use their own collection window; the latest day may be partial.</p>
<div class="grid">{chart('Snapshot first-parent commits per active date', history['daily'], 'commits', '#93e7bd')}{chart('PR merges per active date · all bases', github['daily'] if github else [], 'prs_merged', '#8bd5ff')}</div>
{table('Daily source and GitHub events', ('UTC date', 'Commits', 'Files', 'Text lines', 'PRs opened', 'PRs merged', 'Issues opened', 'Current closures'), rows)}
<p class="muted">{number(history['first_parent_commits'])} first-parent commits; {number(history['reachable_commits'])} reachable commits. Squash merges hide author-branch commit churn. Issue closures are current closure timestamps, not a complete reopen-event history.</p></section>
<section id="files"><h2>Structure and file types</h2>{size_table('Root directories', source['by_top_directory'])}{size_table('File extensions', source['by_extension'])}</section>
<section id="method"><h2>Counting rules and limits</h2>
<p>Git blobs at the named revision supply regular tracked files only. Local edits, ignored worktrees/build output, tool installations and Git metadata are excluded. {len(source['skipped_nonregular'])} nonregular entries were skipped. NUL-containing or invalid UTF-8 blobs count as binary and have no line count.</p>
<p>Physical lines include blank/comment lines and a final unterminated line. Nonblank counts remove whitespace-only lines; a UTF-8 BOM is ignored. Classification is exclusive by path and type; the implementation/test subtotal includes RTL, FPGA HDL, verification programs, assembly, host implementation and host tests. Constraints, art and generated vector banks are separate. Extension totals mix design and verification.</p>
<p>GitHub counts cover all accessible issues and PRs in this repository, across base branches; the main-target count is reported separately. PR duration samples include merged PRs only. Closed-issue durations can include backlog and reopen cycles. Percentiles use linear interpolation. Current labels may differ from labels at delivery. No AI-authorship percentage, labor savings or complexity score is inferred.</p>
<p>Refresh manually with <code>python tools/wiki/repository_stats.py --revision origin/main --output workdir/repository-stats --github --exclude-closed-issue 7 --html wiki/statistics.html</code>. Review and commit the generated HTML. CI validates and publishes committed output; it never collects statistics. This report can be read offline and needs no script, font, stylesheet or API download.</p>
</section><footer>Generated by tools/wiki/repository_stats.py and statistics_report.py. Shared wiki design tokens are embedded. This frozen report may exclude its own delivery and later source changes; source and GitHub timestamps are deliberately separate.</footer>
</main></body></html>\n'''
