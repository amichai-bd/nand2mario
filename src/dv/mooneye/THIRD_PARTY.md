# Mooneye fixture notices

The [lock](pins.json) owns URLs, revisions and file hashes. External files and
built ROMs remain under ignored workdir; this directory contains original
adapter metadata and documentation.

- Mooneye test source: copyright Joonas Javanainen and source-file contributors,
  MIT. Retain its complete LICENSE and selected source headers with fixtures.
- WLA-DX 10.6: copyright Ville Helin and contributors, GPL-2.0-or-later. Retain
  the complete upstream LICENSE and source with the built external tool.
- `common/font.bin`: derived from Lisa Milne/Darkrose's 2014 `font.c`,
  GPL-3.0-or-later. The source-page notice explicitly distinguishes the C bitmap
  source from the PNG's additional license choices. Retain the original font.c
  notice, source archive, source link and GPLv3 license with the selected fixture.
  Do not label the font or aggregate ROM solely MIT.

The pinned Mooneye font contains glyphs 1 through 127 with each bitmap row
duplicated into both Game Boy bitplanes. 125 glyphs match the original font.c;
glyphs 9 and 93 differ in the upstream adaptation. Preserve the pinned asset
unchanged. This adapter introduces no additional font changes.

Installed compiler/build tools are external host dependencies. Their exact
versions, file identities, commands and resulting WLA binaries belong to the
build record. They are not copied into product sources or redistributed.

The locked WLA CMake file declares minimum version 2.8.12. CMake 3.31.1 reports
its exact minimum-version deprecation warning; the builder explains only that
known text. Other warning/error text fails preparation. The build uses CMake's
unchanged `wla-gb` and `wlalink` targets, which do not reference upstream `tests/`.
That unused directory stays in the retained archive but is not extracted.
