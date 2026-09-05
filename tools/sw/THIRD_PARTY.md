# Software oracle provenance

The [shared manifest](../n2m/dependencies.json) owns RGBDS's source pin.
Its root [MIT license][license] permits use/modification with copyright and
permission notices retained in copies or substantial portions. The instruction
manual also declares MIT. Retain notices with the installation. This review
permits an unmodified external RGBASM/RGBLINK oracle; original project material
and other inputs retain their own policies.

Fetch/build in ignored `workdir/tools`/`workdir/cache`; verify the exact Git
commit and record source/build hashes and executable versions. No code or
upstream tests are copied into repository sources. Local changes: none.
Do not enable upstream external/nonfree tests or fetch their dependencies.
Bundled ROMs/assets are not project fixtures; write original tests.

The implementation issue must record host build dependencies, licenses and
versions, retaining notices with installations. No archive/package download,
installation or oracle execution is claimed here. Downloaded archives/packages
require hashes before use. Fetch/build failure blocks conformance.

[license]: https://github.com/gbdev/rgbds/blob/307846b03ea89ee57bf75f179d5f8051175ac60d/LICENSE
