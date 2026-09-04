# Wiki build dependencies

`requirements.txt` pins and hashes the complete Python dependency set. Packages
come from [PyPI](https://pypi.org/) over pip.

| Packages | License |
|---|---|
| [Python-Markdown 3.10.3](https://pypi.org/project/Markdown/3.10.3/) | BSD-3-Clause |

The lock contains the wheel and source distribution hashes. Markdown has no
runtime dependencies. The shell, navigation, and generator are repository-owned;
there is no MkDocs runtime, CDN, binary font, or copied theme.

The workflows use GitHub's `actions/checkout`, `actions/setup-python`,
`actions/configure-pages`, `actions/upload-pages-artifact`, and
`actions/deploy-pages`. Each uses the MIT license and is pinned to a full commit
SHA in its workflow.

Process reference: `amichai-bd/frog-bui` at
`d942998610bb69ee1351aa1adcdf8bd38a35fed1`. Its separate check and deploy
workflows informed the build and deployment split. The reference has no root
license, so no source was copied.
