# Selected Mooneye acceptance

Issue [103](https://github.com/amichai-bd/nand2mario/issues/103) selects only
`acceptance/bits/reg_f.s` from the [locked source](pins.json). Adapter execution
is not yet implemented. This selection is not full Mooneye or CPU coverage.

The unchanged test initializes SP to `e000`, writes both all-one and all-zero
flag values through PUSH/POP, and checks that the low flag nibble reads zero.
It asserts C=`f0` and E=`00`; the inherited high byte in D is not asserted.
The upstream case lists DMG among its passing models. The project applies its
existing `dmg-direct-v1` state, not a hardware boot image. Its entry stub is
NOP/JP150 at100. Real WRAM/echo, HRAM, VRAM and PPU operations are required by
the test and reporting library. LY reads must come from the PPU.

Completion is the instruction retirement at the independently linked
`quit@serial_dump` symbol, address `4a81`, opcode `40` (LD B,B). Require the
whole B/C/D/E/H/L tuple `3,5,8,13,21,34`. The all-`42` tuple is upstream failure;
any other tuple fails with expected and actual fields. An LD B,B at another
address is not completion. This breakpoint precedes serial probing or transfer;
serial behavior is outside this selection and must not be replaced with fake
SC reads. Other cases, model-specific boot assumptions, mappers, manual/audio
tests and unsupported peripherals remain excluded.

The pinned upstream Makefile and CI use WLA-DX, not RGBDS. Build the pinned
assembler/linker source and selected test without rewriting its syntax, header,
assets or instructions. Retain source, tool and image hashes, command output
and [separate notices](THIRD_PARTY.md) under the build's ignored workdir.
The locked ROM hash was derived from the unmodified selected source and must
be independently checked when the adapter build is implemented.

The proposed adapter uses the existing supported Intel initialization and real
LOAD_BEGIN/LOAD_END adoption. Its explicit external-fixture validator must check
the pinned build, exact ROM, header and checksums before emitting memory files.
Default original-software preload validation remains strict. The stock Mooneye
header differs from the project's original-software packager; do not rewrite it
or introduce a skip-validation option. No product RTL change is part of103.

Remaining implementation and evidence: locked build/validation, exact completion
monitor, bounded missing-completion watchdog, actual corrupt-completion and
missing-completion mutations, portable rejection checks, and the three shared
Questa runs with installed Intel models. Independent current-head review and
required CI precede delivery.
