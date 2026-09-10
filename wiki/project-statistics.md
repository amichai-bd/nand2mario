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

Refresh it manually from a checkout with complete Git history:

```text
python tools/wiki/repository_stats.py --revision origin/main --output workdir/repository-stats --github --exclude-closed-issue 7 --html wiki/statistics.html
```

The source SHA and GitHub collection timestamp are separate. Review the generated
HTML and commit it; ordinary CI only validates and publishes that file. It never
collects statistics or commits refreshed output. Without `--github`, the report
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
