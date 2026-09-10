# Wiki build

Purpose and acceptance links: [PRD](PRD.md).

The repository owns its HTML shell, navigation, and build. Python-Markdown
parses Markdown; MkDocs is not used. Run:

```text
python tools/wiki/check.py
```

This creates the pinned environment, runs publication tests, checks tracked
content and links, then writes `workdir/wiki/site/`. Serve that directory over
HTTP for local viewing. The command does not deploy.

## Browser checks

First run `python tools/wiki/check.py --browser --install-browser`.
This installs the pinned Chromium headless shell and its OS dependencies. Later,
`python tools/wiki/check.py --browser` reuses the browser under ignored
`workdir/tools/playwright/`. CI uses the first command on PRs and on `main` before
publication. A browser failure blocks the existing Wiki check or Pages build.

If downloads are unavailable locally, add `--browser-executable <path>` to use
a compatible cached Chromium executable. Its version is recorded; this explicit
override cannot substitute for CI. Browser policies or version mismatches may
prevent launch. No failure silently falls back or skips the suite.

Checks use real page interactions for categories, filtering, the README/AGENTS
toggle, source overlays, slides, fullscreen when supported, HTML links, and
recovery from a missing page. Unexpected console errors and page exceptions fail.
The browser's optional favicon request is handled locally. Waits observe page
state without fixed sleeps.

A second stage then checks quality regressions in the same browser: slide
fragment deep links, safe fallback for unknown and malformed fragments, keyboard
paging, print emulation showing every slide with readable dark diagram text, and
statistics charts that scroll instead of shrinking at narrow widths. It writes
`quality-result.json` and `quality-trace.zip` beside the interaction results. Both
stages must pass; the first failure stops the run.

The test owns an ephemeral loopback server thread and browser. Both close in
`finally` blocks; a forced failure also exercises cleanup. The server's listener
and thread are checked after shutdown. Results, trace, browser temporary files,
and failure screenshots stay under `workdir/wiki/browser/`; CI uploads failure
evidence as an artifact, not to Pages. This Chromium suite does not assess
other browsers or screen readers.

## Sources and navigation

Publish tracked Markdown, HTML, and SVG documentation under `wiki/` and
`.agents/skills/`, plus root `README.md` and `AGENTS.md`. HTML skill templates and
helper scripts are excluded; Markdown templates remain documentation. Stage new documents before checking.

Implementation files under `src/`, `tools/`, and `cfg/` are excluded from
pages, navigation, search, document source payloads, copied files, and redirects.
Links cannot expand this boundary: references to excluded tracked files become
GitHub links. They require repository access. All tracked files still undergo
private-file and text checks, including excluded files.

Package only these shared runtime files from `tools/wiki/assets/`: `tokens.css`,
`shell.css`, `shell.js`, `presentation.css`, `presentation.js`, and `embed.js`.
The shell HTML becomes the site entry point. CSS and JavaScript under `wiki/`
are documentation assets. Runtime files are copied outside the content manifest;
they never become navigation, search, or source-viewer entries. Resource links
and CSS imports to excluded files fail the build.

Top tabs are Home, Src, Agents/Skills, Tools, Cfg, and Presentations. Each tab has
a directory-based sidebar and file filter. Each tab lists its published documentation; an empty category says so.
Home defaults to README; its toggle selects AGENTS. URLs identify the original
file with `?page=wiki/tools/wiki/SPEC.md`; fragments select headings or `#L12` source
lines. Former MkDocs document paths redirect to the matching source.

Keep facts in their original files. The site uses only generated output, never
committed document mirrors. Every documentation page exposes its own escaped source viewer with the
path and line numbers. Implementation source is available only through GitHub.

## Content and embeds

Markdown renders links, headings, tables, and code blocks. Repository-relative
links resolve from the original source path. Missing tracked targets and anchors
fail the build. Links to this repository's `blob/main` and `tree/main` paths also
resolve locally for documentation and externally for excluded files. Other HTTP, HTTPS, `mailto:`, and scheme-relative web links
(`//example.com/path`) are left unchanged. Other explicit URL schemes fail the
build, with or without a host. Runtime assets must still be local.

HTML documents under `wiki/` and SVG assets embed in an iframe with script permission
and without same-origin privileges. External links may open a separate tab
outside the sandbox. A standalone link opens the original file;
relative assets retain repository layout under `files/`. Fullscreen expands
the document wrapper so source overlays remain visible. Browser restrictions on
embedded fullscreen may require the wiki's Fullscreen button.

Generated HTML adds a small navigation bridge. Inside the wiki, local
document links open the rendered target and heading in the shell. Standalone
document links keep their original relative `href`; excluded targets become GitHub links. SVG resource links and `srcset` assets
keep resource semantics rather than becoming document routes.

