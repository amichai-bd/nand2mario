# Verification baseline

Status: shared fixture harness and regression runner implemented. CPU vectors,
ROM acceptance adapters and independent emulator integration are planned below.
No Game Boy instruction or board behavior is implemented by this harness.

## Fixture contract

The test-only byte accumulator under `src/dv/baseline/` is original project
verification scaffolding. Its rising-edge behavior is: synchronous active-high
reset sets the output to zero; otherwise enable adds the unsigned input byte
modulo 256; otherwise the output holds. Reset wins over enable. Inputs remain
stable around the rising edge. The clock period is 10 ns; observation occurs
1 ns after the edge so nonblocking state updates have completed.

`fixture.sv` contains the only intentional defect: `+broken` drops the operand's
high bit before addition. It changes the DUT, never the oracle. The directed
sequence produces expected zero and actual 128 at cycle 6. Both simulators must
exit nonzero with that exact mismatch. A compiler failure, warning, timeout,
other fatal diagnostic or zero runtime exit cannot satisfy this negative case.

## Harness boundaries

| Component | Responsibility |
|---|---|
| Stimulus | Drive falling-edge transactions; initial reset, ten directed transitions, then 64 seeded transactions |
| Monitor | Capture applied reset/enable/operand and resulting output; publish one sampled transaction per rising edge |
| Reference | Predict using integer history and modulo arithmetic; never read DUT internal or output state |
| Scoreboard | Compare each transaction, write expected/actual evidence before failure, and update reference history |
| Assertions | Reject unknown outputs, incorrect reset, and disabled-state changes independently of the scoreboard |
| Coverage | Record reset, reset+enable, addition, zero/max operands, wrap, hold, and reset-after-activity |

The [test plan](../../../../src/dv/baseline/README.md) maps normal, edge, reset,
error and ordering cases to these components. Use this separation for later
units; their contracts must supply expected behavior before writing checks.
This UVM-lite uses modules and explicit sampled transactions, without class,
UVM library, SVA or covergroup dependencies. It works on both selected engines.

Directed literal checkpoints independently establish the oracle's expected
128 at cycle 4 and zero at cycle 6. The good test requires 75 comparisons and
all eight coverage bits. An independent 1,000 ns watchdog rejects a stalled
harness. These bins prove fixture cases, not CPU instruction or project coverage.
The fixed xorshift32 algorithm supplies the random suffix identically on each
simulator; seed zero is supported and the requested seed remains in every row.

## Execution and regression

Run through the shared builder; its [simulation contract](../../../tools/n2m/SPEC.md)
owns tool discovery, strict diagnostics, immutable attempts, cache and exits.
A direct fixture run is:

```text
python tools/build.py sim test baseline-good --sim questa --seed 31 --tag baseline-good
python tools/build.py sim test baseline-broken --sim questa --seed 31 --tag baseline-broken
```

The [regression runner](../../../../tools/n2m/baseline.py) executes the
[manifest](../../../../src/dv/baseline/regression.json) and validates artifacts:

```text
python tools/n2m/baseline.py --sim both --level smoke --tag baseline-smoke
python tools/n2m/baseline.py --sim both --level regression --tag baseline-regression
```

`--sim portable` chooses the builder's native-Icarus/default-WSL discovery;
`--sim questa` selects only Questa; `both` compares both. The optional
`--questa-bin` is passed only to Questa. Missing tools/license/runtime failures
fail the run; there is no fallback to another backend after selection. No
command modifies global paths, licenses, or device state.

The manifest owns the seed lists and aggregate wall budgets. `smoke` uses one
seed and both good/broken targets for changed-unit PR checks. `regression` uses
four seeds, including zero and the largest accepted seed, for baseline delivery
and later scheduled or affected integration runs. Portable smoke runs in hosted
Builder CI. Required local delivery runs both engines; licensed checks are not
claimed by hosted CI. Future CPU/system regressions must add separately reviewed
lists and budgets; no unimplemented CPU coverage is silently included.

Every child builder command retains its own subprocess timeout. The aggregate
budget is checked before each child and after the suite; it rejects overruns
but allows the current bounded child to finish and preserve its evidence.
The runner always requests fresh simulations. Tags are exclusive, at most
24 characters, with distinct child tags. It does not reuse stale runtime proof.

## Evidence and trace comparison

Each child builder attempt records source/tool fingerprints, seed, exact command,
raw exit, compilation/elaboration/runtime logs, `baseline.vcd`, and Questa WLF
when applicable. `transactions.csv` has these ordered decimal integer columns:
`seed,cycle,reset,enable,operand,expected,actual`. Cycle numbers start at one.
The scoreboard flushes each row before a fatal mismatch. Good runs additionally
write `coverage/bins.txt`; incomplete/broken runs do not claim full coverage.

The runner checks artifact hashes and confines them to the child build, requires
nonempty waveform/log/trace, checks the raw runtime exit, and validates ordered
row count, seed and the exact negative mismatch. For `both`, every CSV field and
row must match across simulators. It rejects omissions, extra rows or differing
values; there is no resynchronization or golden-trace update from DUT output.
The summary `workdir/builds/<tag>/regression.json` records each child command,
exit and log plus aggregate result/elapsed time and manifest hash. Child manifests
own the detailed versions and artifacts. Comparator unit tests inject missing,
extra, reordered, seed-corrupt and value-corrupt rows and missing-wave/wrong-exit
reports. These host tests supplement real simulation; they cannot replace it.

## Future adapter plans

