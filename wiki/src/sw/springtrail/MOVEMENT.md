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
| Start and coast | A counter rises toward 6 on directed movement. At 6, class0 becomes class2. No-direction input clears the speed class, decreases a nonzero counter and follows the stored direction for that invocation. | `Call_1D26`; the counter is a state/timer, not a fixed-point velocity. |
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
  fall immediately. There is no extra apex or exhaustion idle update.
- A ceiling collision clamps the upward candidate to the contact boundary,
  changes to descent at index 0 and clears the saved index. Do not also move down
  that update; the next update consumes descent index 0. Landing clamps to the
  support boundary, sets grounded and clears jump state and both indices.
- Keep the original 8x16 collision box, world coordinates and approved art anchors.
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
