# Repository statistics

Open the [HTML statistics report](statistics.html), also available in the wiki's
**Stats** tab. It is a committed, self-contained **frozen snapshot**, not a live
dashboard. The source commit and GitHub collection timestamp identify exactly
what was measured; opening the page later does not refresh its values.

The report covers source size, disciplines, file types, first-parent growth and
GitHub delivery intervals. Use it to understand the shape and activity of the
repository, not as a readiness or productivity score.

## Read the numbers carefully

- Source lines include comments, generated vectors, JSON pixel data and generated
  SVG review art. They do not measure executable complexity or feature quality.
- PR opening-to-merge time includes waiting and review, but excludes development
  before the PR was opened. It is not active engineering time.
- Open/closed issue counts are inventory at collection, not a completion
  percentage. Closed-issue age can include backlog and reopen cycles.
- Area labels describe declared delivery categories. They do not infer code
  ownership, effort or complexity.
- No AI-authorship percentage, labor-saving estimate or project-readiness score
  is inferred from these measurements.

For the current architecture and implementation boundaries, start at the
[documentation home](index.md). For worked explanations, use the
[presentation library](presentations/README.md).

## Refresh the snapshot

A scheduled script on the owner's PC refreshes the snapshot without an agent.
`tools/wiki/refresh_statistics.py` fetches `origin`, and stops when the source
revision recorded in `wiki/statistics.html` on `origin/main` already equals
`origin/main`. Otherwise it creates a worktree `worktrees/stats-refresh-<utc>/`
on a branch of the same name, runs the collector command below with
`--revision origin/main`, commits the changed `wiki/statistics.html` alone, pushes,
opens a non-draft pull request under the
[automated statistics refresh](agents/pull-requests.md#automated-statistics-refresh)
policy class, waits for `PR policy`, merges with the head pinned, and removes
its worktree and branch. Any failure closes the pull request it opened, removes
the worktree and branch, and exits non-zero. It never changes the checkout it
runs from. A lock under `workdir/` refuses an overlapping run.

Run it by hand from the repository root:

```text
python tools/wiki/refresh_statistics.py
python tools/wiki/refresh_statistics.py --dry-run
```

`--dry-run` collects and commits in the worktree, prints what it would push,
open and merge, and cleans up. Hosted CI never runs the collector; the schedule
is the only unattended path, and the guard keeps it from opening a pull request
when `main` has not moved.

An example schedule runs the script hourly through Windows Task Scheduler. The
paths are placeholders for the machine's Python and checkout:

```text
schtasks /Create /SC HOURLY /TN "nand2mario statistics refresh" /TR "\"<python>\" \"<checkout>\tools\wiki\refresh_statistics.py\""
```

The task needs a `gh` login and Git credentials for the account that owns the
checkout. Its stdout is the run log.

The collector itself, for a manual refresh from a checkout with complete Git
history:

```text
python tools/wiki/repository_stats.py --revision origin/main --output workdir/repository-stats --github --exclude-closed-issue 7 --html wiki/statistics.html
```

The source SHA and GitHub collection timestamp are separate. Ordinary CI only
validates and publishes the committed file. Without `--github`, the report
contains source statistics and marks GitHub data as not collected.

The [collector contract](tools/wiki/SPEC.md#repository-statistics) defines counting,
failure handling and exclusions. Source/PR quantity and elapsed delivery time do
not measure complexity, correctness, completeness or active labor.

<a id="size-and-disciplines"></a>
<a id="directory-structure"></a>
<a id="file-types"></a>
<a id="growth-and-delivery-timeline"></a>
<a id="the-issue-to-merge-loop"></a>
<a id="reproduce-and-interpret"></a>

Earlier section links now lead to this entrypoint; all measurements live in the
[single HTML report](statistics.html).
