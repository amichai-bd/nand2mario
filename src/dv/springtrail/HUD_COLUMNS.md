# HUD/column acceptance

The [owning contract](../../../wiki/src/sw/springtrail/HUD_COLUMNS.md) defines
the coordinate, encoding and interrupt changes. This matrix separates host,
shared-routine, actual-game and fixed-renderer coverage.

## Instruction bounds

Counts include each named routine's RET, excluding its external CALL unless
stated. Fixed PublishColumn costs548 dots: setup28, fifteen32-dot row advances,
last16-dot data write, two4-dot high-byte carries, RET16. PublishColumns with
two caches costs1228; RestoreMapPair costs1320, or1368 on its final switch.
PublishHUD costs640 for both maps. ClearTitle is664, BeginMapRestore84,
ReadButtons208 including CALL, and unchanged PublishScene880 excluding CALL.

The longest title transition, from the VBlank request through publication,
costs at most4388 dots. Its additive terms are: entry/vector/ISR188 (including
24-dot interrupted instruction allowance), token dispatch72, JOYP208,
mode/new-level branches28+28, reset flag20, title branch28, ClearTitle688,
remember clear24, BeginMapRestore108, restoration dispatch32, pair1344,
jump12, published-camera32, HUD664, DI4, DMA904, EI4. The final restoration
switch adds48 but has no688-dot title erase, so is shorter. Use a4480-dot
runtime publication ceiling, within the4560-dot VBlank. No other enabled
interrupt can arise there; DMA masks IME without clearing IF.

For line15 beginning B, the qualified request is B-2. Include24 dots for an
interrupted instruction,20 entry,16 vector and16 AF save. The handler reaches
its polling loop before HBlank. Mode reads are32 dots apart. After the final
mode-read T4, the published-camera load and SCX commit take44 dots; LCDC read,
OR and object-enable commit add32. Latest enable is B+256+32+76 = B+364.
Check both split writes in B+280..B+384, after every line15 pixel and before
line16. Objects are disabled above the split, so line15 has no object stalls.
Return follows by28 dots. Do not substitute the diagnostic's HALT-only bound.

Visible preparation retains the prior25000-dot scene ceiling (four fewer
pieces), adds at most3000 for two worst-case16-run columns and512 for HUD,
and retains the20000-dot interaction ceiling. Including512 for interrupted
STAT service and256 dispatch gives49280, below65664 visible dots. Check actual
full OAM/cache/HUD readiness before the next VBlank; no timing value selects
an expected image or state.

## Finite groups

- Host encoding: all96 columns/1536 cells versus literal terrain; blanks,
  repeats, terminator, truncation, overflow, trailing bytes, invalid count/tile
  and index. Build rejects malformed fixture data before assembling it.
- Shared CPU routines: first/last column, all-blank gap, platform column,
  two-cache restoration, final switch and repeated restart; right88-to96
  ring31-to0, left96-to88, right607-to608 no-op, left608-to607, no-change.
  Compare complete caches, destination addresses/data, HUD in both maps,
  published camera and160-byte shadow/OAM, with bounded terminal/settled pause.
- Short actual-game complete harness: initial blank pixels through a fixed
  small prefix, input neutral, real final HALT, no-progress hold and trace END.
  Measure its whole cost before full acceptance, using existing Intel preload.
- Actual-game bounded composition: ordinary Start+Right in the first blank,
  prior TITLE frame, one UpdateGame, complete next-scene/cache/HUD preparation,
  following DMA and final settled HALT. Check all retained pixels, applied input,
  VBlank tokens/STAT order, no extra game update on STAT wake, exact split writes,
  no interrupt or stack access during DMA, and the4480 publication ceiling.
- Shared-renderer composed fixture: independently seeded95-to97 camera ring
  transition, one full normal frame including ground/entering column, fixed HUD
  and an object crossing y15/16 (player world x120/y12). Entering column32 is
  visible at screen x159. Use the actual linked publisher/column/HUD/ISR
  routines; fixture state setup is explicit, not a claim of natural reachability.
  A real accepted column-data or LYC mutation must fail the unchanged pixel/
  boundary checker. Select its earliest downstream witness and preserve failure.
- Packaging/preview: exact20 approved glyphs, unchanged terrain/courier and
 32 KiB layout, source-derived title/PLAY/HUD assembled SVG. No new art.
- Consumer reconciliation: prior composition game and courier full-scene
  expectations become historical or are updated explicitly; direct pose-only
  checks and movement/interaction rules remain qualified where unchanged.
  Existing pre-composition flow/endurance and old renderer guards stay pinned.
  Do not reinterpret historical acquisition/endurance ROMs or rerun their
  physical milestones.
- Required checks, final owning game/DV/composition links and independent
  current-head review, then normal merge. Physical release gates remain open.

Target120 seconds each and300 seconds aggregate; hard300 each. Measured first
four complete supervisors total454.797 seconds; the fault adds130.078 and the
renderer208.219, giving793.094 seconds for the six completed simulations.
The separate renderer setup failure is retained and excluded from that sum.
This exceeds the initial625-second forecast and ordinary aggregate target;
every completed simulation remains below its300-second hard limit. Freeze exact
fixture dots and supervisor commands before launch; use the measured short to
reduce redundant coverage or stop an infeasible run without weakening criteria.
No new framework, unchanged milestone replay or hardware execution is included.
