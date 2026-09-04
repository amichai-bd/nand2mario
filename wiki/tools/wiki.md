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

The Pages workflow runs only after a push to `main` or a manual dispatch. Its
build job runs the same command, uploads `workdir/wiki/site/`, and passes that
artifact to a separate deploy job. Deployments use the `github-pages`
environment and a single `pages` concurrency group.

A repository administrator must select **GitHub Actions** as the Pages source
before the first deployment. Pull requests never deploy.

## References

- [MkDocs configuration and link validation](https://www.mkdocs.org/user-guide/configuration/)
- [GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Pages publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [GitHub Actions secure use](https://docs.github.com/en/actions/reference/security/secure-use)
