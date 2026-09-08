# Independent SameBoy adapter

This adapter for [#102](https://github.com/amichai-bd/nand2mario/issues/102)
builds the pinned reference and compares its retirement records and visible
framebuffer pixels with the original integration program's DUT observations.
A successful native probe means execution completed; the separate comparison
must also pass.

## Run

Use the original integration image from the repository's software pipeline:

```powershell
python -X utf8 -B src/dv/integration/image.py
python -X utf8 -B src/dv/sameboy/probe.py --source workdir/research/sameboy/source --rom workdir/builds/integration140-image/program.gb --output workdir/builds/sameboy-probe
```

The source checkout must match `sources.json`: SameBoy Core at
`213a12ce93d66b105a113debd9396306066a7cfc`. The selected inputs use the Expat
license; each attempt retains the upstream `LICENSE`. No iOS or HexFiend source
is selected. The original image must have the exact recorded length and hash
before any Core load. Core's loader otherwise rounds and pads short files.

The current Windows host uses Ubuntu-24.04 WSL, Clang, Make, binutils and patch.
The runner records commands, tool versions/hashes, source hashes, generated
profile header, observer patch and executable. It builds the upstream static
object-library target directly: distribution-header generation requires `cppp`
and is not part of this build. Each output directory is a fresh attempt.

## Direct entry

`profile.c` accepts a fresh `GB_init`, not a warm-reset object. Generated values
come from [the shared interface configuration](../../../cfg/interfaces.json).
The initializer keeps Core model bookkeeping and changes its power-on defaults
to [dmg-direct-v1](../../../wiki/src/rtl/interfaces/MAS_interfaces.md#direct-entry-and-reset).

| State | Implementation and pinned source basis |
|---|---|
| CPU, ROM | Exact original ROM-only image; boot mapping disabled; generated register/control values and no pending cycle. `gb.c:167` clears the whole fresh object; `gb.c:1683` clears saved reset groups. |
| RAM | Fill WRAM, VRAM, HRAM, OAM and I/O-backed wave RAM with generated zero. Echo uses Core's existing WRAM alias. |
| I/O | Clear writable bytes. JOYP stores select30, released low bits and fixed high bits (`FF`). SC stores its read-only bits (`7E`); other masks remain Core-owned (`memory.c:623`). |
| Timer, serial | Reset clears timer/reload/edge state; explicitly replace reset divider8 with0 through `GB_set_internal_div_counter`. Preserve the inactive serial first-bit mask80. |
| DMA, audio | Reset clears progress/channel state. Preserve Core's inactive DMA destinationA1, no-OAM-rowFF and APU time-unit flag; these encode idle/model representation, not nonzero activity. |
| PPU | Reset clears timing, FIFO, window/object and frame state. `GB_lcd_off` establishes disabled access state; reset coincidence and IRQ histories remain zero, as specified by MAS_ppu's reset/off rule. |
| Epoch/input | Fresh Core has released keys and zero clocks. No host loader is claimed. The eventual ABI adapter must explicitly represent the integration's epoch2 metadata and applied input schedule. |

## Raw observation boundary

`observe.patch` adds original read-only callbacks after the final DMG framebuffer
assignment in `display.c:795`, before the LCD x increment. It does not change
Core timing, color selection or memory effects. Raw RGB, x/y, native ticks and
pending display ticks remain visible. The native startup framebuffer can contain
colors before Core's whole-frame blanking; these raw writes are not yet the
required visible startup source-frame stream.

CPU samples follow `GB_run`; memory callbacks retain every raw read
and write, including LCDC split writes. No PC resynchronization, field masking,
pixel substitution occurs.

`retirement.py` projects only this original program. It retains each native
post-event architectural sample and obtains its completed-dot identity from the
next actual opcode fetch plus that fetch's four pending T-cycles. The initial
fetch produces no preceding event. The IRQ discarded fetch closes the previous
instruction, the handler fetch closes interrupt entry, and HALT's explicit dummy
fetch closes HALT. These three call sites are observed without changing Core
execution. A read-only end-of-advance hook captures IE/IF and verifies released
keys at the actual four-dot fetch completion after Core peripheral service. An
overshot boundary fails instead of sampling late. Architectural registers remain
the completed event's saved state. The declared mapping follows MAS_cpu150–171; it is not applied to
peripheral writes or pixels. Actual operand bytes come from recorded reads, with
strict sequential address and supported-instruction-size checks. Closing snapshots are separate from native instruction-return samples; duplicate,
missing, unknown, orphan and reordered observations fail. Generated ABI packing
validates the complete record. General instructions remain outside this selected
original-program decoder.

Epoch2 represents LOAD_BEGIN then LOAD_END, each entering COMMAND_RESET in
the delivered endpoint, as metadata; the
reference does not claim to execute the UART loader. Version1 and the released
input schedule are the approved fixed ABI for this probe. All26 fields compare
exactly against the separate literal diagnostic. That diagnostic is not DUT
equivalence. Raw samples remain separate from projected records.

Normal `GB_run` continues HALT and all peripherals. Observer-enabled builds
disable only the line batching optimization, selecting Core's existing cycle
path. `--baseline` builds pristine Core for comparison of native CPU events,
frame publication and complete visible framebuffers. The actual vblank callback
records the authoritative frame after Core's startup white fill. Raw per-pixel
assignments stay separate; they do not substitute for those visible values.

The pending display budget is measured in8MHz ticks. The source state machine
acts at `(native_ticks - pending_display_ticks)/2`, before its following sleep
consumes the dot. This action identity is retained without fitting offsets to
DUT data. `compare_diagnostic.py` compares all retirement fields and visible
shades with retained DUT CSVs and reports the first unresolved timing difference;
historical DUT traces are not automatically current-head acceptance.

## Acceptance boundary

Run the existing `python-integration` target with Intel memory preload, then:

```powershell
python -X utf8 -B src/dv/sameboy/compare_acceptance.py workdir/builds/sameboy-probe/observations.log <dut-attempt-directory> workdir/builds/sameboy-probe/acceptance.json
python -X utf8 -B -m unittest discover -s tools/n2m/tests -p 'test_sameboy_*.py' -q
```

The comparison requires all 69 retirement records, all 26 ABI fields including
completed-dot identity, and both complete ordered source frames (46,080 pixels).
The DUT test retains its own source-pixel timing, progress and completion checks.
Preload proves execution after initialization; it does not repeat UART loading.
Corrupt fields or pixels, missing observations and reordered observations fail
at the first expected/actual context without resynchronization.

The [baseline contract](../../../wiki/src/dv/baseline/SPEC.md#independent-emulator-and-retirement-traces)
requires exact retirement fields and ordered visible source pixels. It does not
require Core's internal framebuffer-action timestamps to equal DUT source-event
timestamps. `compare_diagnostic.py` separately retains that unresolved difference
and its nonzero exit. [#194](https://github.com/amichai-bd/nand2mario/issues/194)
tracks it; it is not a #102 prerequisite or a hardware timing claim.

The remaining delivery checks are current DUT runtime/comparison evidence,
independent current-head review, and required repository checks. Pinned native
baseline/observer equivalence and the reviewed direct-entry/hook mapping remain
required evidence, with their original producing fingerprints retained.