HTML skill templates and implementation HTML are not published.
Do not put credentials or private machine or ROM facts in published documents.

HTML references use a real relative `href` in the repository:

```html
<a href="../../../src/rtl/README.md" data-source="src/rtl/README.md" data-line="1">RTL source</a>
```

For excluded targets the build replaces this link with a GitHub URL and line
fragment, and removes source-popup attributes. This works in both embedded and
standalone documents. Embedded scripts may post `{type: "n2m:source", path: "src/rtl/README.md", line: 1}`
to the parent. The shell accepts only its current iframe's messages and
opens only known published paths and valid lines. Opaque sandbox origins require a
`"*"` target for this non-secret message. A `n2m:fullscreen` message requests the
same wrapper; failure returns `n2m:fullscreen-result` with `ok: false`.

Shared visual attributes live in `tools/wiki/assets/tokens.css`: `--bg`,
`--panel`, `--surface`, `--text`, `--muted`, `--accent`, `--border`, `--font`,
`--mono`, and `--radius`. Use the [presentation contract](../../presentations/README.md)
and [authoring skill](../../../.agents/skills/html-presentation/SKILL.md) for decks
under `wiki/presentations/`. Source files remain the authority for all content.

## Text-only policy and deployment

The required Wiki check scans all tracked files, including unpublished ones.
It also enforces the protected extensions and private path rules in the
[source and provenance policy](../provenance.md#enforced-checks-and-limits).
It rejects binary extensions (including PNG, JPEG, PDF, PPT/PPTX),
known binary signatures, invalid UTF-8, and binary control bytes. Textual Markdown,
HTML, SVG, code, and configuration are allowed. No binary fonts or external CDN
runtime are required. Keep generated images, PDFs, ROMs, and other binary artifacts
under ignored `workdir/`. Tests include disguised PDF/PNG, NUL, invalid UTF-8,
and valid Unicode SVG inputs.

Dependency versions, hashes, and licenses are recorded in
[the dependency note](../../../tools/wiki/THIRD_PARTY.md).

PRs run this read-only build and never deploy. Merges to `main` automatically
publish the artifact with standing authorization. Pages uses separate build and
deploy jobs, the `github-pages` environment, and serialized deployment. The source
repository is private; its Pages site is public.

The build/deploy split follows process ideas from `frog-bui`; no code was copied.
See [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Repository statistics

The manual `tools/wiki/repository_stats.py` collector generates the
[HTML statistics report](../../statistics.html). Run it from a repository
checkout with complete history, `--revision <commit>`, `--output workdir/<tag>` and
`--html wiki/statistics.html`. The HTML output is the explicitly authorized
committed generated report; scratch JSON stays under `workdir/`. It resolves the
commit and reads regular tracked Git blobs directly, reporting files, UTF-8
physical/nonblank lines, bytes, exclusive path/type categories and daily
first-parent growth. Comments remain included. Nonregular entries are reported
as skipped; NUL or invalid UTF-8 blobs are binary and excluded from line totals.

`--github` additionally reads paginated issues and PRs through authenticated `gh`;
`--repo owner/name` overrides repository discovery. Without that flag no network
is used. `--exclude-closed-issue <number>` excludes a reused issue from the
issue-duration summary and may be repeated. GitHub collection is sequential and
records its completion time; it does not reconstruct historical state. PR durations
use creation to merge; closed-issue durations use creation to current closure.
Percentiles use linear interpolation. Nested closing-reference truncation is
rejected before publication. Failed API pagination, missing tools, shallow Git
history and subprocess timeouts also fail without replacing the prior HTML.
Each subprocess has a 120-second timeout. Collection and rendering finish before
output writing; the HTML is replaced atomically. The tool never uses stale JSON
as a substitute for a failed requested GitHub collection.

The report embeds CSS (including shared wiki design tokens), SVG and tables with
no external runtime. It escapes data, distinguishes all-base PR metrics from the
main-target count, reports current PR area-label groups (falling back to closing
issue labels; groups can overlap), and
shows empty samples honestly. It includes no raw issue/PR titles or descriptions.
The **Stats** tab opens the HTML directly; the former Markdown page is only a
stable entrypoint. Removed standalone charts are not separately maintained.

The collector never runs automatically in CI, posts to GitHub or changes issues.
CI validates/publishes the committed HTML and runs offline fixture tests; it does
not collect live project statistics. Manual generation is the only refresh path,
including after merges. Quantity and elapsed intervals do not measure active
labor, complexity, authorship, hardware readiness or completeness. Tables and
charts are generated together from the same source/GitHub data.

Run `python -m unittest tools.wiki.test_repository_stats -v` for offline collector,
empty-sample, escaping and atomic-failure checks. The wiki browser suite checks
the Stats tab and report at desktop/mobile sizes, including the snapshot notice,
documentation navigation and keyboard-scrollable chart regions.
