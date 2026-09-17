# What faster feedback actually cost

*Before and after measurements for the verification feedback redesign · Evidence
through 17 September 2026*

This page publishes the before/after feedback measurements for the verification
feedback redesign: the preflight, the shared fixture adapters, the advisory
affected-test report with its conservativeness proof, and the split between host
preparation and the locked simulator phase. Every number below is copied from a
merged pull request's recorded validation or from a repository record; nothing
here was measured for this page except the pull-request interval cohorts, whose
method is stated. This is editorial history. The owning contracts are the
[builder SPEC](../tools/n2m/SPEC.md) and the
[verification tiers](../src/dv/integration/SPEC.md#verification-tiers); where a
sentence here and a specification disagree, the specification is current.

## Read these numbers carefully

The host is a shared WSL2 machine with 22 CPUs. Several agents run their own
suites on it at the same time, so every wall below is quoted with the load
average its author recorded, and walls from different trees are not directly
comparable: the test count, the catalogue and the tree itself grew throughout.
Where a comparison is meant to be exact, it is a single pull request measuring
one change on one tree; those rows say so.

None of this measures coverage. The scoped checks, independent review, and the
pixel, state, fault and completion gates are unchanged; only their cost moved.

## First feedback

Before the redesign, the first host gate an author could run was the required
Builder workflow sequence, executed locally block by block. At head `98fffff`,
[PR #531](https://github.com/amichai-bd/nand2mario/pull/531) records blocks 0
through 6 at 123.9, 3.3, 3.5, 4.5, 2.4, 2.5 and 411.9 seconds — about 552
seconds, under a declared 900-second aggregate.
[PR #526](https://github.com/amichai-bd/nand2mario/pull/526) records the same
shape: block 0 at 144.6 seconds and block 6 at 313.2 seconds, with 400
Springtrail host tests inside the last one.

Today the ordinary first gate is `check`, plus `tests validate` and
`regress pre-merge`:

| Gate | Before | After |
|---|---|---|
| `check` | FAIL on its 180 s timeout at load 3.2 to 5.8; the same tests run directly took 208 s for 910 tests (155 s user), head `31ba64e` | PASS, 60 to 62 s wall for 912 tests at load 4.1 to 5.6; 59 s with `regress pre-merge` running concurrently ([PR #757](https://github.com/amichai-bd/nand2mario/pull/757)) |
| `tests validate` | 0.4 s before host closures were declared | 5.4 to 6.8 s for 662 to 664 units, parsing every reachable module once ([PR #734](https://github.com/amichai-bd/nand2mario/pull/734), [#741](https://github.com/amichai-bd/nand2mario/pull/741), [#743](https://github.com/amichai-bd/nand2mario/pull/743)) |
| `regress pre-merge` | unchanged | 4.6 to 6.4 s aggregate (builder smoke and tile pixel), against a 300 s budget ([PR #736](https://github.com/amichai-bd/nand2mario/pull/736), #741, #743, #757) |

So first meaningful feedback is now about 70 seconds of host time in total,
inside the two-minute aim. It missed that aim in between: `check` grew from 75 s
at head `0163e37` ([PR #736](https://github.com/amichai-bd/nand2mario/pull/736))
to 132.5 s ([PR #741](https://github.com/amichai-bd/nand2mario/pull/741), which
added 23.5 s on a like-for-like baseline) to a 180 s timeout, because this same
epic put a 76-second real-clone equivalence proof inside it. Moving that proof
behind an opt-in command and running the host suite as three concurrent
alphabetical groups is what brought it back down; the budget itself never
changed.

## The advisory report

The affected-test report explains impact; it does not run tests and never owns a
required check. Its own cost was measured twice on the same mutated clones of
`HEAD`, quiet machine, by
[PR #743](https://github.com/amichai-bd/nand2mario/pull/743):

| Report | Before | After |
|---|---|---|
| RTL-only change | 17.36 s, 507 selected / 155 candidates of 662 units | 16.50 s, identical decision |
| Data-only change | 82.74 s, 502 / 160 | 22.42 s, identical decision |

The decisions, reasons and input hashes are byte-identical across the two
columns; only the walls moved, by memoizing the registry parse and each import
walk once per report instead of once per undecided simulation. The current
[SPEC sentence](../tools/n2m/SPEC.md#advisory-affected-test-report) carries those
walls as the contract.

Trust in those reasons is what the
[conservativeness proof](../tools/n2m/SPEC.md#conservativeness-proof) buys, and
it has a price of its own. The in-process proof over eleven recorded mutations
runs under `check` in about 14 to 20 s. Re-deriving the record for real — cloning
`HEAD` eleven times, running each detector before and after its mutation, and
running two full reports against the clones — takes 82 to 163 s depending on how
many real reports the row set carries, and is opt-in through
`tests mutations --confirm` (#741, #743, #757).

## Preflight and preparation

Two costs are new rather than reduced, and are worth stating as such.

Fixture preflight is host-only work that did not exist before. Nine canonical
Python preflights take 2.2 to 4.8 s each with ordinary host overlap. On a bounded
same-fixture experiment, removing the final 16 bytes from an upload declaration
passed the earlier preparation-only path in 0.736 s and is rejected by preflight
in 2.93 s, naming byte 2768 against the actual 2784
([PR #526](https://github.com/amichai-bd/nand2mario/pull/526)). That is seconds
of host time spent instead of a licensed simulation that would have failed.

Preparation overlap is measured from receipts, not claimed. On one tag,
[PR #736](https://github.com/amichai-bd/nand2mario/pull/736) recorded
`sim test preload-lifecycle` holding the tag lock for `locked_seconds` 4.37,
while `sim prepare preload-fixture` ran inside that window with no lock at
`prepare_seconds` 0.024; the adopted run then took the lock with
`locked_seconds` 0.52 and `timing` of prepare 0.024, build 0.29, run 0.02. The
demo targets are small, so the absolute saving is small; what the receipts prove
is that the split is real and that every simulation record now separates
preparation from the locked phase, so a future overlap can be measured the same
way.

## Full cycle

The honest answer is that end-to-end delivery time did not fall.

The frozen [repository statistics](../project-statistics.md) snapshot records PR
opening to merge at p75 31m 25s and p90 1h 51m. Grouping merged pull requests by
number, from the GitHub timestamps as collected on 17 September 2026
(`gh pr list --state merged --json number,createdAt,mergedAt`):

| Cohort | Merged PRs | Median | p75 | p90 |
|---|---|---|---|---|
| Before this work (#1 to #523) | 266 | 13 min | 36 min | 151 min |
| During milestones 1 to 3 (#524 to #733) | 114 | 21 min | 38 min | 95 min |
| After the closure, mutation and overlap slices (#734 onward) | 20 | 21 min | 74 min | 126 min |

Medians stayed in the 10 to 20 minute band the issue aimed for, but they did not
improve, and the later cohorts are slower at the tail. Three caveats apply and
none of them can be resolved from retained receipts. Opening-to-merge excludes
everything before the pull request exists, which is where most of an author's
work and its rework happen. The cohorts are not comparable work: the later ones
carry the tool and RTL changes of this epic and the game library, not a sample of
ordinary small edits. And the repository keeps no per-stage record of queue,
review and rework time, so the criterion's requested split cannot be published
from existing receipts at all.

What the receipts do support is narrower and still useful: host tool time on the
first gate fell from roughly 550 s to roughly 70 s, the report's cost stopped
depending on the kind of change, setup defects now fail in seconds of host time
instead of surviving into a licensed run, and preparation no longer has to sit
inside the scarce lock. Delivery time is dominated by other things.

---

*This article is editorial history dated 17 September 2026. Technical claims link
to the pull request or repository record that produced them; the linked
specifications, not this page, define current behavior.*
