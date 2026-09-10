# Movement and animation research contract

This is the approved movement contract for [#301](https://github.com/amichai-bd/nand2mario/issues/301).
The current [game behavior](SPEC.md) remains implemented. The table below records
confirmed routine behavior, separately from the approved original choices below.
It does not claim complete per-frame SML1 equivalence; implementation is open.

## Reference boundary

Use kaspermeerts/supermarioland revision
`618d00ed6c330928e106719533c6e294ae5d5726`, [bank0][bank0] and [bank3][bank3].
No commercial code, data tables, assets or ROM are vendored or rebuilt.
Routine names below locate external evidence; original implementation state and
algorithms need not use the reference addresses or instruction sequences.

The normal `GameState_00` body remains an `INCBIN` for 0627..06BB. Consequently,
local branch behavior does not prove normal call order, call frequency, player
jump-profile binding, or the frame of a displayed pose. The selected source's
own README confirms that undisassembled sections require an external ROM.
Published forks retain this gap. An unrelated game's physics is not evidence.

## Confirmed local behavior

An invocation in this table means one call of the named routine, not an assumed
normal update. Inputs are logical buttons, independent of the reference's bit layout.

| Area | Confirmed rule | Evidence and uncertainty resolution |
| --- | --- | --- |
| Direction priority | The horizontal routine tests Right before Left. Both held select Right unless an earlier reversal hold returns. | `Call_1D26`; replaces the misleading assumption that opposite directions cancel in the reference. |
| Start and coast | From a grounded start, a counter rises toward 6 on directed movement; jump setup can instead set 48 and arithmetic remains modulo256. At 6, class0 becomes class2. No-direction input clears the speed class, decreases a nonzero counter and follows the stored direction for that invocation. | `Call_1D26`; the counter is a state/timer, not a fixed-point velocity. |
| Horizontal displacement | Each displacement evaluation flips a one-bit phase. Class0 gives alternating 0/1 pixel, class2 gives 1 each, class4 gives alternating 1/2. | `Call_1D26.call_1EB4`; averages are 0.5/1/1.5 pixels per evaluation, not complete initial sequences. Initial phase and caller order remain unresolved. |
| Reverse | Opposite intent enters a reversal state with counter8 and no displacement. Eight subsequent calls decrement it without motion; the next clears reversal without motion. New direction can be accepted on the following call. | `Call_1D26`; ten stationary invocations including entry/clear, not an acceleration ramp. Airborne reversal also holds horizontal motion. |
| Facing | An accepted direction changes facing before the side-collision test. Reversal holds retain the old facing. | `Call_1D26`; collision can therefore block motion while facing changes. |
| Walk cycle | Grounded nonvehicle animation advances when the movement counter is divisible by4, wrapping WALK3 to WALK1. Right increments that counter and Left decrements it, modulo256. | `Call_16F5`; instruction mask3 establishes four, despite the comment saying three. The faster branch compares speed class with35, not normal run class4. No faster run cycle is established. |
| Composition order | The animation routine composes the existing pose before advancing the stored pose and invoking horizontal movement. | `Call_16F5` then `Call_1736`; bank3 `Call_4823` is pose-table composition, not a cadence update. Normal dispatcher order is still absent. |
| Pose precedence | Grounded stop selects STAND and resets animation counter1. Grounded reversal selects skid; airborne reversal does not replace the airborne pose. Exact crouch is excluded from walk advancement. | `Call_1D26` and `Call_16F5`; power/crouch integration remains with #302. |
| Run selection | With B held and jump state0, the input routine selects class2 below counter3, otherwise class4. B release demotes class4 to class2. A new B edge clears counter6 before projectile eligibility is checked. | bank3 `.jmp_4975`, `.jmp_498B`, `.jmp_49FD`; ground-only acceleration and B-edge effect are explicit, but relation to the horizontal invocation is not. |
| Jump eligibility | A must be held and newly pressed; jump state0 and grounded are required. Accepted jump clears grounded, sets ascent and selects JUMP except exact crouch. | bank3 `.jmp_49BF`; held A cannot create another jump by itself. |
| Jump setup | Non-run jump sets curve index2 and class2; run jump preserves its existing index. Normal noncrouch jump sets the horizontal counter48. | bank3 `.jmp_49BF`; the index reset before this call is not established by the missing dispatcher. |
| Release | Releasing A during ascent with index below15 saves index minus1 and sets index15. A separate restoration helper can restore a nonzero saved index when the current index is below15. | bank3 `Jmp_4966` and `.jmp_48FC`; which normal frame calls restoration is unresolved. |
| Vertical evaluator | A generic evaluator consumes a supplied displacement profile forward during ascent and backward during descent; its sentinel changes direction. | bank3 `Call_490D`; `Data_216D` is explicitly used for a nonplayer jump in bank0. The missing normal caller prevents claiming that this is the player profile. |

Routine-boundary examples fixed independently of new DUT output:

- Starting with phase0, three class0 evaluations displace 1,0,1 pixels; three
  class4 evaluations displace 2,1,2. Starting with phase1 reverses each parity.
- Grounded WALK1/counter4 composes WALK1 and stores WALK2; grounded
  WALK3/counter8 composes WALK3 and stores WALK1. Airborne WALK1/counter4
  composes and retains WALK1. These are local examples, not framebuffer timing.
- Starting from rightward state, Left initiates reversal; facing remains right
  through the ten stationary invocations. The next accepted Left faces left,
  including when its side test blocks displacement.

## Reference limits resolved by original choices

The existing [HUD/column schedule](HUD_COLUMNS.md) already fixes one sampled
input and one game update per frame with one prepared-scene display delay. It
also fixes original world coordinates and approved art anchors. These remain.
The following cannot currently be labelled source-confirmed SML1 frame behavior:

1. Input/jump selection before or after horizontal/animation work. This changes
   the first run/stop/reversal/jump sample and which pose is prepared that update.
2. Vertical evaluation before or after landing/head/side collision, including
   held-A release restoration. This changes first displacement, apex and landing.
3. Initial/restart phase, animation counter and vertical profile/index binding.
   This changes the exact first walk/run displacement and full jump trajectory.
4. The original 8x16 collision box and 16x16/16x24 artwork remain distinct.
   Reference side/head sample offsets alone do not establish a replacement box.

The approved choices below resolve these missing seams for original implementation.
The reference table alone does not establish complete reference equivalence.

## Approved original resolution

On 2026-09-10, the user approved best-effort reference alignment despite incomplete
confirmation of original movement. This selects the independently reviewed
original choices below; it does not establish unverified SML1 equivalence. The existing mode/input-edge handling,
one update per frame and prepared-scene display delay remain unchanged.

- Each PLAY update selects run/jump from prior state, decides the animation
  advance, performs horizontal movement and collision, performs vertical
  movement and collision, resolves interactions, then prepares the resulting
  scene. Preparing the resulting pose is an original ordering choice; the local
  reference compositor runs before its stored-pose advance.
- Initialization and restart set horizontal phase 0, animation counter 1, facing
  right, movement counter 0, speed class 0, jump index 0 and saved release index 0.
  Pause freezes movement/animation state while synchronizing input edges.
- Bind the source-described generic displacement profile to the original player:
  ascent indices 0..1 use 4 pixels, 2..3 use 3, 4..12 use 2, 13..19 use 1, and 20..25 use
  0,1,0,1,0,0; then descend in reverse. Implement the behavior originally, without
  copying a commercial table or routine. Non-run starts at index 2; run starts at
  index 0. An accepted jump clears the saved release index.
- Before vertical evaluation, an ascending player with A released and index below
  15 saves index minus 1 and sets index 15. For index 0, save 0 instead of wrapping
  to 255: this is an original underflow rule. Then, on either ascent or descent,
  restore and clear the saved index only when saved is nonzero and current index
  is below 15. A saved 0 means no restoration. These operations occur once each,
  in that order, per update; restoration does not change ascent/descent state.
- Ascent subtracts the current profile value and increments the index. At index
  26, change to descent, apply index 25's downward value in that same update,
  then store index 24. Descent adds the current value and decrements the index.
  After index 0 is consumed, mark descent exhausted; the following update and
  later updates fall 4 pixels each. Walking off support enters this same 4-pixel
  fall immediately and selects JUMP. There is no extra apex or exhaustion idle update.
- A ceiling collision clamps the upward candidate to the contact boundary,
  changes to descent at index 0 and clears the saved index. Do not also move down
  that update; the next update consumes descent index 0. Landing clamps to the
  support boundary, sets grounded and clears jump state and both indices.
- Horizontal box collision/clamping preserves the evaluated counter, phase and
  animation progression and accepted facing; it does not roll them back. This
  original post-movement collision order differs from the reference side-test
  early return. A contact/clamp stores VelocityX0 even for a partial snap. With
  no input, a nonzero counter and no stored direction, decrement once and remain
  horizontally still; do not reproduce an intra-call counter-draining loop. Keep the original 8x16 collision box, world coordinates and approved art anchors.
  No new art, feature family, clock change or additional display delay is included.

The generic evaluator/profile and player helper's non-run index 2/release cut 15
are source-described local facts. Player profile binding, run index 0 reset,
once-per-update dispatch, pose preparation order, underflow handling, ceiling
transition, landing reset and sustained fall are approved original choices, not
confirmed Mario behavior. The immediate sentinel descent follows the generic
evaluator; its normal-player timing remains an original binding. Exact cases
must retain that distinction when the contract is frozen before implementation.

The issue retains all movement, collision, rendered-state, fault, asset and budget
requirements. Its criteria distinguish confirmed local rules from these original
choices; existing physical-release gates remain separate.

## Original state and integration boundary

`InitPlayer` and `StepPlayer` remain the shared entry points. Existing positions,
velocities and collision operands retain their Q4 representation and addresses.
New gameplay state occupies C060..C069 in this order:

| Byte | Meaning and reset |
| --- | --- |
| C060 | Movement counter, 0; unsigned modulo256 arithmetic |
| C061 | Direction: 0 none, 1 right, 2 left, 3 reversal; reset0 |
| C062 | Speed class: 0,2,4; reset0 |
| C063 | Alternating displacement phase, reset0 |
| C064 | Animation counter, reset1; unsigned modulo256 arithmetic |
| C065 | Motion pose: 0 stand,1..3 walk,4 jump,5 skid; reset0 |
| C066 | Jump state: 0 supported,1 ascent,2 profile descent,3 terminal fall; reset0 |
| C067 | Current profile index, reset0 |
| C068 | Saved release index, reset0 |
| C069 | Facing: 0 right or20 hexadecimal left; reset0 |

Scene composition reads motion pose/facing and retains the existing title/retry
mode overrides. It does not advance motion state. Logical skid uses the approved
small-skid core pose; no power/large-state mechanics are introduced. Existing
courier poses and core editable sources remain authoritative. The skid's four
core tiles16..19 stay at ROM6100..613F and are copied at LCD-off startup to
VRAM tiles94..97 (85E0..861F). Courier pose12 uses these four pieces; existing
pose indices0..11 retain their mappings. This allocation needs no extra ROM atlas;
no other approved core state is added to this feature.

Movement remains in the existing ROM2000..27FF allocation. New state does not
alias scene/IRQ/cache operands. All motion and animation work runs in visible
preparation; the existing4480-dot publication deadline remains required.

Initial literal diagnostic anchors, before any DUT implementation:

- From reset, seven Right updates produce X pixels25,25,26,26,27,27,28,
  horizontal counters1,2,3,4,5,6,6 and poses0,0,0,1,1,1,1.
- From reset, seven Right+B updates produce X pixels25,26,27,28,30,31,33;
  initial phase0 is flipped once for each evaluated displacement.
- A grounded reversal entered from rightward state holds X/facing for entry,
  eight countdown calls and one clear call. The next accepted Left changes
  facing even at a blocking wall.
- A fresh non-run jump consumes profile index2 first:3 pixels upward. A fresh
  run jump consumes index0 first:4 pixels upward. Landing and ceiling follow
  the exact state transitions above, rather than an observed trajectory.

## Finite implementation/proof boundary

Before implementation, freeze literal per-update cases for walk/run/coast/reversal,
opposite directions, jump press/hold/release and airborne steering, landing,
wall/ceiling contact, facing/pose precedence, pause and full restart. Keep
independent expected states separate from DUT observations. Use the shared
actual SM83 routines in a short complete CPU harness before its bounded full
case, then the smallest affected composed pixel/input/publication proof and a
meaningful actual consumer fault. Reuse unchanged HUD/STAT/DMA evidence with
explicit source qualification. No RTL movement, new framework, full milestone
replay or physical I/O claim is included.

The exact test counts/dot ceilings and measured aggregate forecast must be
frozen with implementation layout before licensed execution. Target120 seconds
per simulation and300 ordinary aggregate; hard300 whole seconds for every run.
No simulation is authorized by a speculative performance estimate.

[bank0]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank0.asm
[bank3]: https://github.com/kaspermeerts/supermarioland/blob/618d00ed6c330928e106719533c6e294ae5d5726/bank3.asm

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

Initial planning forecast: CPU short20 seconds, CPU full150, game short130,
game full240, renderer220 and early CPU fault40 (800 seconds aggregate). These
are extrapolations from prior harness costs, not measured301 results or relaxed
limits. The ordinary300-second aggregate target may be missed; each simulation
still has a hard300-second whole-run cap. Freeze smaller actual case bounds
where feasible and report measured times; no extra duration or coverage quota
is introduced. Unchanged hardware/transport/STAT baseline evidence is reused only
with explicit input and behavior qualification.
