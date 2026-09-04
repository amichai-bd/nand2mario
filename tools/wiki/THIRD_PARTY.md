# Wiki build dependencies

`requirements.txt` pins and hashes the complete Python dependency set. Packages
come from [PyPI](https://pypi.org/) over pip.

| Packages | License |
|---|---|
| MkDocs | BSD-2-Clause |
| click, colorama, Jinja2, Markdown, MarkupSafe | BSD-3-Clause |
| ghp-import, watchdog | Apache-2.0 |
| mergedeep, mkdocs-get-deps, platformdirs, PyYAML, pyyaml-env-tag, six | MIT |
| packaging | Apache-2.0 OR BSD-2-Clause |
| pathspec | MPL-2.0 |
| python-dateutil | Apache-2.0 OR BSD-3-Clause |

`pip-tools==7.5.2` (BSD-3-Clause) generated the lock file. It is not installed
by the wiki check.

The PR workflow uses GitHub's `actions/checkout` and `actions/setup-python`.
Both use the MIT license and are pinned to full commit SHAs in the workflow.

Process reference: `amichai-bd/frog-bui` at
`d942998610bb69ee1351aa1adcdf8bd38a35fed1`. Its separate check and deploy
workflows informed the split. The reference has no root license, so no source
was copied.
