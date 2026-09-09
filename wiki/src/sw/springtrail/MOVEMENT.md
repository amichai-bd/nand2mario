# Movement and animation research contract

This is the unfinished contract for [#301](https://github.com/amichai-bd/nand2mario/issues/301).
The current [game behavior](SPEC.md) remains implemented. The table below records
confirmed routine behavior, not yet complete per-frame SML1 equivalence.
Implementation waits for the dispatcher/profile resolutions below.

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

## Pending observable decisions

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

No guessed product implementation or per-update oracle is authorized by this
research table. Resolve these seams explicitly before changing the first
success criterion or asserting complete reference equivalence.

## Finite implementation/proof boundary

After resolution, freeze literal per-update cases for walk/run/coast/reversal,
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
