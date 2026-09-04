# Wiki build

The wiki is a strict MkDocs site. One command creates the pinned environment,
builds the site, and checks internal pages and anchors:

```text
python tools/wiki/check.py
```

Output goes to `workdir/wiki/site/`. The command fails on a build warning or a
broken internal link. It does not deploy.

The PR workflow runs the same command with read-only repository access.
Dependency versions and licenses are recorded in
[`tools/wiki/THIRD_PARTY.md`](https://github.com/amichai-bd/nand2mario/blob/main/tools/wiki/THIRD_PARTY.md).

Pages deployment will use a separate main-only workflow after explicit
approval.

## References

- [MkDocs configuration and link validation](https://www.mkdocs.org/user-guide/configuration/)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
