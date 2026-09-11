# Movement and animation acceptance

The [owning motion contract](../../../wiki/src/sw/springtrail/MOVEMENT.md)
separates source-confirmed local rules from approved original choices. The pure
`motion_reference.py` and its literal host cases were frozen before product
movement changed. Current `motion_game_reference.py` checks original24-byte
player/motion state plus existing game fields, complete prepared shadow pages,
all98 tile loads, actual IRQ/JOYP/publication order and retained complete pixels.
The actual CPU fixture also executes the existing UpdateGame mode dispatcher.

## Current instruction and execution bounds

Current startup LCD commit is139388 dots, derived from accepted HUD startup
136560 plus280 for initializing ten motion bytes,2628 for CALL plus the64-byte
approved skid copy, minus96 for the shorter title pose selector, plus16 for the
new small-skid size branch. This is an instruction-derived anchor, not a value
chosen from DUT output. `python-mgs` exercises that full startup through at least
160 blank pixels, normal host HALT, settled hold and counted trace END. Its
90ms simulation watchdog and existing300-second whole supervisor remain active.

VBlank code is unchanged: retain the [HUD publication4388 bound/4480 ceiling](HUD_COLUMNS.md#instruction-bounds).
Current shared CPU ceilings are7960 dots for StepPlayer including marker/call,
892 for InitPlayer and18000 for UpdateGame. The static tally counts all branch
bodies, then adds the bounded repeated work: at most three horizontal rows,
two vertical/support columns and four item iterations. StepPlayer is
7320+2*152+116+120+100=7960. UpdateGame is
2900+7860+892+5*600+23*84+3*432+120=18000. These conservative sums intentionally
include mutually exclusive branches. The fixture enforces8000/20000 call caps;
40 calls (32 step, one init, seven actual mode dispatches),1700 setup per call
and1000 tail give473000 dots, below its500000 guard. Short/full simulation
watchdogs are35/150ms; neither this dot ceiling nor static proof establishes
full-run wall feasibility. Measure the complete first-Right short before that
decision. Old4200 arithmetic below cannot qualify current motion.

Visible preparation retains the49280 ceiling:25000 scene,3000 columns,512 HUD,
20000 game update,512 STAT allowance and256 dispatch. The new UpdateGame bound
is18000. The longest current pose selector is168 dots, shorter than the prior
accepted selector's over200-dot moving path; ComposeCourier adds only16 dots
to existing pose paths. Skid keeps four pieces and skips the large-Y adjustment.
Unchanged piece loops and full tail clearing therefore remain within the broad
25000 scene allowance. The current checker enforces the final full-shadow
ready deadline, not only the first active entries.

The first game update expects
X25,Y112,VX1,VY0, counter1,directionRight,speed0,phase1,animation2,STAND; it prepares
that state after the first VBlank and publishes it at the next. The retained
normal output frame is the prior prepared TITLE; independent rendered motion
states are covered separately, not claimed as this run's visible gameplay.

## Remaining acceptance matrix

All rows remain incomplete until implementation and independently reviewed
producing evidence exist. Host expectations must be frozen before motion code;
exact instruction/dot bounds must be frozen before each licensed run.

| Group | Required result | Planned execution |
| --- | --- | --- |
| Contract/model | Literal per-update walk/run/coast/reverse/opposite inputs; jump hold/release/apex/fall, steering, walls/ceiling/landing; phase/counter wrap; mode pause/resume/restart and pose/facing precedence | Independent pure Python cases, no DUT-fed expectations |
| Shared CPU | Actual InitPlayer/StepPlayer and UpdateGame bytes; every expected state byte after each scripted call, completion and settled halt | Complete short harness, then finite full case set |
| Game schedule | Actual game boot, sampled Start+Right, prior prepared title then first moved scene; complete pixels/state/input, one update/token and unchanged HUD/STAT/DMA ownership | Existing continuous Python/Intel preload, short completion then affected full game |
| Rendered states | Approved WALK cycle and skid mappings, both facings, exact tile bytes and unchanged HUD masking; actual shared composer consumes seeded original operands | Host all-state pixels plus one bounded complete renderer fixture |
| Fault | A real movement consumer mutation rejected at the first differing state by the unchanged positive checker; retain failed receipt | Shortest useful CPU case, after positive proof |
| Consumer qualification | Historical fixed-physics/current-ROM consumers either gain independently current expectations or reject incompatible current ROM/source before use | Focused host guards; no relabelled old full-route evidence |
| Delivery | Owning SW/DV/asset links and previews, original32KiB reproducible image, affected host checks, required CI and current-head independent review | No new art approval or full hardware milestone replay |

The fixed renderer seeds WALK2 facing right at world X120,Y12 and camera97,
with prior published camera95. After the shared PrepareScene writes all160
bytes, a second actual ComposeCourier writes16 approved SKID-left bytes at
C140..C14F for screen X60,Y32. The checker requires both stages in order,
the remaining80 zero tail, both complete160-byte DMA transfers, all98 loaded
tiles and every pixel of the displayed frame. The entering column32 is visible
at X159. No gameplay update or extra feature is inferred from these operands.
`python-mr` uses the complete two-VBlank/terminal/settled-HALT harness, with
LCD-off startup bounded by160000 dots and total progress by300000 dots.

`python-mux` changes the actual first rightward VX store from16 to0 after the
first CPU call marker. The public write trace remains unchanged; the unchanged
positive checker must reject the consumed wrong X/state, with the mutation
marker and failed receipt retained. Host artifact corruption is not this fault.

Historical HUD fixtures pin the prior movement/courier sources; the old HUD
game pins ROMadbef6b0. Earlier fixed-physics CPU units and physical route drivers
also reject incompatible current sources/ROMs before assembly or traffic.
Literal world/terrain helpers remain usable; old trajectory evidence is not
relabelled. Current replacements are the motion CPU/game/renderer targets above.

## Measured durations

Measured whole-run walls: `python-mus`26 seconds, `python-mut`173,
`python-mgs`164 and `python-mux`29, a392-second declared aggregate across the
four completed targets. `python-mgs` reached39.081802 ms of simulated time in
156.19 simulator seconds, a250223 ns-per-second rate.

`python-mgu` and `python-mr` exhaust the300-second whole-run cap: both stop at
the288-second execution limit with12 seconds reserved for cleanup, once with a
cold compile and once with the compile cached. Neither overrun is a checker or
DUT defect; no partial result is claimed for them. The per-target
`timeout_seconds` schema also refuses any value above300, so no configuration
raises either limit. At the measured rate the full game's roughly256500 dots
need about244 simulator seconds and the renderer's300000-dot bound about286,
which leaves neither room for setup, preload and cleanup inside300. Both
fixtures therefore need a smaller frozen case bound before they can qualify;
the earlier240/220-second planning forecast understated them.

Freeze smaller actual case bounds where feasible and report measured times; no
extra duration or coverage quota is introduced. Unchanged
hardware/transport/STAT baseline evidence is reused only with explicit input and
behavior qualification.

## Historical fixed-physics proof

Everything below records the earlier fixed-physics ROM/routines. Its numeric
contracts and85-step evidence are historical; current changed images must not
consume these old expectations. Literal terrain helpers remain unchanged.


The owning [verification matrix](../../../wiki/src/dv/springtrail/SPEC.md#movement-matrix)
separates the actual CPU routine proof, short composed game and whole-game FPGA
scrolling. The [PR270 evidence](https://github.com/amichai-bd/nand2mario/pull/270)
records the completed scoped proofs.

## CPU unit checkpoint

`python-st-unit` loads an original software unit ROM through the existing Intel
preload, actual CRC scan and Client adoption. The unit and game link the same
movement, renderer and literal world at addresses 2000,2800,1400 hexadecimal.
Both also link the same page-aligned collision view at4000:18 rows of256 bytes,
with the first96 cells matching the world's solid tiles and160 zero padding
bytes. Exhaustively compare this view to the independent literal terrain.
Their complete section bytes must be identical before execution. There are no
expected results in the unit ROM: only ordinary WRAM operands and input masks.

The ROM executes 85 steps: walk/run/opposed direction, complete held-jump arc,
release/rejump, gap fall and hold, side/head/landing contacts, fractional contact,
both horizontal bounds, camera anchor/tile boundary/256-pixel wrap/right clamp.
The added airborne camera crossing is the reachable fourth jump update and
exercises three horizontal rows plus two vertical columns on one entering-column
frame. The original84 case expectations remain unchanged.
Each step calls the actual movement routine and emits the resulting 14 state
bytes through ordinary WRAM writes. Boundary cases also call the actual
renderer. Compare all emitted bytes and selected OAM/SCX/new-column writes to
the independent integer model and literal world; input history selects expected
states, never observed DUT values. The unit loop preserves actual state between
successive steps within each group.

Normal software marker writes bracket the routines. Require every measured
movement/render call to finish within 4200 dots, conservatively including call
and marker overhead, so VBlank writes can complete before the next scanline.
Reserve another268 dots for the ordinary input/state/return-to-HALT path and64
for wake alignment: even counting the marker overhead twice,4200+268+64 remains
below4560. The title-clear path is checked separately in the composed game.
This measures routine execution, not continuous full-game frame cadence.

The existing optional passive trace retains every public write/retirement.
Reject unknown/truncated lines, wrong/missing/reordered report bytes, incorrect
markers, extra input/pixels and missing terminal/END records. Require the actual
terminal marker, normal host HALT, no reset/fault and bounded cleanup. Expected
results are frozen in `movement_reference.py` and `unit_cases.py`; the original
driver is `src/sw/springtrail/unit.asm`.

Declare the existing 300-second whole-process cap, 120-second target and
300000-dot unit progress bound. Host/model and section-identity checks plus
independent source review precede actual CPU execution. The
[PR270 evidence](https://github.com/amichai-bd/nand2mario/pull/270) records measured
durations, retained failures and the selected aggregate; no budget exception is implied.

## Short composed game

The original complete game initializes normally through Intel preload and the
actual CRC scan/adoption. The software enables LCDC97 at independently derived
dot48528: the initialization, 160-byte OAM clear, tile/map copies and initial
renderer all execute on the actual CPU. The initial renderer costs476 routine
dots; its CALL and the preceding setup place the LCD write at that fixed dot.

Drive one ordinary UART INPUT129 (Start plus Right) at dot178528..180528,
before the second VBlank at184416. This clears the22 title tiles and performs
one walk update, yielding player(25,112), camera0, OAM(128,33,12,0) and SCX0.
The next complete world image must show the courier one pixel to the right.
The three complete output frames are startup white, title and that first world:
23040 pixels each, literal CRC32 B15161F6,4E8A1268,B3387AE4. The literal original
artwork and independent physics select these images; no DUT state selects them.

Check every pixel's shade, coordinate, frame-start/eligibility flags and epoch2,
with strictly increasing dot timestamps. Frame k, row y must occur within
`[48528 + k*70224 + y*456, 48528 + k*70224 + (y+1)*456)`.
This allows real object-fetch stalls within the correct line. It does not claim
an exact per-pixel object timing oracle. Check the actual ordered title clears,
OAM/SCX writes and mode transition inside the normal VBlank interval. Retain all
26-field retirement records and check epoch/sequence/dot continuity; no full
register oracle is claimed. Request normal HALT at254436 and require actual
pause within2000 dots, complete trace trailer, all69120 pixels and no fault/reset.

The existing actual output-shade fault remains checked by the unchanged pixel
oracle. Its first nonwhite forced title pixel must fail; a setup failure is not
fault evidence. Both simulations retain the300-second total cap and120-second
target. Record the selected unit, game and fault durations together against the
300-second ordinary aggregate target. Each test still obeys its 300-second hard
cap; a target miss is not a budget allowance or coverage waiver.
