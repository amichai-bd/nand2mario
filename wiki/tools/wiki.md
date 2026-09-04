# Wiki build

The repository owns its HTML shell, navigation, and build. Python-Markdown parses
Markdown; MkDocs is not used. Run:

```text
python tools/wiki/check.py
```

This creates the pinned environment, runs publication tests, checks tracked
content and links, then writes `workdir/wiki/site/`. Serve that directory over
HTTP for local viewing. The command does not deploy.

## Sources and navigation

Publish tracked `README.md`, `AGENTS.md`, `wiki/`, `.agents/skills/`, `src/`,
`tools/`, and `cfg/`. Referenced tracked files outside these roots are included
as source dependencies without category navigation. Unreferenced files outside
the roots and untracked drafts are not published. Stage new files before checking.

Top tabs are Home, Src, Agents/Skills, Tools, Cfg, and Presentations. Each tab has
a directory-based sidebar and file filter. Src includes RTL, DV, SW, and FPGA.
Home defaults to README; its toggle selects AGENTS. URLs identify the original
file with `?page=wiki/tools/wiki.md`; fragments select headings or `#L12` source
lines. Former MkDocs document paths redirect to the matching source.

Keep each fact in its original file. The site uses generated output only, never
committed document mirrors. Every page exposes an escaped source viewer with the
path and line numbers. Published source references work without GitHub access.

## Content and embeds

Markdown renders links, headings, tables, and code blocks. Repository-relative
links resolve from the original source path. Missing tracked targets and anchors
fail the build. Links to this repository's `blob/main` and `tree/main` paths also
resolve locally. Other HTTP, HTTPS, `mailto:`, and scheme-relative web links
(`//example.com/path`) are left unchanged. Other explicit URL schemes fail the
build, with or without a host. Runtime assets must still be local.

HTML documents under `wiki/` and SVG assets embed in an iframe with script permission
and without same-origin privileges. A standalone link opens the original file;
relative assets retain their repository layout under `files/`. Fullscreen expands
the document wrapper so source overlays remain visible. Browser restrictions on
embedded fullscreen may require the wiki's Fullscreen button.

The generated HTML copy adds a small navigation bridge. Inside the wiki, local
document links open the rendered target and heading in the shell. Standalone
links keep their original relative `href`. SVG resource links and `srcset` assets
keep resource semantics rather than becoming document routes.

Skill templates and other source HTML render as escaped text, not live pages.
Do not put credentials or private machine or ROM facts in public source files.

HTML source links use a real relative `href` as a standalone fallback:

```html
<a href="../../src/rtl/README.md" data-source="src/rtl/README.md" data-line="1">RTL source</a>
```

Embedded scripts may post `{type: "n2m:source", path: "src/rtl/README.md", line: 1}`
to the parent. The shell accepts messages only from its current iframe and only
opens known published paths and valid lines. Opaque sandbox origins require a
`"*"` target for this non-secret message. A `n2m:fullscreen` message requests the
same wrapper; failure returns `n2m:fullscreen-result` with `ok: false`.

Shared visual attributes live in `tools/wiki/assets/tokens.css`: `--bg`,
`--panel`, `--surface`, `--text`, `--muted`, `--accent`, `--border`, `--font`,
`--mono`, and `--radius`. Use the [presentation contract](../presentations/README.md)
and [authoring skill](../../.agents/skills/html-presentation/SKILL.md) for decks
under `wiki/presentations/`. Source files remain the authority for all content.

## Text-only policy and deployment

The required Wiki check scans every tracked repository file, including files not
published. It rejects binary extensions (including PNG, JPEG, PDF, PPT/PPTX),
known binary signatures, invalid UTF-8, and binary control bytes. Textual Markdown,
HTML, SVG, code, and configuration are allowed. No binary fonts or external CDN
runtime are required. Keep generated images, PDFs, ROMs, and other binary artifacts
under ignored `workdir/`. Tests include disguised PDF/PNG, NUL, invalid UTF-8,
and valid Unicode SVG inputs.

Dependency versions, hashes, and licenses are recorded in
[the dependency note](../../tools/wiki/THIRD_PARTY.md).

PRs run the same read-only build and never deploy. Merges to `main` automatically
publish the artifact with standing authorization. Pages uses separate build and
deploy jobs, the `github-pages` environment, and serialized deployment. The source
repository is private; its Pages site is public.

The build/deploy split follows process ideas from `frog-bui`; no code was copied.
See [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
