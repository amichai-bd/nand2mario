# Software oracle provenance

The [shared manifest](../n2m/dependencies.json) owns RGBDS's source/version pin,
official Windows/Linux x86_64 release archive hashes, and hashes for the license
and upstream build metadata. The release tag was checked against the pinned
commit; archive digests were checked against GitHub's release asset metadata.

RGBASM and RGBLINK are installed unmodified from the official prebuilt archive.
This is an upstream binary installation, not a local source build or a claim of
bit-for-bit source-to-binary reproduction. The cached archive and each installed
executable are checked before every execution. No arbitrary PATH installation is
accepted. The [software SPEC](../../wiki/tools/sw/SPEC.md#implemented-oracle)
owns commands, failure behavior, artifacts, and fixture scope.

The pinned root `LICENSE` grants MIT permission for these tools and is retained
beside every installation. The instruction manual has the same MIT notice.
Only the two executable members are installed; RGBFIX, RGBGFX, upstream tests,
external/nonfree test dependencies and commercial ROMs are not used. Original
project material retains the [source policy](../../wiki/tools/provenance.md).

Local provisioning uses Python's standard library (PSF-2.0; version recorded by
the builder) and the host operating system. It installs no host build packages.
The upstream release workflow, dependency script and CMake configuration are
retained as hashed build provenance, never executed. They describe upstream
MSVC/CMake/Ninja/Bison or GNU build tools; their exact build-host package versions
are not attested by the release archive, and are not claimed as local evidence.
A future local source-build path must record its actual build dependency versions,
licenses and source/build hashes before acceptance.

All downloaded bytes, notices, installed tools and generated fixture output stay
under ignored `workdir/builds/<tag>/sw/oracle/`. No RGBDS source is vendored or
modified. A failed download, hash, version, assembly, link or comparison blocks
conformance; no fallback oracle is used.

## Assembler opcode data

The [provenance index](../provenance.json) pins the reviewed `mgbdis`
`instruction_set.py` and its raw source SHA-256. Its MIT notice is retained in
[MGBDIS_LICENSE.md](MGBDIS_LICENSE.md). `opcodes.json` adapts only the base/CB
opcode-to-form dictionaries: illegal slots and disassembler aliases are omitted;
explicit accumulator, full-address LDH and address-based JR spellings follow the
software contract. RST/bit variants retain their architectural opcode fields.
No upstream executable disassembler logic, external tests, ROMs or assets are
imported. Original parser, expressions, schemas and tests do not change its terms.

The independent conformance matrix is constructed from instruction families and
register/condition combinations without reading the imported table. Unmodified
RGBDS owns its expected instruction bytes and relocations, so the imported table
cannot supply both implementation and oracle answers.
