# Palette boundary discriminator

[#194](https://github.com/amichai-bd/nand2mario/issues/194) corrects the native
adapter initial-fetch latency. The FC case checks its full execution across
VBlank. Residual cadence and palette diagnosis remains in
[#197](https://github.com/amichai-bd/nand2mario/issues/197); neither model is
assumed to be the silicon oracle. No RTL change is made.

The original integration setup is unchanged through LCDC commit592 and
retirement596. Its terminal HALT is replaced by `LD BC,2510`, then 2510 iterations
of `DEC BC; LD A,B; OR A,C; JR NZ`, two NOPs, `LD A,palette; LDH [FF47],A; HALT`.
The loop is `2510*28-4=70276` dots. The tail therefore commits BGP at70908,
retires it at70912 and retires HALT at70916, with10114 total retirement records.
The existing assembler, linker and packager check the unchanged setup and
literal tail bytes. `palette194.json` declares both complete image hashes.

Run the FC control before the00 discriminator. Both use the existing Python
integration top, actual CPU/PPU/Intel stores and supported preload. The native
probe uses an explicit named case with10120-event/140600-dot bounds; its default
integration case remains100 events. Core runs normally through HALT. Its
26-field retirement projection is checked at every event, including IF across
VBlank. A first retirement mismatch fails before pixel conclusions.

The [PPU contract](../../../wiki/src/rtl/ppu/MAS_ppu.md#digital-ports)
samples the old palette on a coincident write. DUT normal-frame x0 completes at
70908 and uses E4. Subsequent pixels use the new palette. Pinned Core's
`sm83_cpu.c` palette conflict advances to70906, stores `old|new`, advances one
dot, then stores new at70907; display synchronization renders earlier pending
actions before each store. Its normal x0 action is70905.

- E4→FC is monotonic, so both native writes are FC. Expected first normal pixels
  are0,3,3,3,0,3,3,3. This checks the common visible write boundary.
- E4→00 retains E4 during the intermediate native store. Core predicts x1 shade1
  before the final00 store; the DUT old-at-commit rule predicts x1 shade0. This
  predicted discrepancy could concern palette collision modeling rather than
  line cadence. A failure is diagnostic evidence, not a passed compatibility
  test or an automatic RTL defect.

`python-palette194-fc` and `python-palette194-00` build the original image and
separately execute pinned Core during preparation, then compare its records and
two complete visible frames in continuous Python/Questa execution. Each public
test command retains the existing600-second total wall bound. The pinned Core
checkout must be present at `workdir/research/sameboy/source`; all selected files
are hash-checked before compilation. No UART loading or physical proof is claimed.

The first FC attempt with the old adapter failed at retirement9446/dot66252:
its future snapshot reported IF1 while the DUT reported IF0. The corrected
profile starts with four pending initial-fetch cycles, then projects actual
post-`GB_run` state. It does not relabel that failed attempt. The FC retry must
compare every field and both complete frames. The00 discriminator and residual
PPU interpretation belong to #197; they are not completion criteria for the
scoped initial-fetch correction. Merged #102 evidence retains its producing
source identity.
