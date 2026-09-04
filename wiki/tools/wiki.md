# Wiki build

The wiki renders existing repository files. One command creates the pinned
MkDocs environment, tests publication, and checks pages and anchors:

```text
python tools/wiki/check.py
```

Output goes to `workdir/wiki/site/`. The command fails on a build warning or a
broken internal link. It does not deploy.

## Sources and navigation

The build stages tracked `wiki/`, `README.md`, `AGENTS.md`, and
`.agents/skills/` files under `workdir/wiki/docs/`. Generated copies are ignored;
edit the originals. Untracked drafts are not published. Stage new files with
`git add` before checking them.

The landing page shows the full README by default. The README/AGENTS buttons
switch documents and work with the keyboard. Without JavaScript both documents
remain readable. Source and edit links point to the original repository files.

Wiki and skill navigation follows their directory structure. Skill templates,
examples, references, scripts, and configuration files are included. Scripts and
other text support files render as escaped text; the build never runs them.
Raster images are copied as assets. Other binary files link to their source.

Markdown links, reference links, images, and anchors resolve from each original
file's location. Links to repository files outside the published set open GitHub.
Code examples are left untouched. Existing wiki page paths stay stable; its
former landing page is available as `wiki-index/`.

Keep each rule or specification in its original owner file. Link to that source
instead of adding a second version for the website.

## Checks and deployment

The PR workflow runs the same command with read-only repository access.
Dependency versions and licenses are recorded in
[`tools/wiki/THIRD_PARTY.md`](https://github.com/amichai-bd/nand2mario/blob/main/tools/wiki/THIRD_PARTY.md).

Merging to `main` authorizes automatic wiki deployment; no further approval is
needed. The Pages workflow runs after a push to `main` or a manual dispatch. Its
build job runs the same command, uploads `workdir/wiki/site/`, and passes that
artifact to a separate deploy job. Deployments use the `github-pages`
environment and a single `pages` concurrency group.

GitHub Actions is the configured Pages source. Pull requests never deploy.

The Pages site is public even while the source repository remains private.
Private-repository Pages requires a GitHub plan that supports it. Treat every
published source as public: do not include credentials, private ROM facts,
unique device identifiers, or machine-specific paths.

## References

- [MkDocs configuration and link validation](https://www.mkdocs.org/user-guide/configuration/)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
