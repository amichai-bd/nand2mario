# Original linker fixture

These independently authored sources exercise a forward branch, a cross-unit
absolute address/call, fixed ROM0, floating ROM1, and allocation-only WRAM.
The layout deliberately places code at 0200 and the second unit at 4000.
`Start` is an emitted instruction boundary. The direct-entry header owns
0100..014F and contains no logo asset.

The linker test suite checks exact bytes and computes header/global checksums
with separate byte-by-byte loops. This fixture is tooling evidence, not a CPU
or Game Boy program acceptance result.
