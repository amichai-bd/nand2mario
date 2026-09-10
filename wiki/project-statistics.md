# Repository statistics

Open the [HTML statistics report](statistics.html), also available in the wiki's
**Stats** tab. It is one committed, self-contained snapshot with source-size,
discipline, file-type, timeline and GitHub delivery tables and charts.

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