These are reviewed designs and reuse plans, not implemented adapters. Select a
CPU boundary/model contract before enabling vectors, and preserve model-specific
unsupported cases explicitly. Import no commercial ROMs, boot images, saves or
private metadata into tracked sources or Pages. Downloads/builds remain under
ignored `workdir/`; external code is never copied into product RTL.

| Planned input | Immutable review pin | License and reuse boundary |
|---|---|---|
| [SingleStepTests SM83](https://github.com/SingleStepTests/sm83/tree/f9c30210245dd691661db39f5ace022c465ecc2f) | `f9c30210245dd691661db39f5ace022c465ecc2f` | [MIT](https://github.com/SingleStepTests/sm83/blob/f9c30210245dd691661db39f5ace022c465ecc2f/LICENSE); preserve copyright/permission with imported test data |
| [Mooneye test suite](https://github.com/Gekkio/mooneye-test-suite/tree/31510e12eea6286d36eea060a6adde755e1067aa) | `31510e12eea6286d36eea060a6adde755e1067aa` | [MIT](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/LICENSE); preserve notice with selected source and built test artifacts |
| [SameBoy core](https://github.com/LIJI32/SameBoy/tree/213a12ce93d66b105a113debd9396306066a7cfc/Core) | `213a12ce93d66b105a113debd9396306066a7cfc` | [Expat/MIT](https://github.com/LIJI32/SameBoy/blob/213a12ce93d66b105a113debd9396306066a7cfc/LICENSE) for Core; exclude iOS and HexFiend exceptions and unrelated frontends/assets |

These upstream license files were read at the named commits. No external test
or core content is imported here. An implementation must fetch only the exact
commit, verify the archive/content hash in its dependency lock, record selected
files, retain notices and identify any original glue/patches separately. Recheck
component headers/transitive build dependencies before importing or upgrading.
Missing notices, mutable revisions or unreviewed dependencies block that adapter.
The existing [RGBDS pin](../../../../tools/n2m/dependencies.json) is the planned
Mooneye build oracle; its invocation and output hashes must also be recorded.

### SingleStep vectors

Implementation follows [#101](https://github.com/amichai-bd/nand2mario/issues/101).

Parse the pinned [format](https://github.com/SingleStepTests/sm83/blob/f9c30210245dd691661db39f5ace022c465ecc2f/README.MD)
into an isolated CPU with flat test RAM, not the system MMIO map. Apply initial
registers and listed RAM, run one instruction under a bounded watchdog, then
compare final registers and touched RAM against the input's expected values.
Record vector name and first expected/actual difference. Treat bus observations
as M-state data; nullable address/data are don't-care only where upstream says
so. They do not prove T-state edge timing. Upstream does not establish reliable
interrupt-state expectations; the future CPU contract must classify IME/EI
cases explicitly and independent directed tests must cover any excluded fields.
Do not claim the source is infallible or use its Ares-derived expectations as
an independent Ares differential oracle. Preserve exclusions in the run report.

### Mooneye acceptance

Implementation follows [#103](https://github.com/amichai-bd/nand2mario/issues/103).

Select only tests compatible with the approved DMG model/revision and implemented
peripherals. Build the pinned selected source with the pinned assembler. The
[pinned reporting protocol](https://github.com/Gekkio/mooneye-test-suite/blob/31510e12eea6286d36eea060a6adde755e1067aa/README.markdown#passfail-reporting)
requires checking the register signature at its completion breakpoint or the
complete serial signature. An arbitrary breakpoint is not a pass. Treat the
failure signature, missing completion and watchdog expiration as failures.
Record test revision, model, image hash, completion signature and cycle bounds.
Tests relying on hardware-specific boot/reset state cannot be silently loaded
under `dmg-direct-v1`; provide the prescribed test state or explicitly exclude
them. Do not fake LY/SC reads to accelerate system acceptance. Manual/audio,
other-model and undefined-state tests remain outside a reviewed test selection.

### Independent emulator and retirement traces

Implementation follows [#102](https://github.com/amichai-bd/nand2mario/issues/102).

The planned original SameBoy Core adapter runs separately from the DUT and its
reference model. Select an explicit DMG model and apply the same documented
`dmg-direct-v1` initial state/input schedule; do not depend on a boot ROM. Before
execution, retain core commit, build options, model, image hash, interface ABI,
and adapter revision. Add a reviewed original observation hook where needed;
this plan does not claim an existing core API already exposes every field.

Both sides serialize the existing [retirement ABI](../../rtl/interfaces/MAS_interfaces.md#retirement-records)
and [generated layout](../../../cfg/interfaces.md#retirement-record) without a
second field definition. Compare ordered `(epoch, sequence, kind)` events and
all architectural values, fetched bytes and completed-dot counts exactly.
Interrupt entries remain separate events; HALT/STOP idle time produces no fake
retirement. Verify initial metadata/ABI and record lengths first. Missing, extra,
reordered or unknown records fail at the first difference with a bounded context
window. Never realign traces by PC or discard an unexplained field mismatch.
If the reference cannot expose an ABI field, adapter acceptance remains incomplete
until the observation is implemented and tested; do not fill it from the DUT.

Observe source frames independently and compare every visible pixel before VGA
conversion. Frame/input schedules follow the [charter](../../project-charter.md)
bounds; convenience host snapshots cannot replace every-frame evidence. Future
adapter tests must accept an independent known trace and reject one corrupt,
one missing and one reordered event, as well as one corrupt pixel. None of this
claims CPU, full-system or physical proof from the fixture baseline.
