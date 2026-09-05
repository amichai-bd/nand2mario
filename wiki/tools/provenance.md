# Source and provenance policy

Original project hardware and software remain private for now. No license or
reuse rights are granted for original project material. A future license or
visibility change requires an explicit owner decision. Third-party material
retains its own terms.

The private repository still publishes its selected text sources through the
[public wiki](wiki.md). This standing publication authorization is unchanged;
public reading does not grant a reuse license. Treat all committed files as
potentially public. Keep private inputs and results outside tracked sources.

## External inputs

Before importing or downloading external code, tests, tools, or assets, record:

- Name and upstream source URL.
- Exact commit or release version; archive/package hashes when downloaded.
- License identifier and location of the applicable license and notices.
- Purpose, including whether used as an external tool, copied, or modified.
- Local changes, explicitly `none` when unchanged.
- Where it is stored and any redistribution or use restrictions.

Keep the authoritative pin in the dependency's existing lock or manifest and
link it from the [provenance index](../../tools/provenance.json). Do not duplicate
pins in prose. Retain upstream notices with imported files or downloaded tools.
Unknown permission blocks copying; it does not authorize choosing a license.
Review compatibility for the intended use before an import. A tool's license
does not automatically establish rights to its input or output.

The index covers the current external build and test tools. No third-party HDL,
test ROM, game asset, or emulator code is imported. New imports must add a record
before use. Reproducible fetching of future verification suites belongs to
[GAP-013](../preflight-gaps.md#gap-013-external-dependencies).

`frog-bui` is a process and behavioral research reference only. Its inspected
revision and absent root license are recorded in the
[wiki dependency notes](../../tools/wiki/THIRD_PARTY.md). Do not copy its source
without confirmed file-level reuse terms. Cite research sources when deriving
original contracts and tests; record any later licensed import separately.

## ROMs, assets, and private results

Never commit commercial game ROMs, Nintendo boot ROMs, saves, credentials, or
copies encoded as text. This includes base64, hex dumps, memory initialization
files, screenshots, extracted tiles, and generated images derived from protected
content. Renaming or transforming data does not make it project-owned.

User ROMs are runtime inputs only: use an external path or ignored
`workdir/private/`. Keep ROM identity, hashes, headers, absolute machine paths,
device serial numbers, captures, and private logs in ignored local results.
Report public acceptance using neutral fixture names and pass/fail results.
Loaders must accept runtime paths and avoid embedding private values in sources,
PRs, wiki pages, or published CI artifacts.

Commit original assembly, source assets, and small original test vectors with
their authorship stated in the owning specification. Build their ROMs, memory
images, screenshots, and other generated output under ignored `workdir/`.
Imported open test sources need the same provenance and permission review as
other dependencies; open availability alone is insufficient.

## Enforced checks and limits

`.gitignore` excludes generated output, private directories, cartridge/save
formats, memory images, and common credential files. The required `Wiki check`
and Pages build scan every tracked file before publication. They reject those
private paths and protected extensions even after `git add -f`, plus binary
signatures, invalid UTF-8, and binary control bytes. The existing text-only rule
also excludes binary screenshots and generated images.

Run `python tools/wiki/check.py` after staging intended source changes; untracked
files are not the publication input. Negative tests cover forced tracked private
content and ASCII-only ROM/save files. Checks report paths, never file contents.

These checks cannot identify every secret or distinguish a commercial hex dump
from original text vectors. Authors and independent reviewers must inspect the
staged diff, provenance, and artifact upload paths. Do not force-add private
content or publish local result directories to bypass these rules.
