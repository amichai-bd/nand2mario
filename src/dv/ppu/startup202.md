# Startup OAM boundary witness

Issue #202 remains an investigation. These original programs test the legal
CPU-visible first-line OAM boundary independently of internal pixel timestamps.
The correction blocks only early OAM reads; writes and source timing are unchanged.
Early VRAM reads belong to #204; late OAM writes/corruption remain #208,
and raw startup cadence remains #205. No
hardware-revision claim follows from a model disagreement.

The [pinned primary read table](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/ppu/lcdon_timing-GS.s)
requires FF after LCDC81,111 NOPs,LD A,(DE=FE00). The
[paired write table](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/acceptance/ppu/lcdon_write_timing-GS.s)
accepts81 at the same placement. These sources identify DMG/MGB/SGB/SGB2,
not a particular DMG CPU revision. The expectation is independently specified;
Core is not treated as silicon.

Both original images initialize OAM00 while LCD is off, set DE=FE00 and enable
LCDC81 with SCX0, IE0 and object rendering disabled. The accepted enable write
is dot80. The tested access is dot532 (enable+452); its retirement is dot536.
The read expects A=FF. The write control subsequently disables LCD and reads
back81 at dot556. Read/write HALT retirements are540/564, with122/125 complete
26-field retirement records. Literal opcode bytes and whole-image hashes are
checked before Intel initialization. The oracle never uses actual DUT values.

`python-startup202-read` and `python-startup202-write` reuse the existing
continuous Python/public observations and Intel preload/adoption. Metadata
requests finish before INPUT/RUN at8.001/8.201ms; no historical150ms idle is
needed. A10us progress watcher and20ms simulated deadline bound the short
complete path; the shared600-second total wall cap remains. Raw bus/retirement
samples are retained before assertions. This is preload execution, not UART
ROM loading, physical evidence, or full#88 acceptance.

First run the read candidate and retain any first mismatch without masking or
resynchronization. A mismatch may concern read/write access sampling rather
than the454/455 startup pixel interval. The paired control, defect sensitivity,
independent review and any required product correction remain contingent on
that diagnosis; no passing status or resolved#202 is claimed by adding targets.

## Scoped correction checks

`ppu-oam-read` checks the unchanged write allowance and distinct read allowance
at448/452/456 and904/908/912, startup8/76/80, VBlank entry and next-frame
entry. A held pre-T4 state proves pause cannot bypass the read block; DMA still
denies both directions and core reset clears the early condition. The actual
read output is forced allowed in `ppu-oam-read-corrupt`, which must fail the
unchanged0/1 versus1/1 check. No new write or mixed-port collision is enabled.
The two original CPU targets then check the corrected architectural read and
unchanged write/readback. All raw earlier failures remain failed evidence.
