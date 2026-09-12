# Current HUD and column CPU proof

The [software contract](../../../wiki/src/sw/springtrail/HUD_COLUMNS.md) owns
publication. Row0 PublishHUD writes seven prepared values to both maps.
Row1 PublishProgress writes six prepared values to the map selected by LCDC
bit3. These are distinct rules. No product behavior changes in this proof.

## Finite operand matrix

Thirty ordinary operand cases use actual shared calls, independent column and
HUD literals, ordered accepted CPU writes and complete preserved current state.
Stage0 has96 columns and camera0..608; stages1/2 have80 columns and camera0..480.

| Group | Named operands | Required witness |
|---|---|---|
| Decode (6) | stage0 first0, last95, blank22, platform31; stage1/2 last79 | All16 ordered cache stores; stage-base selection, exact terminal cell and adjacent canaries |
| Block overlays (2) | stage0 used item column38; broken brick column52 | Current decoder's row10/11 override after terrain stores, without executing or replacing block-interaction proof |
| Camera (8) | 80 to88;88 to96;96 to88;607 to608;608 to607;96 unchanged; stage2 479 to480 and480 to479 | Entering31/ring31,32/ring0, left11, valid right-clamp no decode, left75, no-change; current shorter-stage clamp and left margin |
| Restoration (3) | PAUSED pair0; final pair30; two restarts after partial14 | Game state remains paused; all32 final pair writes precede LCDC map switch; restart discards prior partial counter/history each time |
| Dirty publication (1) | dirty pair38 with a simultaneous camera boundary | Both caches publish first, dirty flag clears, OldCameraTile remains for the deferred entering column; next ordinary prepare publishes that column |
| HUD (7) | TITLE, PLAY, RETRY, PAUSED, WON, TIMEUP, OVER; scores spanning0..4 | Seven cache writes, then exactly seven row0 stores in9800 and seven in9C00; blank padding is explicit |
| Progress selection (2) | LCDC bit3 clear/set, lives09/time387/stage2 | Six cache values at row1 columns2,3,13,14,15,18 go only to the selected map; static icon cells and the other map remain unchanged |
| Combined publication (1) | current entity scene, camera88 to96, current HUD/progress | Actual PrepareScene/PrepareMap/PrepareHUD/PrepareProgress then publication; full160 ordered shadow bytes,160 actual DMA bytes, full OAM readback, caches and preserved123-byte world state |

The short case is PAUSED pair0: it exercises preparation, publication, state
preservation and complete transport/terminal handling. It is not an empty
startup sample. Full groups retain every named case; grouping follows measured
short throughput and source-derived setup/call/report counts before launch.

Literal anchors independent of assembly: stage0 columns0/95 are fourteen zero
bytes then11,11; column22 is sixteen zero bytes; column31 has tile11 at cache
indices8,14,15. TITLE score0 is90,83,90,84,82,0,74; TIMEUP score0 is
90,83,145,82,91,87,74; OVER score0 is86,146,82,88,0,0,74. Other modes and
all column records are checked against the existing independent original
terrain/glyph rules before source assembly. No expected output is injected
into the fixture ROM or learned from DUT writes.

## Observation and preservation

Reuse the current bounded UART runner and existing assembler/linker/column
validator. The fixture seeds ordinary operands through CPU stores before each
marker, calls unchanged game routines and reports after return. The checker
compares all accepted cache/VRAM/metadata writes in order, rejecting extra,
missing and transiently wrong stores. It verifies complete current world
fields, PublishedCamera and adjacent cache/shadow canaries; only declared
routine scratch and requested publisher metadata may change. Restore LCDC
checks retain non-map bits. No frame IRQ or whole visible-time deadline is
claimed by a fixture holding LCD off.

One actual accepted-write fault corrupts the first published column byte after
its source cache has passed. The unchanged checker must fail at that ordered
VRAM write. Keep the mutation marker, downstream failure and raw test status.
Positive and negative cases both use the existing completion protocol: bounded
terminal marker, real settled HALT/hold and END; missing report/END, late writes
and timeout are host negative tests.

## Evidence boundaries and budgets

Current entity and compatibility cases already prove world evolution and
supported routine behavior; they do not replace the publication matrix above.
The current renderer's95-to97 pixel proof is retained as separate evidence.
Historical hud_program/hud_unit_check guards and retired execution definitions
remain unchanged. No historical binary identity is relabelled current.

Qualify each new ROM's shared section bytes against a fresh current game build,
validate target input closure and run focused host literal/checker negatives
before the complete short. Forecast: short40s, five full groups around120s
each, fault40s, approximately680s aggregate; these are planning estimates,
not measured limits. Every new target retains a300-second whole-operation cap.
Freeze exact per-group dot/case limits after source assembly and use the short
measurement before any full run; do not launch a predictably over-budget run.
No FPGA or hardware execution is needed.

The current [entity timing proof](ENTITIES.md) owns the reachable visible bound
and retained4412/4480 publication bound. Shared PublishScene remains880 dots
excluding its caller's CALL and transfers160 bytes. This CPU operand proof
must not revive historical25000-dot scene or dual-map progression assumptions.
Required host/wiki/catalogue checks and independent current-head review close
the proof; there is no new framework or gameplay feature.
