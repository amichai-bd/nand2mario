# Wiki build dependencies

`requirements.txt` pins and hashes the complete Python dependency set. Packages
come from [PyPI](https://pypi.org/) over pip.

| Packages | License |
|---|---|
| [Python-Markdown 3.10.3](https://pypi.org/project/Markdown/3.10.3/) | BSD-3-Clause |
| [Playwright 1.62.0](https://pypi.org/project/playwright/1.62.0/) | Apache-2.0 |
| [pyee 13.0.1](https://pypi.org/project/pyee/13.0.1/) | MIT |
| [greenlet 3.5.5](https://pypi.org/project/greenlet/3.5.5/) | MIT and PSF-2.0 |
| [typing_extensions 4.16.0](https://pypi.org/project/typing_extensions/4.16.0/) | PSF-2.0 |

The lock contains the wheel and source distribution hashes. Markdown has no
runtime dependencies. The shell, navigation, and generator are repository-owned;
there is no MkDocs runtime, CDN, binary font, or copied theme.

`requirements-browser.txt` separately pins Playwright and its transitive packages
with PyPI release hashes. The installed Playwright version selects its matching
Chromium revision (1.62.0 uses revision 1234). Browser binaries and bundled notices
remain in the ignored cache; Chromium uses BSD-style and bundled third-party
licenses. These are test dependencies, not site runtime assets.

The runner follows Playwright's [library API](https://playwright.dev/python/docs/library),
[headless shell setup](https://playwright.dev/python/docs/browsers#chromium-headless-shell),
and [CI guidance](https://playwright.dev/python/docs/ci). No upstream test code is copied.

The workflows use GitHub's `actions/checkout`, `actions/setup-python`,
`actions/configure-pages`, `actions/upload-pages-artifact`, and
`actions/deploy-pages`, and `actions/upload-artifact`. Each uses the MIT license and is pinned to a full commit
SHA in its workflow.

Process reference: `amichai-bd/frog-bui` at
`d942998610bb69ee1351aa1adcdf8bd38a35fed1`. Its separate check and deploy
workflows informed the build and deployment split. The reference has no root
license, so no source was copied.
