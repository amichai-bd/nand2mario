# Software toolchain requirements

The pinned RGBDS oracle, complete documented SM83 assembler, deterministic linker
direct-profile cartridge packager, and original shade-asset conversion are
implemented. The original program remains assigned to #88 and depends on its
CPU/PPU/loader and execution evidence.

The [SPEC](SPEC.md) owns the assembly language, object schema, independent
conformance, deterministic artifacts and remaining delivery dependencies. The
[ownership map](../../ownership.md) connects implementation, tests and provenance.
The [charter](../../src/project-charter.md) requires the complete toolchain for
`v0.5`; assembler coverage alone does not prove CPU or program behavior.
