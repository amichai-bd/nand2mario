# Selected Mooneye acceptance

Issue [103](https://github.com/amichai-bd/nand2mario/issues/103) selects only
`acceptance/bits/reg_f.s` from the [locked source](pins.json).
This selection is not full Mooneye or CPU coverage.

The unchanged test initializes SP to `e000`, writes both all-one and all-zero
flag values through PUSH/POP, and checks that the low flag nibble reads zero.
It asserts C=`f0` and E=`00`; the inherited high byte in D is not asserted.
The upstream case lists DMG among its passing models. The project applies its
existing `dmg-direct-v1` state, not a hardware boot image. Its entry stub is
NOP/JP150 at 100. Real WRAM/echo, HRAM, VRAM and PPU operations are required by
the test and reporting library. LY reads must come from the PPU.

Completion is the instruction retirement at the independently linked
`quit@serial_dump` symbol, bank 1/address `4a81`, opcode `40` (LD B,B). Require the
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
The builder rejects any different ROM hash or linked completion symbol.

The adapter uses the existing supported Intel initialization and real
LOAD_BEGIN/LOAD_END adoption. Its explicit external-fixture validator checks
the pinned build, exact ROM, header and checksums before emitting memory files.
Default original-software preload validation remains strict. The stock Mooneye
header differs from the project's original-software packager; do not rewrite it
or introduce a skip-validation option. No product RTL change is part of 103.

Use the [shared Python builder](../python/README.md) with targets
`mooneye-reg-f`, `mooneye-corrupt` and `mooneye-missing`. Each builds the locked
tool and unmodified case before simulation. The declared Python inputs include
the pins and notices; compiler files and CMake modules enter the stage identity.
Set `$env:N2M_MOONEYE_BUILD_HOST='wsl'` in PowerShell to build with the locked
Ubuntu host toolchain. The default remains the pinned Windows toolchain; unknown
hosts fail. WSL builds in the same ignored attempt directory through its mounted
Windows path. No ROM import or tool-build cache bypass is used. The host identity
hash covers executables, compiler headers, GCC support files, system libraries
and CMake modules, and is rechecked before and after building. A changed host
requires a reviewed pin update. Questa and Intel memory simulation stay on Windows.

WLA 10.6 sorts equal-priority, equal-size sections without returning equality in
`wlalink/write.c:_sections_sort`. Linux and Windows therefore place eight helper
labels differently. The lock retains one exact ROM hash for each host. Both use
the unchanged reg_f instructions and completion address; the Linux build is not
expected to reproduce the Windows byte layout. The selected host's exact hash,
complete checksums and completion symbol are required again before simulation.
Link-file object paths are quoted so build tags may contain spaces.

Build commands have a 120-second timeout with retained output, including timeout
failures. Only WLA's unused `tests/` extraction is omitted to avoid intentional
long-filename fixtures on Windows; the complete archive remains in the attempt.
Linux commands also have a 110-second process-group timeout and a two-second kill
grace. The public test supervisor supplies its execution deadline so Linux groups
terminate before the Windows process-tree cleanup deadline.

The controller checks loaded-and-paused epoch 2 before RUN. The simulation uses
the existing 25 MHz clock and 3.125 Mbaud UART, a 500 ms total simulated bound,
and the shared 300-second hard wall bound, with a 120-second runtime target.
That target is not a measured result. After RUN, dots must advance at each 10 us check.
Completion must occur within 1,000,000 dots. All instruction retirements and bus
commits are recorded; this test checks the selected upstream verdict, not an
independent instruction-by-instruction oracle for the reporting library.

The corrupt target forces the six actual public retirement registers to `42`
at the linked instruction. The missing target replaces the actual CPU read
response there with HALT (`76`); IE is zero and the real PPU keeps advancing.
The unchanged checker must reject these with `MOONEYE_COMPLETION_REGISTERS`
and `MOONEYE_MISSING_COMPLETION`. A passing test ends immediately on completion,
before the upstream serial routine. Retain XML, client transactions, complete
records, waves, build provenance and the observed completion under the attempt.
