# Build system

Status: Verilator `doctor`, `sim test`, `tests run` and `regress` on WSL, `check`, MAX 10 `fpga build`, [software build/conformance](../sw/SPEC.md), [host load/control](host/SPEC.md), the [test catalogue](#test-catalogue), [declared regression subsets](#regression-subsets) and [tagged cleanup](#cleanup) are implemented.

## Purpose

The [PRD](PRD.md) owns the purpose and acceptance links.

The entry point is:

```text
python tools/build.py <command> [options]
```

`tools/build.py` is a thin dispatcher. Command logic belongs in small modules
under `tools/n2m/`.

## Available commands

Simulation commands run on WSL Linux:

```bash
python3 tools/build.py doctor --json
python3 tools/build.py check --tag builder-check --json
python3 tools/build.py sim test builder-smoke --tag smoke --seed 1 --json
python3 tools/build.py sim test builder-smoke --tag smoke --json
python3 tools/build.py sim test builder-smoke-fail --tag deliberate-failure --json
python3 tools/build.py sim test builder-smoke --verilator-bin <prefix>/bin --tag smoke --json
python3 tools/build.py tests validate --json
python3 tools/build.py tests list --level 0 --json
python3 tools/build.py tests run --level 0 --tag level0 --json
python3 tools/build.py tests run --label springtrail --tag springtrail --budget 600 --broader --json
python3 tools/build.py regress pre-merge --tag pre-merge --json
python3 tools/build.py regress builder-fault --tag deliberate-aggregate --json
python3 tools/build.py clean --tag deliberate-aggregate --json
```

FPGA commands run on Windows PowerShell; see [FPGA build](#fpga-build).

The second identical simulation reports `CACHED`. The deliberate-failure target
must exit 1 and retain its mismatch log and waveform. The `builder-fault` subset
must exit 1 naming `builder-smoke-fail`. Other successful commands
exit 0; errors exit nonzero. `--json` emits one result object on stdout.

`doctor` defaults to `--profile simulation`: on WSL it compiles, elaborates and
runs a checked Verilator smoke without consulting any license. Quartus and
devices remain explicitly untested in this profile. See
[environment doctor](#environment-doctor).
`sim test` proves compile, elaboration, run, and the target's expected signature
under [Verilator](#verilator-simulation); a target still registered for the
retired Questa path is reported `SKIPPED` with reason `questa-retired` and
exit 2, neither a pass nor a defect.
`check` runs host contracts with controlled simulator doubles; these are not RTL
evidence. It also proves the [test catalogue](#test-catalogue) still
covers every test in the tree, and fails naming the first uncovered file.

## Simulator policy

Verilator is the sole supported simulator and the default. The licensed Questa
seat has left the flow; no command may require a license variable, and a
license failure is never a `SKIPPED` reason for new work. The
[pinned toolchain](../../../tools/n2m/dependencies.json) is Verilator v5.052,
built from source on WSL, and cocotb 2.1.0; [installation](#installation)
names the steps. `--sim verilator` remains an optional explicit spelling for
`doctor`, `sim test`, `regress` and `tests run`. Retired selections (`questa`,
`auto`, `icarus`, `wsl-icarus`), the retired `--questa-bin` and
`--intel-sim-lib` options and the Icarus/WSL executable options fail argument
parsing. Missing tools fail with diagnostics; there is no fallback simulator.

One build tool serves two operating systems. On WSL (Linux) it owns `sim`,
`regress`, `tests run` and `doctor`; on Windows PowerShell it owns `fpga build`
and `fpga program`. Caches and fingerprints stay per OS under `workdir/`.
[Command ownership](#command-ownership-by-operating-system) names the refusals;
the [doctor](#environment-doctor) on Windows only states where simulation runs
and performs the Quartus, JTAG and UART identity checks. Where RTL instantiates
an Intel primitive, the predefined `VERILATOR` macro selects a behavioral double
and Quartus always sees the vendor instance; the
[memory MAS](../../src/rtl/common/MAS_memory_primitives.md) owns that rule.
Four-state assertions are removed during migration as an authorized behavior
change: Verilator runs with `--x-initial unique` and
`+verilator+rand+reset+2`, so an uninitialized read fails by value mismatch
rather than by an `X` check.

Migration is incremental per area. Every registry target records its
[simulator](#simulator-field); an unmigrated `questa` target reports `SKIPPED`
with reason `questa-retired` and never passes silently. The Intel primitive
doubles are tracked in [#598](https://github.com/amichai-bd/nand2mario/issues/598)
and the whole migration in [#595](https://github.com/amichai-bd/nand2mario/issues/595).

### Command ownership by operating system

One build tool serves two hosts. On WSL Linux it owns `sim`, `tests run` and
`regress`; on Windows PowerShell it owns `fpga build` and `fpga program`. Each
side refuses the other's commands before any workspace is taken: on Windows a
simulation command exits 1 with `simulation runs on WSL Linux`; on Linux an
`fpga` command exits 1 with `FPGA build and programming run on Windows
PowerShell`. Every command header and simulation record carries `os`
(`platform.system()`), and caches, fingerprints and compiled objects live under
the running host's own `workdir/`. [`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py)
covers both refusals and both permitted sides with a mocked platform.

## Test catalogue

[`src/dv/builder/catalogue.yaml`](../../../src/dv/builder/catalogue.yaml) holds
one entry per **runnable unit**: every registered simulation target and every
standalone `test_*.py` unittest file in the tree. A runnable unit is the
smallest thing that can be executed alone, which is what makes a recorded
duration meaningful.

The file holds `version` 1, a `labels` vocabulary, a `units` mapping, a
`not_runnable` mapping and an optional `retired` mapping. Each unit declares
exactly:

- `kind`: `sim` for a registered target, `unit` for a `test_*.py` file;
- `level`: `0`, `1` or `2`, single-valued and ordered. Level 0 buys simple
  confidence that nothing broke and is optimised for speed; level 1 is more
  thorough; level 2 is everything. Selecting a level runs every level below it.
- `labels`: a set, orthogonal to level. Every label must be declared in the
  file's own `labels` vocabulary; an undeclared label fails validation.
- `duration_seconds`: the wall of the last actual run, or `null` before the
  first. `tests run` writes it back; it is not edited by hand.

`not_runnable` maps a `test_*.py` path to the reason nothing can run it. It
covers the builder's own `tools/n2m/test_budget.py`, which is the wall-budget
supervisor rather than a test, and two cocotb entry points under
`src/dv/springtrail` that no registry target names.

`retired` maps a former registry target name to the reason the simulator cannot
serve it. A retired name may not remain in the registry or in `units`; `tests
validate` and `check` fail on either. It records `async-assert-known` and
`ppu-shift-unknown`, whose expected fatal was a four-state `N2M_ASSERT_KNOWN`
on an X input; a two-state simulator cannot witness X, so the
[macro](../../src/rtl-reference-style.md#named-assertion-convention) is a no-op
under `VERILATOR`.

The file is a strict YAML subset so the builder keeps its stdlib-only
dependencies: block mappings, flow mappings, flow sequences, plain and quoted
scalars, and whole-line comments. Inline comments are refused, because a `#`
inside an unquoted value would otherwise be silently truncated. `tests validate`
rewrites nothing, and `tests run` rewrites only the unit lines it measured, so
comments and order survive.

### Coverage is a build gate

`tests validate` and `check` both prove the catalogue still covers the tree. A
`test_*.py` file present in the tree fails the build unless it is a catalogued
unit, a `not_runnable` entry, or already an input of a catalogued registry
target — the last case covers cocotb modules, which run through their target
and never alone. A registered target absent from the catalogue, a catalogued
target absent from the registry, and a catalogued path naming no file each fail
the same way. This is the control that stops the catalogue drifting out of date.

### Selection

`tests list` and `tests run` select by `--level`, by `--label`, or by both.
Repeated `--label` requires every named label. A selection needs at least one
selector.

Two failure modes are deliberately loud:

- an undeclared selector label fails with `unknown label: <name>` before
  anything runs; and
- a selection matching zero units fails with
  `selection matched no tests: <selector>`, naming any selector that carries
  nothing. A typo that runs nothing and reports success is the same shape of
  bug as an ungated suite.

### Execution and contention

A `sim` unit runs as the ordinary `sim test` worker under the run's tag, with
the same `--seed`, `--rebuild` and `--verilator-bin`, under the
same [per-target wall budget](#test-wall-budget). A `unit` runs as
`unittest discover` over exactly that one file, with the file's own directory as
the top level and `tools/` on `PYTHONPATH`. Its stdout and stderr share one
pipe; the whole output is kept, and the one-line `error` is the first
`FAIL:`/`ERROR:` header, else the `FAILED` verdict, else the last line. A unit's
own trailing print is never reported as its failure.

A `sim` unit whose registry row still names `simulator: "questa"` is reported
by name as `SKIPPED` with reason `questa-retired` before any child is launched,
and the run exits non-zero only when something actually failed. A unit labelled
`needs-cocotb` is skipped with reason `cocotb-environment` when the pinned
`src/dv/python` interpreter is absent. A skip is not a defect, and is never
silently swallowed: the summary lists every skipped unit in `skipped`.

The default aggregate budget is the ordinary 300-second pre-merge aggregate.
`--budget` declares another; above 300 seconds it also needs `--broader`, as a
regression subset does. The result is published as
`workdir/builds/<tag>/tests/summary.json` and as the tag's `manifest.json`;
`tests/.lock` holds the tag for the whole selection.

## Verilator simulation

Verilator v5.052 on WSL is the executing simulator for every registry target
with `simulator: "verilator"`. [`verilator.py`](../../../tools/n2m/verilator.py)
builds the commands and checks transcripts; [`simulator.py`](../../../tools/n2m/simulator.py)
discovers the tool; [`simulation.py`](../../../tools/n2m/simulation.py) runs the
stage and publishes the record.

### Simulator field

Every target in [`targets.json`](../../../src/dv/builder/targets.json) declares
`simulator` as `verilator` or `questa`. A missing or unknown value fails the
target validator, `tests validate` and `check` with
`registry target <name> must declare simulator as one of verilator, questa`.
A `questa` target is retired: `sim test`, `tests run` and `regress` report it
by name as `SKIPPED` with reason `questa-retired`, publish a `SKIPPED`
`sim/test/<target>/result.json` naming `simulator`, `os` and `seed`, and never
discover a simulator or launch a child. It counts as neither a pass nor a
defect; `sim test` exits 2 and the aggregate commands list it in `skipped`.
`vendor_model` on a `verilator` target records the synthesis binding of the
RTL under test (`intel-memory`, `intel-adc` or `intel-controls`). The Verilator
stage compiles no vendor source: the wrapper selects the repository double
under `VERILATOR`, and the record's `options.vendor_model` names the binding
and the double. `intel_mixed_mode_instances` was the Questa model's
coercion-diagnostic inventory; the double emits no such diagnostic, so the
validator refuses the field under `verilator` (see the
[memory MAS](../../src/rtl/common/MAS_memory_primitives.md#writes-and-collisions)).
An `intel-adc` target receives the [channel fixture files](#intel-adc-binding-under-verilator)
beside its run. `defines` lists `NAME` or `NAME=VALUE` identifiers that the
build passes as `+define+`; elaboration-time selection is a build option, not
a runtime plusarg, and the validator refuses any other shape.
`preload` runs on the Verilator stage; see
[preload fixtures](#preload-fixtures-under-verilator). A `driver` runs through
the [Verilator peer](#verilator-peer-driver). The migrated targets
are `builder-smoke`, `builder-smoke-fail`, `python-joypad`,
`python-joypad-fault`, `preload-fixture`, the three `tb_verilator_peer`
targets `verilator-peer`, `verilator-peer-fault` and `verilator-peer-fatal`,
the 58 SystemVerilog targets
labelled `cpu`, the 67 SystemVerilog targets labelled `ppu` or `input`
that declare no `vendor_model` in the [test catalogue](#test-catalogue), the
34 SystemVerilog targets without a `vendor_model` labelled `joypad`,
`interrupts`, `timer`, `serial`, `interfaces`, `display`, `clocking`
(`clocking-early-reset`, `timebase25`, `timebase25-bad-numerator`) or
`common` (`assert-synthesis`, `register-macros`, `register-macros-corrupt`),
the 23 SystemVerilog targets without a `vendor_model` labelled `dma`, `uart`
or `baseline`, the 117 SystemVerilog targets that declare a `vendor_model`
(the `memory`, `dma`, `uart`, `vga`, `snapshot`, `audio`, `ppu`, `input`,
`common`, `integration` and `host-play` areas, including the ten `driver`
targets and the two `tb_preload_load` targets), the three `tb_clocking` targets `clocking`, `clocking-bad-numerator` and
`clocking-drop-tick`, and the five `tb_async_assert_macros` targets
`async-assert-macros`, `async-assert-direct`, `async-assert-hold`,
`async-assert-never` and `async-assert-no_reset`. `ppu-shift-unknown` and
`async-assert-known` are [retired](#test-catalogue): their expected fatal was
a four-state `N2M_ASSERT_KNOWN` that a two-state simulator never raises.

### Registered target execution

```bash
python3 tools/build.py sim test builder-smoke --tag smoke --json
python3 tools/build.py sim test builder-smoke --verilator-bin <prefix>/bin --tag smoke --json
```

`--verilator-bin` selects the directory containing `verilator`; omit it to
resolve it on PATH. Discovery runs `verilator --version`, requires a
`Verilator <release>` banner with no diagnostic, and records the executable
path, hash, banner and release. The C++ compiler Verilator drives (`CXX`, else
`g++`) is discovered and recorded the same way, because it shapes the binary
the run executes. Missing or invalid explicit selections fail without fallback,
and no command changes the caller's environment or reads a license variable.

Each attempt has two commands. The build verilates and compiles under
`compile/verilator/<target>/<attempt>/obj_dir/` with `--cc --exe --build`,
`--trace-fst`, `--x-assign unique --x-initial unique`,
`+incdir+<root>`, `--top-module <top>` and `-j 0`, within the target's selected
[wall budget](#test-wall-budget). Verilator's lint warnings stay fatal; nothing
passes `-Wno-fatal`. A SystemVerilog testbench builds with `--timing` and a
harness `sim_main.cpp` written beside `obj_dir`: it is Verilator's own `--main`
loop plus an FST trace of the whole top opened at `waves/simulation.fst`, and
it exits nonzero when the runtime counted an error. A testbench's own
`$dumpfile` still writes where it says, in FST form under `--trace-fst`. The
run executes `obj_dir/sim` from the attempt with `+seed=<seed>`,
`+verilator+seed+<seed>`, `+verilator+rand+reset+2` and the registry `args`,
under the registry `timeout_seconds` (default 60).

Time-zero edge semantics follow an event-driven simulator: an edge fires only
when an assignment changes a signal's value. Verilator captures each trigger's
previous value from the randomized initial state at initialization, so a
randomized initial value is never itself an edge and a clock that is never
driven never clocks its process. The runner therefore does not pass
`--x-initial-edge`: Verilator 5.052 implements that option by setting every
trigger at initialization (`V3SchedTrigger.cpp`), which executes every
`always @(posedge clk ...)` once at time zero with the testbench's time-zero
inputs, shifts `n2m_reset_control`'s synchronizers one edge early and loads
power-up initialized `DFF_INIT_*` registers before any real edge. The
alternative of keeping the option with deterministic clock and reset initial
values cannot work, because that trigger is set regardless of value. The cost
is that a two-state simulator has no X-to-value edge: an asynchronous reset
written at time zero, by an `initial` block or a cocotb write before the first
evaluation, fires its `posedge` only when the randomized previous value
happened to be 0. A testbench that needs the reset before its first clock
asserts it by an explicit assignment after time zero, as
[`test_joypad.py`](../../../src/dv/python/joypad/test_joypad.py) does; a reset
held across the first clock edge needs nothing, because the clocked branch of
`DFF_ARST_*` and `DFF_RST_*` resets there.

Any `%Warning` line in the build or run, and any `WARNING`, `ERROR` or
`CRITICAL` word from cocotb's log, fails the attempt as `unexplained simulator
warning`; any `%Error`, `%Fatal`, `ERROR` or `CRITICAL` line fails it as
`unexpected simulator diagnostic` unless the target expects a nonzero exit and
the line carries its declared signature. A `$fatal` reports its signature on
the `%Fatal` line, then `%Error: <file>:<line>: Verilog $stop` and
`Aborting...`; those two are the fatal's own stop and are accepted with it.
The raw exit must match `expected_exit`, the signature must appear, and the
retained wave must exist; otherwise the attempt is `FAIL`.

### Python testbenches under Verilator

`testbench: "python"` targets keep the [testbench contract](#testbench-types):
the same `python` object, import closure, pinned interpreter and one named
completed test. The build adds `--vpi --public-flat-rw --timescale 1ns/1ps`,
links `-lcocotbvpi_verilator` from the installed cocotb 2.1.0 library
directory, and compiles cocotb's own `share/lib/verilator/verilator.cpp` as the
main; `--timing` is not passed. The run adds `--trace --trace-file
waves/simulation.fst` and the same seed plusargs. The environment sets
`GPI_USERS` to the embedded `libpython` and cocotb's GPI entry point beside
`PYGPI_PYTHON_BIN`, `LIBPYTHON_LOC`, `COCOTB_TOPLEVEL`, `COCOTB_TEST_MODULES`,
`COCOTB_RESULTS_FILE` and `COCOTB_RANDOM_SEED`; caller `COCOTB_*`, `GPI_*`,
`PYGPI_*` and `PYTHON*` settings are replaced. The discovered runtime records
the Verilator VPI library, `verilator.cpp`, entry point, `libpython`,
interpreter and installed package contents, so all of them enter the
fingerprint.

`results.xml` follows cocotb 2.1: one `testsuite` per module with counted
`tests`, `failures`, `errors` and `skipped`, one `testcase` per test carrying a
`properties` block with `sim_time_duration`, and a `failure`, `error` or
`skipped` child when the test did not pass. PASS requires raw exit zero, the
transcript signature, exactly one counted test whose identity matches the
declared `module` and `test`, positive wall and simulation time, and the
verdict `expected_exit` declares, plus nonempty `results.xml`,
`transactions.jsonl`, `waves/simulation.fst` and `sim.log`. cocotb ends a
failed test through `$finish`, so the simulator process exits zero for every
Python target and a nonzero process exit always fails the attempt; for a
Python target `expected_exit` names the verdict of its named test. `zero`
requires no verdict child and zero failure counts. `nonzero` is the Python
form of a deliberate failure, checked by
[`python_tb.accepted`](../../../tools/n2m/python_tb.py): the test must carry a
`failure` or `error` child whose message contains the target's `signature`
(a `skipped` child never satisfies it), the signature must also appear in the
transcript, and a warning line is explained only when it names the declared
`<module>.<test> failed`, as cocotb's `WARNING cocotb.regression` report of
the failed test does; every other warning still fails the attempt. A passing
or skipped test, an unrelated failure, or invalid results fail a `nonzero`
target exactly as a failure fails a `zero` target, and neither is reused. [`python-joypad-fault`](../../../src/dv/python/joypad/README.md) is
the registered example. The optional `python.waves` list is validated as
before but does not narrow the trace: Verilator's FST holds the whole top.

### Preload fixtures under Verilator

A target that declares `preload` names one of the registered fixture builders
in [`python_tb.FIXTURE_BUILDERS`](../../../tools/n2m/python_tb.py); the
validator, `tests validate` and `check` reject any other value with
`preload <name> has no registered fixture builder to check`. The
[testbench types](#testbench-types) section names each preload's image and
inputs. A Python target carries the fixture's inputs in `python.inputs` as
before. A SystemVerilog target declares them in `preload_inputs`: a nonempty
list of in-tree files that must include every file the builder reads for that
preload and every module the builder imports under `tools/`, the same closure
`python_tb.validate` demands of Python targets (`tools/n2m/*.py` and
`tools/build.py` are implicit). `preload_inputs` on a Python target, or
without `preload`, is rejected.

Every fixture input is hashed into the fingerprint, so a changed program
source, layout, packager or builder module rebuilds rather than reuses. For
`preload: "mooneye-reg-f"` the locked host toolchain identity from
[`mooneye.tool_identity`](../../../tools/n2m/mooneye.py) enters the fingerprint
as `options.fixture_tools`. On Linux the default build host is the locked
Ubuntu toolchain (`N2M_MOONEYE_BUILD_HOST=wsl`), which
[`mooneye_wsl.py`](../../../tools/n2m/mooneye_wsl.py) runs natively with the
same identity hash, pinned image hash and `timeout` process bound it used
through `wsl.exe`; the `windows` backend fails because it needs the retired
Questa installation's MinGW tools.

Before the build command, `python_tb.prepare` builds the image in the attempt
directory and emits `preload-rom.mif`, `preload-presence.mif`,
`preload-crc.hex` and `preload.json` beside it, then checks them
(`fixture-preflight.json`). Immediately before the run command,
[`preload.verify`](../../../tools/n2m/preload.py) rechecks the image hash and
every emitted file hash; a mismatch fails the attempt without launching. The
verified manifest is retained in the record as `preload` (`image_sha256`,
`image_crc32`, `files` hashes and `fixture` when one is named). The run
executes from the attempt directory, so `$readmemh("preload-crc.hex")` under
`SIM_PRELOAD` and `SIM_INIT_FILE("preload-rom.mif")` resolve to the prepared
files, as they did under Questa. A driver target that sets `driver.preload`
instead prepares through its Python peer, and the same recheck runs after the
peer is ready and before the run launches.

`preload-fixture` ([`tb_preload_fixture.sv`](../../../src/dv/preload/tb_preload_fixture.sv))
proves the pipeline without product RTL: it reads the ROM MIF, presence MIF and
CRC hex from its run directory, rebuilds the 32768 bytes, requires the CRC-32
of the rebuilt image to equal the hex the loader reads, and checks the
integration image's entry stub and title. Measured on WSL: build 4.5 s, run
under 0.1 s, `CACHED` on rerun. `preload-lifecycle` and `preload-crc-fault`
([`tb_preload_load.sv`](../../../src/dv/preload/tb_preload_load.sv)) run the
loader against the initialized RAM double with the same `preload: "integration"`
declaration and rebuild their expected bytes from the prepared ROM MIF. The
Python-area preload targets flip in their own migration.
[`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py)
`PreloadTests` cover validation, preparation, the pre-launch recheck, the
record, and fingerprint invalidation by a changed fixture input or Mooneye tool
identity, with doubles.

### Verilator peer driver

A `driver` target steers a SystemVerilog testbench from the builder-owned
Python peer through a live byte bridge. The catalogue schema is unchanged:
`driver` holds `script`, `peer`, `inputs`, `access` and optional boolean
`preload`. Under `simulator: "verilator"` the `script` is the Verilator peer,
a cocotb module ending in `.py` that defines one test named `peer`; `access`
must be a nonempty list of top-level identifiers. The validator, `tests
validate` and `check` refuse a `verilator` driver whose script is not a `.py`
module (`driver script must be the Verilator peer module (.py)`), whose
access list is empty, or whose script, peer or inputs are missing or outside
the tree. A `questa` target keeps its retired Tcl script and is `SKIPPED`.

The run is the [Python flow](#python-testbenches-under-verilator) with
`--timing` kept, because the testbench owns the clock, the checks, the
signature and `$finish`; cocotb's main advances to the testbench's next time
slot between the peer's own timers. Instead of `--public-flat-rw`, the build
takes a generated configuration `compile/verilator/<target>/<attempt>/access.vlt`
that makes exactly the `access` list public on the top module
(`public_flat_rw -module "<top>" -var "<name>"`); the peer touches nothing
else, and the whole-design switch cost Verilator most of its optimizations
(`integration-smoke` ran 168 s with it and 68 s without), and compiles with
`-CFLAGS -O2` instead of Verilator's default `-Os`, because the composed
product systems otherwise exhaust their wall budget (`host-play` ran 200 s
with `-O2` and did not finish in 288 s without). The build also passes the
target's `defines` as `+define+`. The stage discovers the pinned runtime,
so `sim test` for a driver target runs on the pinned interpreter like a
Python target. Before the run command the builder starts the Python peer
([`simulation_peer.py`](../../../tools/n2m/simulation_peer.py)), waits for
`peer-ready.json`, rechecks a declared `preload`, and passes the listener port
as `N2M_PEER_PORT` and the access list as `N2M_DRIVER_ACCESS` beside the
cocotb environment; `COCOTB_TEST_MODULES` is the script's module name and its
directory heads `PYTHONPATH`. The run also receives `+smoke_root=<root>`. The
record's `peer` names the port, module and access list; `driver.script`,
`driver.peer`, `driver.inputs`, the pinned requirements and the peer
interpreter identity enter the fingerprint.

[`peer_bridge.py`](../../../src/dv/integration/peer_bridge.py) is the peer's
protocol, shared by [`integration/driver.py`](../../../src/dv/integration/driver.py)
(absolute `WAIT 136280`) and [`host_play/driver.py`](../../../src/dv/host_play/driver.py)
(relative `WAIT 200000|150000`, `FAIL PLAY_*`, `driver-progress.log`). It
connects to the peer, advances 1 us, then answers line by line: `TX <hex>`
clears `rx_count` and `rx_done`, deposits `tx_bytes`, `tx_count` and `tx_go`,
polls every 100 us of simulation time until `rx_done` and not `tx_busy`
within 120 s of wall time, and replies `RX <simulation_ns> <hex>`; `WAIT <n>`
polls `dot_count` and replies `WAITED <simulation_ns>`; `DONE` closes the
bridge, deposits `finish_request` and advances 1 us, inside which the
testbench prints its signature and calls `$finish`, and the test then
completes. Every observed or deposited object must be in `access`, resolved
once on the top at start (`SMOKE_DRIVER_ACCESS <name>` otherwise). Faults are
raised by name with the retired driver's vocabulary: `SMOKE_DRIVER_TX_SIZE`,
`SMOKE_DRIVER_RX_SIZE`, `SMOKE_DRIVER_WAIT_RANGE`, `SMOKE_DRIVER_MESSAGE`,
`SMOKE_DRIVER_LINE_SIZE`, `SMOKE_DRIVER_PEER_EOF`, `SMOKE_DRIVER_PEER_TIMEOUT`
(30 s peer idle) and `SMOKE_DRIVER_RESPONSE_TIMEOUT`. Progress lines
`SMOKE_DRIVER phase=<phase> ordinal=<n> wall_ms=... sim_ns=... dot=...
tx_count=... tx_busy=... rx_count=... rx_done=...` go to the transcript, and
`driver-transactions.json` records each request, reply and simulation time
beside the Python peer's own `client.json`.

The verdict for `expected_exit: "zero"`: raw exit zero, the cocotb
`results.xml` for `<module>.peer` reports PASS, the transcript signature is
present, no diagnostic, the retained wave exists, and the Python peer exited
zero within 5 s. A peer fault fails the attempt as `Verilator peer failed:
<name>` with the raised name, and the Python peer is reaped with
`completed_normally: false`. A `driver` attempt is reused only with
`results.xml`, `peer.log`, `peer-result.json`, `waves/simulation.fst` and
`sim.log` present and nonempty. For `expected_exit: "nonzero"` the testbench's
`$fatal` ends the simulation while the peer test is running; cocotb then
reports exactly `WARNING cocotb.regression <module>.peer failed` and
`cocotb.regression.SimFailure: cocotb expected it would shut down the
simulation, but the simulation ended prematurely...`. When the declared
signature appears on a diagnostic line (`%Fatal`, `%Error`, `ERROR` or
`CRITICAL`), that two-line report is
accepted as the fatal's own stop report for that module only; any other
warning still fails the attempt, and no results check applies. A deliberate
failure the peer raises instead (the `host-play` variants' `FAIL PLAY_*`)
ends through `$finish` with raw exit zero; that form passes only when the
peer test's `results.xml` failure message carries the declared signature
([`python_tb.accepted`](../../../tools/n2m/python_tb.py)), the signature is
in the transcript, and the only explained warning is cocotb's
`<module>.peer failed` report of that test.

[`tb_verilator_peer.sv`](../../../src/dv/integration/tb_verilator_peer.sv) proves
the peer without product RTL: the tb_integration mailboxes, a 25 MHz
`dot_count`, and a byte endpoint that answers each request with every byte
inverted by `0x5a` plus a terminating zero. [`peer_check.py`](../../../src/dv/integration/peer_check.py)
is its Python peer: requests of 1, 19 and 271 bytes, `WAIT 136280`, `DONE`,
checking each reply and monotonic simulation time. `verilator-peer` expects
`PASS verilator-peer transactions=3`; `verilator-peer-fault` uses
[`peer_check_fault.py`](../../../src/dv/integration/peer_check_fault.py), which
sends `WAIT 5` after the first request, and must fail as `Verilator peer
failed: SMOKE_DRIVER_WAIT_RANGE`; `verilator-peer-fatal` passes `+echo_fault`
so the endpoint raises `PEER_ECHO_FAULT seq=2` inside the second transaction
and must exit nonzero with that signature. Measured on WSL: build 1.4 s cold
and 0.25 s with `ccache`, run under 0.5 s, `CACHED` on rerun.
[`test_peer_bridge.py`](../../../tools/n2m/tests/test_peer_bridge.py) covers
the protocol against a fake access list;
[`test_simulation_peer.py`](../../../tools/n2m/tests/test_simulation_peer.py)
and [`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py) cover
validation, the stage, the by-name failure and the fatal acceptance with
doubles. The ten product driver targets (`integration-smoke` and its three
fault variants, `integration-preloaded` and the five `host-play` targets) run
through this peer with `script` at `src/dv/integration/driver.py` or
`src/dv/host_play/driver.py`; `integration-preloaded` selects its prepared
images with `defines: ["PRELOADED"]`, and its `driver.preload` peer prepares
them. The two `tb_preload_load` targets declare no driver: their retired
`load.do` only acknowledged image preparation, which `preload: "integration"`
with `preload_inputs` now does on the stage.

### Record

Beyond the shared fields, a Verilator record carries `simulator`
(`verilator`), `os`, `seed`, `waves` (`format: fst` and the retained path),
`timing` with `build_seconds` and `run_seconds` measured separately so the
compile cost against the wall budget is visible, `elapsed_seconds`,
`exit_code` and `timeout_seconds` on each command, `preload` when the
target declares a fixture, and `peer` plus `python_results` when it declares
a driver. Measured on WSL: the
`builder-smoke` build takes about 4 s cold and under 0.3 s with `ccache`, the
run milliseconds; `python-joypad` builds in 0.3 s and runs in 0.4 s.
[`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py) covers
discovery, command shape, transcript classification, the record fields, retired
targets and host ownership with doubles; the runs above are the simulator
evidence.

## Questa simulation

This section describes the retired path. Every target it still applies to is
registered `simulator: "questa"` and is reported `SKIPPED questa-retired` by
the commands above; its command construction, macro and Intel model bindings
stay in [`questa.py`](../../../tools/n2m/questa.py),
[`intel_memory.py`](../../../tools/n2m/intel_memory.py) and
[`intel_adc.py`](../../../tools/n2m/intel_adc.py) for the area
migrations under [#595](https://github.com/amichai-bd/nand2mario/issues/595).
The retired Tcl driver scripts (`driver.do`, `load.do`) remain in the tree
for the Questa retirement; no registered target names them. The Python peer
process they connected to is the same
[`simulation_peer.py`](../../../tools/n2m/simulation_peer.py) the
[Verilator peer](#verilator-peer-driver) uses.

### Testbench types

The [target registry](../../../src/dv/builder/targets.json) defaults to
`testbench: "systemverilog"`; existing SV commands and expected-exit rules stay
unchanged. `testbench: "python"` explicitly selects cocotb with a closed `python`
object requiring `module`, `test` and `inputs`, with optional `waves`. No other
keys are accepted. The module/test are identifiers;
inputs name checked-in files including exactly one module file. Unsupported
types, missing inputs and driver settings fail without fallback.
`expected_exit` names the Python verdict, as the
[Verilator Python contract](#python-testbenches-under-verilator) defines. The
first path accepts one named Python test per target. The [usage guide](../../../src/dv/python/README.md) owns
setup and commands; the [joypad plan](../../../src/dv/python/joypad/README.md)
owns its bounded subsystem coverage.

`waves`, when present, is a nonempty list of unique public signal identifiers
from the top module. Hierarchical paths, wildcards and Tcl text are rejected.
Both WLF and VCD select exactly those names. Omission retains the existing
top-level selection. Passive projections may bound waveform activity while
continuous functional monitors retain the complete required observations.

Each Python target module registers one decorated cocotb test. The declared
`test` field validates the completed XML identity; it does not select which
tests cocotb schedules from the module.

Python targets may select `vendor_model: "intel-memory"` through the existing
strict model resolution, hashing and library binding. The explicit
`intel-controls` profile adds the same pinned ADC models and real ADC PLL
at the specified system/pixel clock boundary for the [paused controls proof](../../../src/dv/python/controls/README.md).
It checks the exact ADC diagnostics plus the existing Python access warning and
declared frame-RAM diagnostics. Other vendor selections remain unsupported.
`preload: "integration"` packages the original integration
image and prepares/verifies the supported Intel initialization files before
elaboration; it requires the software packager inputs in the Python fingerprint.
The [integration plan](../../../src/dv/python/integration/README.md) owns its
diagnostic scope and historical source comparison. `preload: "v05"` uses the
original v0.5 software build and its recorded image hash with the same preparation,
verification and public loader adoption. It requires that software's source,
layout and tool inputs. This is short execution evidence, not real UART loading
or full milestone acceptance; the [v0.5 plan](../../../src/dv/python/v05/README.md)
owns those separate gates.

`preload: "mooneye-reg-f"` selects only the [locked external fixture](../../../src/dv/mooneye/README.md).
Its builder verifies source archives, installed build-tool identities, the
unmodified ROM and linked completion symbol before the same Intel-file emission.
The pins, separate license notices and compiler/CMake inputs enter the record.
This named validator does not change original-software validation or the product
loader. Generated files are rechecked before simulator launch.

`preload: "startup-read"` and `"startup-write"` package the original
[startup OAM boundary witnesses](../../../src/dv/ppu/startup202.md), validating
literal instructions and declared image hashes through the same Intel preload
preparation. Their source and software tools are fingerprinted inputs.

`preload: "late-fe9c"`, `"late-fe9d"` and `"late-fe20"` use the same
preparation for the original [nonuniform late OAM witnesses](../../../src/dv/ppu/late208.md).
The producer verifies literal instructions and a declared whole-image hash;
its source and software tools are required fingerprinted inputs.

`preload: "timer234"` packages the original [actual-v0.5 timer program](../../../src/dv/timer/README.md#actual-v05-timer-program)
through the same validated Intel preparation and public loader adoption. Its
literal instruction/hash producer and software tool inputs are required in the
fingerprint. It proves bounded execution, not physical UART loading.

`preload: "dma239"` uses the same preparation for the original
[actual-v0.5 DMA program](../../../src/dv/dma/README.md#actual-v05-dma-program).
Its literal instruction/hash producer and software tools are required inputs.
The image executes CPU writes to seed WRAM and HRAM; preloading does not supply
the transferred OAM bytes or bypass subsequent memory arbitration.

Python targets use the executing pinned interpreter and installed packages from
the [separate dependency record](../../../src/dv/python/THIRD_PARTY.md). Normal
SV use does not import or require cocotb. Execution does not install dependencies.
The shared stage fingerprints Python input files, pins, interpreter, embedded
Python library, cocotb native library and installed package content. It retains
the shared timeout, command logs, input hashes, immutable attempts and result
publication. Runtime environment settings for cocotb filters, test selection,
seed, result paths and Python integration are replaced by the target settings;
license environment remains available.

Each Python attempt additionally retains `results.xml`, `transactions.jsonl`,
`waves/simulation.vcd` and `waves/simulation.wlf`. PASS requires raw Questa exit
zero, the expected transcript signature, one completed named passing XML test,
and nonempty trace/wave evidence. Skipped, extra, incomplete, malformed, missing
or failing Python tests cannot pass. Raw command exits and `python_results`
remain distinct; a Python failure can accompany raw exit zero and still makes
the builder exit 1. Negative Python targets remain FAIL and are never reused.
Required evidence paths and hashes are checked before cache reuse.

A simulation is reused only when every declared input is unchanged, so every
module the test module or the preload's fixture builder imports, transitively,
under `src/dv/springtrail`, `tools/` or `src/dv/python/integration` must appear
in `python.inputs`; `tools/n2m/*.py` and `tools/build.py` enter every
fingerprint and need no declaration. `python_tb.validate` walks the import
statements with `ast`, including those inside functions and branches, and
rejects the target naming it and each undeclared module. For an import on a
branch the target never takes, `python.excluded_imports` maps the module to the
reason it is never loaded; the exclusion prunes that module and whatever only it
would load. Validation rejects an exclusion without a reason, outside the three
directories, also declared as an input, or never reached from the target, and
rejects a preload with no registered fixture builder. The walk sees only
`import` statements: a module loaded through `importlib`, `__import__` or a
string path, as `motion_program.py` loads its `*_cases` module, is invisible
to the check and must be declared by hand. An exclusion is honoured even when
the module is always loaded, so its recorded reason is the only evidence;
review each reason against the branch it names.
[`test_import_check.py`](../../../tools/n2m/tests/test_import_check.py) covers
detection and the exclusion mechanism.

Classic waveform access uses `-no_autoacc` and `-voptargs=+acc=rnbp+/<top>`.
WLF and VCD log top-level signals, including explicit observation latches,
without recursively dumping memory arrays.
The exact single vopt-10908 optimization warning and matching zero-error,
one-warning summary/restored counts are explained in the record. This visibility
cost is expected; other warnings and errors still fail. Python scheduling uses
the simulator's time and does not introduce a second RTL execution engine.

### Installed Intel ADC model

`vendor_model: "intel-adc"` resolves the pinned installed control core, canonical
synchronizer, public and encrypted MAX10 atoms, and PLL models. It uses the same
installation discovery and explicit `--intel-sim-lib` selection as memory did
while that option was accepted.
Every source hash and PLL generation dependency enters the fingerprint before
reuse. Each attempt records the actual PLL generator command, verifies its
parameters against the FPGA configuration, and retains the generated hash.
Vendor compilation separates `n2m_intel_adc_atoms` from the control library
`n2m_intel_adc`. Control resolves its canonical synchronizer locally; it does
not overwrite the alternate definition embedded in `altera_mf.v`. Explicit
run mappings and `-L` binding preserve that separation. Repository substitutes
for these modules are rejected.

The pinned top wrapper contains CR-CR-LF around its timescale. Only its exact
vlog2083 line24 diagnostic is explained, with the supported source hash, path,
single occurrence and one-warning/zero-error summary required. Raw logs and
`explained_compile_diagnostics` retain that one actual warning. Other compiler
or runtime warnings remain failures. No vendor bytes are edited or compiler
warnings suppressed. Host dependency tests are not hardware behavior evidence.

### Intel ADC binding under Verilator

A `verilator` target with `vendor_model: "intel-adc"` lists the PLL and control
doubles among its sources. Before the build the stage writes the original
voltage fixture `adc_ch0.txt` to `adc_ch16.txt` into the attempt from
[`intel_adc.stimulus_manifest`](../../../tools/n2m/intel_adc.py): channel 1
holds 0.625 V, channel 2 holds 1.25 V, every other channel 0 V, one row each.
An existing file with the fixture text is left alone; a different file under a
fixture name fails the attempt. [`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py)
covers the files and the refusal.

### Installed Intel memory model

Under Verilator none of this section applies: a `verilator` target's
`vendor_model: "intel-memory"` is the recorded synthesis binding and the stage
compiles the repository double. The retired Questa adapter required the
installed source set pinned in [dependencies.json](../../../tools/n2m/dependencies.json).
It found `quartus/eda/sim_lib` beside the selected Questa
distribution, or took `--intel-sim-lib <directory>` explicitly; the builder no
longer accepts that option (it fails argument parsing). Each required source had to
exist and match the supported hash before cache reuse or compilation. A missing,
modified or wrong model fails; there is no portable fallback. Repository HDL
that defines a shadow `altsyncram` or `altsyncram_body` is rejected.

Each attempt compiles the unchanged source into its own `n2m_altera_mf` library,
maps that library in the run directory, and binds through `vsim -L n2m_altera_mf`.
The record's `options.vendor_model` retains release, source paths/hashes,
compilation options and binding options. These and the wrapper/fixture sources,
parameters, dependency pin and builder options enter the fingerprint. Updating
an approved pin changes the fingerprint; removing/changing an installed source
cannot reuse an older PASS. Vendor source is never copied into tracked files.

`intel_mixed_mode_instances` named the exact vendor instances expected to emit
the reviewed model's mixed-port coercion warning. This inventory was part of
the Questa descriptor and fingerprint; no `verilator` target declares it (the
Python `questa` targets keep theirs until their migration), and the validator
refuses it under `verilator` because the double emits no coercion diagnostic. The forbidden collision it classified is checked under both
simulators by the wrapper's `INTEL_RAM_MIXED_PORT_A/B` assertions, which
`intel-memory-collision` witnesses. Only the pinned source's exact two-line time-zero
diagnostic is classified, and only during runtime. Missing, duplicate,
wrong-instance, wrong-time and other warnings fail. `explained_diagnostics`
records each original pair, source hash and reason; raw logs remain unchanged.
The exception applies only to the forbidden collision described by the memory
MAS. Synthesis must use the same reviewed model source and must not produce
Quartus critical warning 15003.

The pinned ADC model has a separate, exact elaboration diagnostic profile:
seven protected-model width messages, nine ignored `$rewind` return messages,
and two messages for its unused FIFO `eccstatus` output. The same profile occurs
with 50 MHz and 25 MHz control clocks. The protected internal widths cannot be
inspected; this classification does not prove arbitrary ADC configurations.
Actual channel/sample/lock recovery checks and fitted product port/clock checks
remain required. The ADC classifier checks source hashes, complete messages,
locations, counts and summary lines. Any drift or additional warning fails.
Raw logs and the complete profile remain in `explained_diagnostics`; no simulator
warning suppression is enabled.

The [shared memory MAS](../../src/rtl/common/MAS_memory_primitives.md) owns the
same-instance simulation/synthesis rule and the narrow supported port shapes.
Missing-model and cache host tests use controlled original bytes and fake
execution; only actual Intel-model simulation supplies behavior evidence.

The `intel-memory` FPGA target retains the four MAS configurations with virtual
system request and observation ports. A real pixel-domain producer outside
the wrapper alternates read-enable and advances through addresses 0–23039.
Its sixteen launch registers use the existing pixel clock and reset. There
is no fictional off-chip pixel input budget. The audit checks the exact
63 system input names, all existing timing gates, and setup/hold paths from
every pixel request register into memory at all three timing corners. Each
path must use the same pixel launch/capture clock and have nonnegative slack.
It also checks four logical RAM shapes and ten fitted M9Ks. Fitted atom checks bind data and byte lanes, system/pixel
clocks, B address/read-control clocks, unregistered outputs, disabled B writes,
and absent memory clear/initialization. The fitter's physical new-data mode
may include NBE handling; the MAS permits simultaneous A read/write only with
all public lanes enabled, where that mapping preserves the defined result.

The `memory-stores` FPGA target constrains the seven direct-profile stores at
25 MHz with virtual service inputs and outputs, including explicit packed-struct
member names for the paired OAM port. Its checker requires the exact
seven logical depths, 395,640 bits and 52 fitted M9Ks. It checks both port
register stages, the common clock, disabled B writes, whole-byte enables,
physical bit inventory, and absent primitive reset/initialization. The ordinary
timing and diagnostic gates still apply. This proves the raw storage slice;
CPU routing, arbitration and full-system initialization require their own
composition evidence in the [memory contract](../../src/rtl/memory/MAS_memory.md).

### Registered target execution

Run an authorized registered target with default or explicit Questa:

```powershell
python tools/build.py sim test builder-smoke --sim questa --tag questa-smoke --json
python tools/build.py sim test tile-pixel --sim questa --questa-bin <directory> --tag questa-tile --json
python tools/build.py sim test tile-pixel-corrupt --sim questa --tag questa-corrupt --json
```

`--questa-bin` selects the directory containing `vlib`, `vmap`, `vlog`, and
`vsim`; omit it to resolve those executables on PATH. Missing or invalid explicit
selections fail without fallback. No command changes the caller's
environment variables or license settings; the FPGA build's process-only
[allocator override](#quartus-allocator-override) is the one recorded exception.
Versions and executable hashes are recorded; `vlib` has no version query, so its path and hash identify it.

The target registry owns seed, expected exit and signature rules. Each Questa attempt creates an isolated library under
`compile/questa/<target>/<attempt>/` and local mappings in its compile and run
directories. A retained `run.do` uses the same finish/error handling as the
[doctor](#environment-doctor). Logs, mappings, macro, library, VCD/WLF files,
commands, and input/tool hashes remain beneath the tag. Unexpected warnings,
errors, timeouts, or missing signatures fail; expected nonzero targets require
their full diagnostic and reject additional errors.

### Feedback selection gap

Required validation still follows the [PR check policy](../../agents/pull-requests.md#hosted-and-local-checks).
Conservative affected-test selection and shared fixture preflight are planned in
[the verification feedback redesign](https://github.com/amichai-bd/nand2mario/issues/507).
Until implemented and reviewed, that plan does not replace required checks.

### Test wall budget

Ordinary simulations have a maximum 300-second total wall budget. Target at most 120
seconds per simulation and 300 seconds aggregate for ordinary pre-merge checks;
declare broader milestone aggregates before execution. A target that demonstrably
needs more may [declare an allowance](#declared-wall-allowance) above 300 and up to
900 seconds; 300 remains the default for every target that declares nothing. The user's bounded
Mooneye authorization permits exactly `mooneye-reg-f`, `mooneye-corrupt` and
`mooneye-missing` up to 1500 seconds (25 minutes) total each. The three-case
aggregate is at most 75 minutes. This exception changes wall time only; selected
source, models, simulation-time watchdogs, complete signature and fault criteria
remain unchanged. No unlisted target, environment setting or public numeric option
extends its budget. `python tools/build.py sim test` supervises
the complete worker process tree: discovery, preparation, compilation, simulation
and checking share the same budget. The absolute deadline starts before record
preparation and process launch. Reserve 12 seconds for cleanup, leaving at most 288
seconds for ordinary worker execution or 1488 seconds for those three named cases.
The worker runs as an owned process tree
([process_tree.py](../../../tools/n2m/process_tree.py)): a Windows job object
joined before the worker's first instruction, or a POSIX session group. Expiry
terminates the whole tree at once, including a descendant spawned while cleanup
starts, returns failure and retains a `wall-budget` record with the raw killed
process exit and partial output. Existing attempt artifacts remain partial;
TIMEOUT is never a checked DUT result. Tree termination and pipe draining each
have a five-second cleanup bound, followed by at most two seconds to reap the
immediate worker. Each blocking cleanup timeout is clamped to the remaining
absolute selected budget. `cleanup_complete: true` requires the job to report no
active process and the pipes to drain within those bounds; otherwise the record
carries `cleanup_complete: false` with the surviving pids as `survivors`. Inspect
and stop them before releasing shared tool ownership. Never treat that failure
as a clean exit.

The killed worker never ran the `finally` that releases its tag `.lock`. After
tree termination the supervisor reads the lock's recorded `pid`: a dead writer's
lock is removed and the record and result carry `stale_lock_removed: true`. Any
lock left is named as `lock_left`; when it is unreadable, still the worker's, or
a dead writer's that could not be removed, the result also reports
`cleanup_complete: false`. A lock a live foreign writer holds is left with
cleanup reported honestly. A budget-exhausted tag therefore never turns a later
command into a silent cache hit: its `sim/test/<target>/result.json` was
published `RUNNING` before execution and is never reused.

A target may set integer `timeout_seconds` from 1 through its selected total budget
for its simulator run command: 300 normally, its declared allowance when it has one,
and 1500 only for the three names above.
The supervisor and target validator use the same exact-name selection. The
Verilator build command is bounded by the same selected total budget, so a
large design's C++ compile cannot outlive the wall it shares with the run; the
record's `timing` splits the two. Other preparation commands remain
60 seconds, subject to the overall ceiling. The value enters the fingerprint and
each command records its effective bound. The outer execution deadline takes
precedence over a longer nested timeout. The palette-case native reference
build also has a 300-second nested command limit. Separate environment
preparation is not a DUT test. FPGA compilation remains separately measured
under its owning tool limits.
Independent simulation-time watchdogs remain required. If a milestone cannot complete
within this wall budget, keep it open and report the missing evidence; do not
schedule a longer run or shorten its oracle to claim completion. An explicitly
authorized acceptance revision must name the new matrix and leave missing proof
open, as in [v0.5](../../src/dv/v05/SPEC.md#revised-milestone-matrix).

Elapsed time is captured before final evidence-file writes. OS scheduling,
process launch and synchronous filesystem calls are not preemptible Python
timeouts; the supervisor does not claim to measure or bound those final writes.
Report cleanup failures and measured overruns honestly. Changing timeout metadata
invalidates exact target cache fingerprints. Retained behavior evidence may be
qualified against unchanged RTL, models, stimulus and oracles, but is not a
fresh300-second PASS; the 537.281-second six-frame baseline remains historical.

Backend, tool identity, source, target, seed, or runner changes invalidate cache.
Damaged artifacts also invalidate it. A matching successful result may be
`CACHED`, including a verified expected-failure target. Cache reuse performs no
simulation or runtime license checkout; use `--rebuild` for fresh evidence.
The failing smoke target still reports FAIL. Discovery failures retain their
diagnostics and request record under `discovery/<attempt>/` and invalidate any
previous success for the requested target.

Coordinate the licensed execution slot with the root orchestrator before actual
runs. Where the installation limits concurrent sessions, serialize builder,
doctor, standalone and regression invocations, including all regression children.
Release the slot only after those processes finish. Retain license-contention
failures as failures; retry once the competing run ends, with fresh evidence.
Do not kill another author's simulator or change license settings to bypass it.

The [gap register](../../preflight-gaps.md#gap-008-verification-baseline) records
the licensed tests established by this integration and outstanding coverage.

### Regression subsets

`regress <name>` runs one subset declared in
[`src/dv/builder/regressions.json`](../../../src/dv/builder/regressions.json)
and reports one aggregate result with a per-target outcome. Subsets are declared
in the repository, never assembled on the command line; an unknown name fails
with `unknown regression subset: <name>` before any simulator time is spent.
The file holds `version` 1 and a nonempty `subsets` object. Each subset has
exactly:

- `tier`: `ordinary`, `transport` or `milestone`, the
  [verification tier](../../src/dv/integration/SPEC.md#verification-tiers) the
  subset serves;
- `purpose`: a nonempty sentence saying what the subset proves;
- `budget_seconds`: an integer aggregate wall budget from 1 through the sum of
  its members' selected [per-target budgets](#test-wall-budget).

A subset carries no target list of its own. Its members are the
[catalogue](#test-catalogue) simulation targets labelled with the subset's own
name, in name order, so the repository holds one list of tests rather than two.
A subset whose label names no catalogue target declares nothing and fails.

An `ordinary` subset cannot declare more than 300 seconds, the pre-merge
aggregate guidance. Any subset above 300 seconds is a broader declared
aggregate: `regress` refuses it unless `--broader` is passed, and records the
flag. Every declared subset is validated whenever the file is read, so one bad
declaration fails every `regress` invocation. Every member of the selected
subset also passes the target validator before the first child runs.

A member registered `simulator: "questa"` is reported `SKIPPED` with reason
`questa-retired` before any child is launched, listed in the aggregate's
`skipped`, and counts as neither a pass nor a failure; `pre-merge` therefore
reports `tile-pixel: SKIPPED questa-retired` until that target migrates.
Members run in order, each as the `sim test` worker under the same tag with the
regression's `--seed` (default 1), `--rebuild` and `--verilator-bin`. The regression supervises each child exactly as a standalone
`sim test` is supervised: the child keeps its own selected wall budget and
declared allowance, capped by the aggregate seconds remaining, and its one
`wall-budget` record notes the cap as `wall_ceiling_seconds`. A member reached with fewer than 13
seconds left is `SKIPPED` without launching. A member is `PASS` only when its
child exits 0 with a `PASS` result; anything else, including a child wall-budget
expiry, is `FAIL` with the child's error. A child killed at its wall budget
never releases the tag `.lock` it holds; the supervisor removes that dead
writer's lock and the member carries its `stale_lock_removed`, so later members
and the aggregate publish take the tag normally. A lock the supervisor left is
carried as the member's `lock_left`: the aggregate is still reported with the
lock error appended, the tag stays `RUNNING`, and `clean` refuses it while its
writer is alive. A `CACHED` member is a valid reuse of
unchanged inputs; use `--rebuild` for fresh evidence. Later members still run
after a failure, so the aggregate reports every outcome.

The aggregate is `PASS` only when every member passes within the budget.
Otherwise it is `FAIL` and the error names each non-passing member and its
status, for example `regression builder-fault failed: builder-smoke-fail FAIL`.
The result records the subset, tier, purpose, budget, `broader`, seed, the
subset file hash, `targets` keyed by name with status, cache, exit code,
elapsed seconds, error or skip reason and the child `result.json` path, the
`failed` and `skipped` lists, elapsed seconds and provenance. It is published as
`workdir/builds/<tag>/sim/regress/summary.json` and as the tag's `manifest.json`.
A passing child moves `workdir/latest.txt` as any `sim test` does; unless the
aggregate is `PASS`, the regression restores its previous content (or absence)
before it returns. Children take the tag lock
one at a time; `sim/regress/.lock` holds the tag for the whole regression, so a
second `regress` on the same tag fails as locked. Serialize regressions with
other licensed runs as [above](#test-wall-budget).

#### Declared wall allowance

300 seconds is the default and stays the default. A target that measurably cannot
finish within it declares its own allowance in `src/dv/builder/targets.json`:

```json
"example-target": {
  "wall_allowance": {"seconds": 420, "reason": "measured 289-second run leaves no room for setup and checking"}
}
```

`seconds` is an integer above 300 and at most 900, the hard ceiling. `reason`
is a nonempty string recording why the target needs the time. Both keys are
required and no other key is allowed. A declaration above 900, a non-integer or
out-of-range value, a missing or empty reason, and an unexpected key each fail the
target validator and the supervisor with an error; nothing is clamped silently.
The supervisor records the selected `wall_limit_seconds` and the
`wall_allowance_reason` in the `wall-budget` record. A target that declares no
allowance keeps exactly 300 seconds, and the reserved 12 cleanup seconds apply to
the selected budget unchanged. The allowance is not an environment or command-line
option and cannot extend the three named Mooneye cases. Declaring one changes
target metadata and so invalidates that target's cache fingerprint.

## Environment doctor

```bash
python3 tools/build.py doctor --json
python3 tools/build.py doctor --verilator-bin <directory> --json
```

```powershell
python tools/build.py doctor --profile environment --quartus-bin <directory> --uart-port COM5 --json
```

Executable discovery uses PATH or explicit directories, never changes global
PATH, and never falls back from an explicit selection. Tool versions are recorded;
commercial installations are user-provided, not bootstrapped or assumed pinned.
The [tool provenance](../../../tools/sim/THIRD_PARTY.md) owns installation boundaries.

Each invocation gets fresh logs and a fresh Verilator `obj_dir` under
`workdir/builds/<tag>/doctor/<attempt>/verilator/`. Source/runner hashes, commands,
versions, artifact hashes, and per-check outcomes remain in ignored build evidence.
Readiness is never cached. On WSL every profile runs the Verilator smoke and
checks 22 reset, count, and wrap observations.

The default profile checks Verilator; the environment profile adds the remaining tools:

- Verilator (WSL only): `verilator --version` must report a `Verilator <release>`
  banner, recorded as `version` and `release`. The check builds
  [`builder_smoke.sv`](../../../src/dv/builder/builder_smoke.sv) with
  `--binary --timing --trace-vcd --x-initial unique` into `obj_dir/smoke`,
  then runs it with `+seed=1 +verilator+rand+reset+2` and requires the exact
  `PASS builder-smoke seed=1 checks=22` signature. It then runs the same binary
  with `+inject_failure` and requires a nonzero exit carrying the exact
  `count cycle=3 expected=7 actual=3 seed=1` diagnostic, recorded under `fault`.
  Any `%Warning`, `%Error` or `%Fatal` line in the build or the positive run
  fails; Verilator lint warnings are never demoted with `-Wno-fatal`. Timeouts,
  a missing signature and a fault that does not fail all report FAIL. The
  check removes `SALT_LICENSE_FILE`, `LM_LICENSE_FILE` and `MGLS_LICENSE_FILE`
  from the child environment and records `license` as none consulted, so a
  PASS cannot depend on a license. `--verilator-bin <directory>` selects the
  directory holding `verilator`; otherwise it is resolved on PATH. The compile
  step has a 300-second bound; the runs keep the 60-second default.
- Verilator (Windows): no simulator runs. The `verilator` check reports the
  informational status `NOT_APPLICABLE` with the detail
  `not applicable; simulation runs on WSL Linux: python3 tools/build.py doctor`,
  and `untested` gains `Verilator smoke`. That status never lowers the doctor
  result: a healthy Windows environment profile (Quartus, JTAG and UART identity
  all `PASS`) ends `PASS`/exit 0 with `readiness` `complete` and updates
  `workdir/latest.txt`. The Windows simulation profile has no applicable check;
  it ends `PASS`/exit 0 with `readiness` `partial`, because it establishes
  nothing. Windows is the FPGA-side identity preflight, not simulation readiness.
- Quartus: report version and edition. Lite needs no license file; other editions
  report unverified licensing. Unexpected diagnostics fail. Version discovery
  does not prove synthesis. The version output may carry exactly the pinned
  allocator notice classified for the [build flow](#diagnostic-classification);
  the check reuses that single definition, retains the line in the log and in the
  result's `explained_diagnostics`, and continues. Any other text, including
  different `TBBmalloc` wording, still fails. The check launches `quartus_sh`
  with the build flow's [allocator override](#quartus-allocator-override) and
  reports the same `environment` and `notice`, so the doctor and `fpga build`
  see the same Quartus behavior.
- JTAG: invoke only `jtagconfig` enumeration. Exactly one USB-Blaster chain must
  report `10M50DA`; `--jtag-cable <index>` selects among multiple chains. This is
  reported identity, not wiring, voltage, or programming proof.
- UART: Windows CIM PnP Ports enumeration, including FTDI virtual COM ports.
  Require a serial `(COM<number>)` name suffix and retain the exact PnP identity;
  exclude parallel ports and malformed names. Select with `--uart-port`, `--uart-vid`,
  `--uart-pid`, or exact `--uart-identity` (the OS PNP identity, which may include
  a serial). Combined selectors must all match exactly one port. No selection
  is a warning; a missing, ambiguous, or unhealthy explicit selection fails.
  Windows must report `Status=OK` and `ConfigManagerErrorCode=0`. Non-Windows
  enumeration is unsupported and reports a warning.

The doctor never opens UART, drives modem lines, sends bytes, programs FPGA memory,
changes JTAG configuration, or proves physical operation. Those follow the
[current authorization](../../agents/bootstrap-plan.md#verification-and-hardware-authorization)
and hardware workflow. No extra Python packages are required.

`PASS`/exit 0 means all applicable checks in the selected profile passed;
`NOT_APPLICABLE` entries are informational and excluded. `WARNING`/exit 2
means requested evidence is incomplete. `FAIL`/exit 1 means a check failed and
takes precedence over warnings. JSON includes `profile`, `simulator`
(`verilator`), `checks`, `tools`, `inputs`, `readiness`, and `untested`;
simulation success is not full environment readiness. Only PASS updates
`workdir/latest.txt`. The record keeps the earlier shape with these changes: the
simulation check is keyed `verilator` instead of `questa`, its result adds
`release` and `fault`, `tools` holds only `verilator`, and `--questa-bin` is no
longer a doctor option. [`test_doctor.py`](../../../tools/n2m/tests/test_doctor.py)
proves the broken-elaboration, runtime, signature, undetected-fault, missing-tool
and Windows cases with controlled doubles; only the WSL run is simulator evidence.

Quartus license scope follows the [Intel 24.3 overview](https://www.intel.com/content/www/us/en/docs/programmable/683472/24-3/design-suite-overview.html).
Installed `jtagconfig --help` defines the read-only enumeration invocation.
The [gap register](../../preflight-gaps.md#gap-008-verification-baseline) records
the doctor's scoped runtime evidence and the [shared baseline](../../src/dv/baseline/SPEC.md). A failed
environment check still reports FAIL; a passing smoke is not full readiness.

## Installation

The [dependency definition](../../../tools/n2m/dependencies.json) pins Python
3.14.5 for the Windows host, Verilator v5.052 by tag and commit, and cocotb
2.1.0 through the [Python lock](../../../src/dv/python/requirements.txt). Host
tests use the standard library. Physical UART commands have an explicit optional
[pinned serial dependency](../../../tools/n2m/host/THIRD_PARTY.md).

A fresh WSL Ubuntu 24.04 machine needs the repository and three steps, each
recorded under `verilator.install` and `cocotb.install` in the dependency
definition: one `apt-get install` line for the build prerequisites, including
`liblz4-dev` because Verilator 5.052 compiles its FST writer against the system
`lz4.h` and links `-llz4` for every `--trace-fst` build; a source
build of the pinned tag into a prefix outside the repository
(`autoconf && ./configure --prefix=<prefix> && make -j$(nproc) && make install`),
because the distribution package (5.020) is below cocotb's 5.036 minimum; and
`pip install -r src/dv/python/requirements.txt` into a venv under
`workdir/builds/python-dv-env/.venv`. Expose `<prefix>/bin` on PATH or pass
`--verilator-bin <prefix>/bin`. Paths with spaces are supported. There is no
simulator bootstrap, automatic download or license configuration command; no
command reads a license variable. Unmigrated Questa targets still expect
`vlib`, `vmap`, `vlog` and `vsim` on PATH or `--questa-bin <directory>` until
their migration under the [simulator policy](#simulator-policy). Recorded
executable versions/hashes identify the installed tool.

## CI execution boundary

[Builder checks](../../../.github/workflows/builder.yml) validate generation
and host contracts. [Tile runner checks](../../../.github/workflows/tile-pixel.yml)
validate standalone host contracts. Both run locally before merge and by
`workflow_dispatch`, per the [PR policy](../../agents/pull-requests.md#hosted-and-local-checks);
neither executes a simulator or reports licensed RTL acceptance, and their
summaries state this limitation. `PR policy` is the only required hosted check.

Actual local simulator positive and deliberately failing runs are mandatory author
and independent-review evidence; they run under Verilator on WSL as targets
migrate. No trusted remote simulation runner is currently configured. The protected trusted-revision route and required product checks
are out of scope while no runner can be hosted;
[GAP-010](../../preflight-gaps.md#gap-010-github-remote-issues-ci-and-pages)
keeps the record. That route, if resumed, requires independent review of concrete workflow/launcher/configuration before
activation; an actual dispatched licensed sample must then prove it. If its
workflow must first land on main for dispatch, review and land the inert bootstrap
before activation and acceptance. The inactive
[controller bootstrap](../ci/SPEC.md) owns its fixed admission and attestation
contract; it does not establish the configured licensed route. Untrusted PR code must never execute on the
physical/self-hosted runner. Missing tools or licensing is a failure, never a
skipped job presented as a successful simulation. Quartus and board CI activation
remain part of that same recorded gap.

## First simulation target

`src/dv/builder/targets.json` defines sources, top module, plusargs, expected exit
class (`zero` or `nonzero`), and nonempty required output signature. The original smoke
fixture checks synchronous reset, counting through 4-bit wrap, and reset again:
22 comparisons on falling edges after rising-edge register updates. Its failure
variant injects expected=7 at cycle 3, where actual=3. Seed is recorded and passed
to the testbench; this directed fixture does not use randomness. A 1 us watchdog
and 60 s host command timeout bound execution. Partial timeout output is retained
in the failing command's log. Unclassified simulator warnings fail the stage.

Add simulation targets to this manifest when their contracts and tests are ready.
The [tile pixel checks](../sim/SPEC.md) use this interface for normal and
expected-corruption runs through Questa.
Software commands use modules under `tools/sw/` and the output boundaries below.
The [software contract](../sw/SPEC.md) defines implemented `sw build`
inputs, deterministic artifacts and independent conformance requirements.

## HDL includes

Simulation and FPGA builds share the [dependency resolver](../../../tools/n2m/hdl.py).
Sources are repository `src/` files. An include must name a literal, canonical
repository path such as `src/rtl/common/macros.svh`. Only `.sv` source files, `.svh` headers and
ASCII path letters, digits, underscore, hyphen, slash and period are accepted.
Relative traversal, missing files, escapes, symlink files, cycles, dynamic names,
extra include tokens and ambiguous source-directory shadow files fail before
cache lookup or compilation. Closure is limited to 256 source/header files.
Comments are ignored; includes in every conditional branch are dependencies. FPGA file-I/O
rejection selects branches using the tool-owned `SYNTHESIS` definition; unknown
conditions retain both alternatives. Guaranteed simulation-only file reads are
excluded from that check, while their source files remain fingerprinted. Source
redefinition of `SYNTHESIS`, malformed conditions and unsupported inline
conditional syntax are rejected. This is bounded guard handling, not a general
preprocessor.
This is deliberately bounded parsing, not a general preprocessor.

The repository root is the compiler include directory for Questa and Quartus. Quartus QSF explicitly defines `SYNTHESIS=1`, matching synthesis dependency inspection and excluding simulation assertion checks/history. Normal Questa compilation leaves this macro undefined. Every transitive header and the resolver implementation is fingerprinted;
a changed header rebuilds the stage. A missing or unsupported dependency cannot
reuse previous success. FPGA headers retain the existing prohibition on external
file reads; constraints retain their separate SDC checks. The
[standalone tile runner](../sim/SPEC.md#standalone-checks) uses the same resolver
and includes its header hashes in each fresh manifest, without caching.

## FPGA build

`fpga build --build-id <32 lowercase hex digits, nonzero>` is a comparison-only option for the
targets that carry an identity macro (`controls_proof` and the `v05` board
targets). It replaces the fingerprint-derived `N2M_CONTROLS_BUILD_ID` /
`N2M_V05_BUILD_ID` constant with the given nonzero value so two builds of
different sources can be compared with `tools/fpga_netlist_compare.py`; the
constant is folded into logic, so fingerprint-derived identities never match
across sources. The record carries `build_id_override: true` and a notice, the
override is part of the cache fingerprint. `fpga program` fails closed: it
programs only an `output/design.sof` still in place beside a readable attempt
`result.json` whose `artifacts` list that file with its current hash, and it
refuses a record that carries the override. A copied, moved or altered `.sof`,
or one without a record, is refused. Other targets reject the option.

The `v05-board` target uses the existing composed system with the physical pins
in the [system contract](../../src/rtl/system/MAS_system.md). It requires a
nonzero producing fingerprint identity through `N2M_V05_BUILD_ID`; generated
assignments and compiled identity must agree. UART TX uses 8 mA drive, KEY0 uses
the established Schmitt-trigger input standard, and unused package pins are
reserved as tri-stated inputs. Only the UART asynchronous first stage is
excepted; all three-corner setup/hold paths to the second stage remain checked,
along with the existing PLL, reset, memory and VGA evidence. Physical and full
milestone acceptance remain separate: [board bring-up](../../src/board-bring-up.md)
records the physical verification and the observed monitor picture, and the
[v0.5 matrix](../../src/dv/v05/SPEC.md#revised-milestone-matrix)
defines composed acceptance.

The composed memory check accounts for every logical store and physical atom:
seven direct-profile stores (52 atoms), four 5760-byte snapshot stores (32),
three dual-clock VGA banks (18), and six UART stores (9). The complete inventory
is 20 logical stores, 111 M9Ks and 761,704 bits. Existing store, VGA and UART
checkers validate their explicit composed hierarchy, clock/reset roles,
initialization, read shape and bit partitions; the outer inventory rejects
missing or extra atoms and inconsistent fitted capacity. Diagnostic placement
targets retain their own scoped evidence.

```powershell
python tools/build.py fpga build builder-smoke --quartus-bin <directory> --tag fpga-smoke --json
python tools/build.py fpga build builder-invalid --quartus-bin <directory> --tag fpga-invalid --json
```

The first command compiles, fits, assembles, and checks the owned MAX 10 fixture.
The invalid target deliberately supplies a negative clock period and must FAIL
with exit 1; it never becomes a passing build. No command programs the board,
opens UART, or proves physical operation. Design-specific PLL/frame/fit evidence
belongs to the [clocking](../../src/rtl/clocking/MAS_clocking.md) and
[VGA](../../src/rtl/vga/MAS_vga.md) owners, using the
[timing contract](../../src/clocks-resets-cdc.md).

The [target registry](../../../src/fpga/de10_lite/targets.json) has exactly
`schema_version: 1` and a `targets` object. Each named target has exactly
`device`, `top`, ordered nonempty `sources` and `constraints` lists, a `pins`
port-to-package-pin object, and a `virtual_pins` port-pattern list. The device
is `10M50DAF484C7G`; top names are identifiers. Inputs are unique existing
repository-relative `.sv` and `.sdc` paths under `src/`, without traversal or
symlink escapes. Physical pins are unique `PIN_<letters><digits>` names; port
names permit an optional numeric or wildcard array index. Physical assignments
use 3.3-V LVTTL. HDL uses the bounded [include contract](#hdl-includes); HDL file reads that are not proven simulation-only and external/dynamic SDC
loads are rejected. SDC permits one literal clock,
delay, exception or uncertainty assignment per line, using the bounded command
set in the [validator](../../../tools/n2m/fpga.py). Collection getters may select
ports, clocks, pins, cells, registers, nets, inputs or outputs; nested bracket
expressions, variables, control/procedure bodies, command chaining and dynamic
commands are unsupported. Comments and line continuations are allowed. Generated
IP, broader Tcl syntax and additional file types need an explicit dependency
extension before use.

`--quartus-bin` is required and resolves `quartus_sh`, `quartus_map`,
`quartus_fit`, `quartus_asm`, and `quartus_sta` from that one directory. All must
report the same version. Record their versions, executable hashes and paths;
never alter global PATH or provision commercial tools. The checked native
flow uses Quartus Prime Lite 25.1std; a different installation must satisfy
the same reports and diagnostics. `--timeout` bounds each tool to 1–3600 seconds
(default 600; discovery at most 60). Each tool runs as an owned process tree
([process_tree.py](../../../tools/n2m/process_tree.py)): a Windows job object joined
before the tool's first instruction, or a POSIX session group. Timeout terminates
the whole tree at once, including a descendant spawned while cleanup starts, and
cleanup is complete only when the job reports no active process. Closing the job
also ends the tree, so a killed builder leaves no tool behind. Partial output is
retained. Missing tools, nonzero exits, and incomplete reports fail.
Tool stdout and stderr share the attempt's binary log file directly; output is
retained while the process runs. After termination, decode UTF-8 with replacement
for the returned text and existing strict diagnostic checks, without rewriting
the raw log. Timeout cleanup allows five seconds for tree termination, five for
reaping and two for fallback reaping; incomplete cleanup remains a failure.

Each request gets an immutable attempt under
`workdir/builds/<tag>/fpga/<target>/attempts/<id>/`. Generated QPF/QSF and the
timing-audit Tcl script live there, with databases, logs, output reports and
images; checked-in configuration/source stays separate. `result.json` in the
target directory is the atomic current result. It becomes RUNNING before input
validation/discovery, so an interrupted or invalid request cannot reuse a stale
success. Failures retain the failed attempt and publish FAIL. Only PASS updates
the shared latest pointer.

Fingerprint input/configuration/runner hashes, explicit tool identity and
timeout. Reuse requires a matching successful result, agreement with its immutable
attempt record, the complete required report/image/configuration inventory,
every retained artifact hash, and revalidated timing evidence; `--rebuild` forces
execution. Cache hits still probe explicit tool versions,
record that discovery, and link the reused immutable result and its artifacts.
They perform no compile or timing run. An altered image/report/source/constraint,
changed tool, or failed forced rebuild prevents stale reuse.

Required evidence includes map/fit/assembler/timing reports, a nonempty SOF,
the successful exact-device fit summary with final timing models, and timing
summary checks for setup, hold and minimum pulse width at Slow 1200mV 85C,
Slow 1200mV 0C and Fast 1200mV 0C. Every reported slack must be finite and
nonnegative with zero TNS. The audit requires zero illegal/unconstrained
clock/input/output setup and hold counts, no ignored SDC assignments, and no
structural timing problems. Missing/malformed evidence fails rather than passing
on the tool exit alone. Keep resource totals and all corner slack values.

### Quartus allocator override

Quartus Prime Lite 25.1 on Windows can exit 3 before doing any work, most
often at PLL generation, when its bundled TBB allocator fails to replace the
`ucrtbase.dll` allocation hooks. The signature is the exact classified notice
`TBBmalloc: skip allocation functions replacement in ucrtbase.dll: unknown
prologue for function _msize` in the failed step's log, followed by a nonzero
exit. It is a host condition of the installed toolchain, not an RTL, target or
constraint defect.

Intel documents [`TBB_MALLOC_DISABLE_REPLACEMENT=1`](https://www.intel.com/content/www/us/en/docs/onetbb/developer-guide-api-reference/2021-11/windows-os-c-c-dynamic-memory-interface.html)
to keep the standard CRT allocator. `fpga build` sets that variable in the
environment of every Quartus process it launches, including PLL and ADC
generation, and the [doctor](#environment-doctor) Quartus check launches with
the same environment. The setting is process-only: the operator's shell, the
host and any other tool are unchanged, and no manual environment variable is
required. The build is explicit about it rather than silently succeeding: the
result and each attempt record carry `environment` with the applied variable,
every recorded command carries the same `environment`, and `notices` holds one
line naming the override. Text output prints that line after the status. If the
notice still appears in a log, [classification](#diagnostic-classification)
retains it unchanged; any other allocator wording still fails. Programming and
JTAG enumeration do not apply the override.

### Diagnostic classification

Keep every diagnostic in the logs and result. Unknown warnings, critical
warnings and errors fail. The following exact messages are classified for this
bounded build flow; different text under the same number fails:

| Diagnostic | Meaning and limit |
|---|---|
| 12125, exact `v05-board` generated PLL, RAM, decode, and mux inventory under the attempt `db/` directory | Quartus 25.1 may select 17 retained generated design units although the generated QSF does not list those database files. No 12125 warning is required. Once one appears, classification requires all 17 exact basenames and messages, one-design-unit/entity counts, and regular files in the owned attempt database. A partial, duplicate, relocated, renamed, or additional 12125 warning fails. |
| 292013, LogicLock requires a subscription | Lite does not provide this optional placement feature. The generated QSF has no LogicLock assignments; this does not excuse missing required IP/tool licenses. |
| 169177, MAX 10 3.3/3.0/2.5-V interface advisory pointing to AN 447 | The fitter reminds the user of electrical requirements. A generated image does not verify wiring, voltage, or physical acceptance; those remain required before use. |
| Exact `TBBmalloc` `_msize` replacement notice | The installed allocator cannot replace that CRT allocation hook. It is not a failed compilation or timing check; retain the notice and require all execution/report evidence. The [allocator override](#quartus-allocator-override) keeps this condition from aborting a launch. |
| `check_timing` virtual_clock = 1, exactly “No virtual clock was found.” | The fixture's I/O delays reference its physical clock. No virtual reference clock is required. Every other structural check still must be zero. |

The installed Quartus messages and `report_ucp`, `check_timing`, `report_sdc`
reports own the diagnostic text and timing observations. Independent review
checks these narrow classifications against the actual retained reports. The
[host tests](../../../tools/n2m/tests/test_fpga.py) inject unexpected diagnostics,
negative/malformed timing, missing evidence, invalid inputs, cache corruption,
tool failures and timeouts. Real positive/invalid-constraint runs prove execution;
test doubles alone do not establish Quartus readiness.

### VGA proof profile

The `vga_proof` top extends the generated-clock proof with the
[frame bridge](../../src/rtl/vga/MAS_vga.md). Its two registered targets use the
shared nominal/upper reference analyses. The generated QSF explicitly defines
`SYNTHESIS=1`, matching synthesis-aware include discovery and excluding guarded
simulation assertions. The original test-card producer is a fit fixture, not a
PPU or a physical monitor result.

[fpga_vga](../../../tools/n2m/fpga_vga.py) owns exact proof hierarchy collections.
Each CDC exception selects its named launching register and one named first-stage
data pin. MAX 10 may map that input to `d` before fitting and synchronous-load
`asdata` after fitting. Only those two exact alternatives are queried; exactly
one must exist. Missing or ambiguous collections fail, and the chosen pins are
retained in each compilation phase's log and the final endpoint report. No clock,
reset or second-stage pin is eligible. Adjacent stage setup/hold reports remain
mandatory. Bounded Tcl tests execute missing/ambiguous selection cases.

Stable-bundle registers and VGA output ports also require complete exact
collections. Each offer-to-capture bundle has paired minimum 0 ns and maximum
20 ns assignments. The minimum explicitly overrides that bundle's hold
relationship, including clock-network delays; it adds no intentional extra hold
beyond the protocol's offer-through-capture/ack stability. The independent Q-to-D
path report still checks the 20 ns bound. Full STA hold/slack checks and adjacent
synchronizer setup/hold reports remain required. The helper also emits the
shared contract's output bounds and retains per-endpoint path and skew reports. These new reports enter the required
cache inventory, and final validation must recompute them from current inputs.
The profile's physical VGA assignments come from the referenced manual table;
an explicit 8 mA drive setting removes an unspecified synthesis choice. It does
not verify the connected load or authorize using an unverified board.

The verifier checks all bundle bits, all output ports, exact skew constraint
scope and adjacent synchronizer endpoints at each of three explicitly selected
operating corners. It also requires the three fitted simple dual-port, dual-clock
RAM rows and matching total memory/M9K usage. Missing, malformed or out-of-bound
records fail. Actual nominal/upper delivery evidence must pass this complete
profile; no generated image is accepted on RAM bit count alone.

### PPU and LCD-control proof profile

The bounded `ppu_proof` target connects the actual PPU to the frame bridge,
with explicitly timed virtual CPU/memory ports. It does not supply [system backing
stores](../../src/rtl/memory/MAS_memory.md),
a complete CPU/system or physical monitor proof. Its nominal/upper
profiles preserve the existing device, generated PLL, manual-derived VGA pins,
three-bank memory shape, complete timing checks and strict diagnostic policy.

In addition to the four original bridge chains, `blank_pix` crosses the request
into the pixel clock and `blank_seen_sys` returns active blank to `clk_sys`.
Each named launch/first-data endpoint is exact; both adjacent-stage setup/hold
checks remain mandatory at all three operating corners. The latter chain must
not inherit a pixel-clock classification from its position in an inventory.
The profile additionally retains setup/hold paths from `blank_active` and
`blank_pix[1]` to all twelve packed RGB output registers at every corner.
The four-level F/A/5/0 value repeats those two registered bits across each RGB
channel. Quartus packs the original plus five duplicates of each bit into
the twelve pins. Both VGA profiles require the exact register-to-pin mapping
in the fitter table and output paths; the LCD profile checks every physical
copy as a blank-control capture. Missing, extra, mispaired, wrong-clock or
negative-slack paths fail.
Only final gray/sync registers launch the registered output-to-pin paths;
existing complete output/skew bounds remain. The skew assignment aggregate
must be nonnegative and at most 2 ns. Individual earliest/latest contributions
may be signed, but each must have magnitude at most 2 ns, nonnegative slack,
and slack equal to required minus actual skew within 0.0011 ns for the printed
three-decimal reports. White selection precedes the
existing final register edge and does not add a cycle.
All additional reports enter immutable-result/cache completeness checks.
The deliberate invalid target still requires the exact missing reset endpoint.

## Source and workspace boundary

- Root `tools/` contains checked-in project automation.
- `workdir/tools/` contains downloaded or provisioned external tools.
- `workdir/cache/` contains reusable downloads and immutable cached data.
- `workdir/builds/` contains tagged build state and results.
- `workdir/logs/` contains bootstrap and doctor logs that have no build tag.

Keep generated build-specific scripts inside their tagged build alongside
commands, inputs, and results.

`workdir/` is ignored and disposable. It must never contain the only copy of
source, configuration, or documentation.

## Repository layout

```text
.agents/skills/       Agent methods
.github/              GitHub templates and workflow entry points
cfg/                  Small, project-wide YAML configuration
src/rtl/              Synthesizable RTL
src/dv/               Verification and regression definitions
src/sw/               Target software and ROM sources
src/fpga/             Board projects and constraints
tools/                 Checked-in build and automation code
wiki/src/              Source-design documentation
wiki/tools/            Tool documentation
wiki/agents/           Agent documentation
workdir/               Ignored tools, cache, builds, and logs
```

Do not create speculative configuration trees. Keep owner-specific input near
its owner. For example, put regression definitions under `src/dv/` and board
constraints under `src/fpga/de10_lite/`.

## Build tags

An explicit tag creates or reopens a persistent build workspace:

```text
python tools/build.py sim test builder-smoke --tag smoke-dev
```

If `smoke-dev` exists, reuse valid stages; rebuild stale stages and their
dependents.

Without `--tag`, the build uses a UTC timestamp:

```text
20260904t142311z
```

If the name exists, append a short numeric suffix. A build tag is a
directory name, not a Git tag.

Tags must be lowercase, filesystem-safe, and at most 48 characters.
Allowed characters are letters, numbers, `.`, `_`, and `-`. Start with a letter
or number; trailing dots and Windows device names are rejected. UTC `t` and `z`
are lowercase to satisfy the same rule as explicit tags.

## Cache rules

Directory names do not prove validity. Each stage has a content fingerprint
containing:

- source input hashes;
- direct dependency result hashes;
- consumed configuration hashes;
- tool name and version;
- command options; and
- test seed when applicable.

Reuse results only when the fingerprint matches and the prior stage succeeded.

- A cache hit reports `CACHED`.
- A changed input rebuilds that stage and dependent stages.
- A failed or interrupted stage is never reused.
- `--rebuild` bypasses reuse for the selected stage.
- A per-tag lock prevents concurrent writers.
- A stale stage is replaced atomically after the new stage completes.

Record publication writes a unique sibling temporary file, closes it, then
replaces the destination without unlinking the old record. Windows access,
sharing, and lock denials (errors 5, 32, 33) receive at most five retries with
10, 20, 40, 80, and 160 ms delays (310 ms total). Other errors fail immediately;
exhaustion propagates the final error. This bounds transient handle contention,
not permanent permissions. How many of those retries a publication actually
spends is not fixed: an antivirus scanner or indexer holding the destination
adds denials of its own, so behaviour is pinned by the preserved record and the
bound, never by an exact retry count. Cleanup attempts to remove only that
operation's temporary file; a cleanup denial must not mask the publication
error. A blocked cleanup can leave that temporary file for inspection. Failed
replacement leaves the old complete record intact. Simulation still publishes
RUNNING before any execution; publication failure aborts the request rather
than reporting success.

Each backend treats compilation and simulation as one stage: any source,
runner module, dependency definition, target configuration, seed, or discovered
tool identity change rebuilds both. Artifact hashes are also checked before reuse.
`check` and `doctor` always rerun. The tagged `.lock` records its writer as
`pid=<n>`, and the writer keeps the file open until it releases the lock. A
command that finds the lock held checks that process: a dead writer's lock is
reclaimed once, with a stderr notice naming the lock and the pid, and the
command's report (a tagged command, a regression or a selection) records
`stale_lock_reclaimed`; the command then runs, and no cached result is ever
served in place of that run. Exactly one command can reclaim a given stale
lock, and a lock a live writer holds is never reclaimed; each platform proves
both its own way:

- Windows: the open handle denies every rename or unlink by another process.
  The reclaim is an atomic rename of the lock to a unique `.lock.stale-<id>`
  sibling, removed only while it still records the dead writer. A rename that
  fails is a held lock. A moved file that records another writer is that
  writer's closed lock and is put back. A put-back that fails, because the
  writer released it meanwhile or a third command already holds a fresh lock,
  never raises; the sibling is removed once the pid it records is dead, and
  every later writer of the tag removes such siblings on entry. The writer
  must close its handle before the unlink, so a reclaimer stalled for the
  writer's whole run can move the closed file in that instant; the writer then
  waits briefly (at most 630 ms) for its own pid to return before unlinking.
  If the wait expires and the put-back lands later, `.lock` records the
  exited writer's pid and the next writer reclaims it under the dead-pid
  policy, with the notice; no second holder is possible either way.
- POSIX: nothing denies a rename or unlink, so the writer also holds an
  advisory `flock` on the lock for the workspace's life, and nothing is ever
  renamed. A reclaimer opens the lock, must take the flock without waiting,
  must find the same inode still at the lock path, and must re-read the dead
  writer's pid from that inode; only then does it unlink, still under the
  flock. A live writer's flock, a fresh lock at the path, or a changed pid each
  refuse the reclaim, and a fresh lock is never displaced. The writer unlinks
  before it closes, so no closed file recording a live pid ever exists.

On both platforms the loser fails as
`tag <tag> was taken by another writer while its stale lock <path> was
reclaimed`. A lock whose
writer is alive, or whose owner cannot be read, refuses the command by name:
`tag <tag> is locked by live pid <n>; confirm its writer stopped before removing
<path>`. There is no age-based lock stealing. Process ids can be reused by the
operating system, so a reclaim decision is about the recorded pid, not about
which program holds it.

Named tags support fast iteration. Timestamp tags preserve isolated run history.
Different tags may share downloaded tools and immutable cache content, but not
mutable stage directories.

`workdir/latest.txt` identifies the latest successful build. It is updated only
after the requested command succeeds.

## Output layout

Implemented commands create only their needed directories. The larger layout
below includes implemented FPGA and software attempts and regression summaries.

```text
workdir/builds/<tag>/
├── manifest.json
├── status.json
├── commands.log
├── scripts/
├── compile/
│   └── questa/
├── sim/
│   ├── test/
│   │   └── <test-name>/
│   └── regress/
│       └── summary.json
├── fpga/
│   └── <target>/
│       ├── result.json
│       └── attempts/<id>/
│           ├── design.qpf
│           ├── design.qsf
│           ├── audit.tcl
│           ├── db/
│           └── output/
└── sw/
    └── <image-name>/
        ├── obj/
        ├── image.gb
        ├── image.map
        ├── image.sym
        └── image.lst
```

Separate compilation by simulator to prevent incompatible library collisions.
FPGA output stays separate because Quartus compilation, fitting, timing, and
image generation form their own flow.

Use `sw/`, not `sw-collateral`:

- `obj/` contains intermediate object files.
- `image.gb` is the final cartridge image.
- `image.map` is the linker memory map.
- `image.sym` contains exported symbols.
- `image.lst` is the compiler or assembler listing.

## Simulation results

An explicitly selected test writes to:

```text
workdir/builds/<tag>/sim/test/<test-name>/
```

A [regression subset](#regression-subsets) member writes to the same
`sim/test/<test-name>/` location, and the aggregate to:

```text
workdir/builds/<tag>/sim/regress/summary.json
```

The implemented simulation stage publishes `result.json` atomically. It records
status, fingerprint, provenance, commands, and hashes of immutable artifacts under
`attempts/<id>/` and `compile/<backend>/<test-name>/<id>/`, with `verilator` as the backend directory. A new attempt never
modifies an old attempt. `sim.log` beside `result.json` is a convenience copy;
the record's hashed paths are authoritative. Each attempt contains `sim.log`,
`result.json`, `waves/`, and `coverage/` (empty until coverage is implemented).

Before execution, the published record becomes `RUNNING`, preventing reuse after
interruption. Completion publishes `PASS` or `FAIL`; a failed forced rebuild
invalidates the earlier success for that stage and preserves both attempts. A
retired target publishes `SKIPPED` with reason `questa-retired` and no attempt.
Discovery or preparation failure also invalidates that target's prior success.
`manifest.json` and `status.json` describe the latest command on the tag. The
latest pointer changes only after command success; it records the last successful
invocation's tag, whose later contents may change when explicitly reused.

`src/dv/builder/regressions.json` defines regression membership. Directory
placement reflects output; it does not define regressions.

## Manifest

`manifest.json` records evidence to explain and reproduce a result:

- build tag and creation time;
- Git commit and dirty-tree fingerprint;
- host and tool versions;
- requested command and options;
- configuration and input hashes;
- completed stages and cache decisions; and
- paths to logs, reports, images, and test summaries.

Do not record credentials, commercial ROM paths, or private ROM hashes in a
committed file. Build manifests remain ignored under `workdir/`.

## Cleanup

`clean --tag <tag>` removes exactly `workdir/builds/<tag>/`, including its
attempts, compile libraries, waves and records, and reports the removed path,
file count and byte total. `--tag` is required; there is no bulk prune and the
command never removes `workdir/` itself, another tag, checked-in tools or
source files. The tag must satisfy the [tag rule](#build-tags), so a path,
`..` or an absolute name fails validation. The command then resolves
the directory and refuses a link, a directory whose resolved parent is not
`workdir/builds/`, a missing tag (`no build tag <tag>`), a tag holding a
`sim/regress/.lock`, and a tag whose `.lock` records a live or unreadable
writer; a dead writer's `.lock` does not hold the tag. Links inside the tag
are removed as links; their targets are untouched and never counted, so the
file count and byte total are the tag's own files. When `workdir/latest.txt`
names the removed tag it is deleted and the result records `latest_cleared`.

## Interface generation

The [interface contract](../../src/rtl/interfaces/MAS_interfaces.md) owns shared
behavior; [cfg/interfaces.json](../../../cfg/interfaces.json) owns numeric values
and ordered layouts. Its [generated table](../../cfg/interfaces.md) is the
checked documentation export.

Run `python tools/n2m/interfaces.py` to regenerate the marked SV package, Python
exports, assembly prelude and Markdown tables. `python tools/n2m/interfaces.py --check` renders
in memory and fails on a missing or changed export, including documentation.
The Builder sequence runs this and the interface unit tests. The normal
wiki renderer publishes the generated Markdown tables as HTML; no separate
hand-maintained HTML copy exists.

The source uses exact integer values, closed object keys, nonempty constant
groups, unique uppercase names and explicit unsigned widths. Record fields are
ordered byte multiples with unique lowercase names. Unknown keys, duplicate
JSON keys, booleans/floats as integers, overflow, invalid references, duplicate
addresses/command IDs, map overlap/gaps and inconsistent ROM/frame sizes fail.
The generator's `validate` function is the executable schema v1. Changing an
existing wire layout or meaning requires a new ABI version, even if the source
schema can still represent it. Unsupported versions fail; no implicit downgrade.

Checked-in generated exports are interface source artifacts required by this
issue. Build-specific output and test logs stay under `workdir/builds/<tag>/`.
Each export records the canonical source SHA-256. The Python software packager
must import `tools/n2m/generated_interfaces.py` and fingerprint it and the JSON;
the builder-owned allowlisted [assembly prelude](../../../src/sw/generated/interfaces.inc)
supplies the same exported names and values as immutable EQU definitions, outside
the target's source tree. Fingerprint this input as required by the
[software contract](../sw/SPEC.md). Do not maintain a second
memory map. SV users import `n2m_interfaces_pkg`.

## Verification baseline runner

`python tools/n2m/baseline.py` composes registered fixture simulations and checks
retained evidence and transaction traces. It is a host entry point alongside
`tools/build.py`; no new dispatcher subcommand is implied. The
[baseline contract](../../src/dv/baseline/SPEC.md#execution-and-regression) owns
its options, regression levels, wall-budget semantics and trace checks.

## Generated clocking inputs

An FPGA target may declare the bounded `pll` definition for `n2m_pixel_pll`:
input period 20000 ps and output multiplier/divisor 63/125. The generator owns
50% duty, zero phase, normal operation and CLK0 compensation. These settings
implement the [clock contract](../../src/clocks-resets-cdc.md), which owns the
selected rates. The `system_divide: 2` field additionally generates
`n2m_system_pll` from the same reference, divide-by-two with LOW bandwidth.
Each instance has its own generated HDL and command log. Other ratios are
rejected. Supported proof tops retain the exact `u_clocking` wrapper hierarchy;
the v0.5 adapter scopes bridge path checks under `u_system`. Other hierarchies
need an explicit checker extension.

`qmegawiz` comes from the explicit Quartus directory. Its executable, ALTPLL
definition/rules/wizard XML and primitive declaration hashes enter the request
fingerprint. The generated HDL, generation command/log and vendor auxiliary
files remain under the immutable attempt. The generated HDL is checked against
the requested parameters and loaded directly; generated QIP Tcl is retained but
not evaluated. Reuse requires this evidence as well as the complete fit/timing
inventory. Generator errors fail the request and remain retained; there is no
automatic retry or acceptance of partial output. A later explicit build request
creates a separate attempt.

Optional declarative `timing` assignments produce owned SDC with checked exact
asynchronous-reset pins and output clock/port collections. Every collection must
match its declared count. Reset exceptions terminate only at named `clrn` pins;
they do not cut synchronized reset consumers or whole clock domains. Output
delays explicitly include source latency. Arbitrary Tcl bodies and external
constraint loads remain unsupported in source SDC.

The MAX 10 ALTPLL lock output contains the vendor's documented event latch when
`areset` is enabled ([PLL control signals, section 2.3.6][lock-guide]). Its raw
`locked` transition clocks a constant-one D input; PLL reset clears the latch,
and output logic still propagates raw lock loss. This is not a periodic datapath
clock. A single-PLL proof has one such `no_clock` row; the parallel system/pixel
wrapper has exactly two. The ADC composition adds its separately checked vendor
row. The builder explains these rows only after checking
the generated functional netlist: latch input/reset/initial state, the lock gate
truth table, and all downstream buffers/fanout through the two lock sampling reset
pins. For parallel PLLs, all 32 combinations of raw locks, event latches and
reference reset release must propagate either lock loss to reset. Bootstrap
runs on the raw reference; the lock sampling pipeline runs on the generated
system clock. The checker resolves the selected D or synchronous-load data
input, including constant/buffer feeder LUTs. Supported LUT, clock-control and register parameter sets are exact; default
constant declarations/assignments and absence of extra drivers are checked.
The installed atom/register model hashes join the generator fingerprint.
Unsupported primitive modes, structural statements, extra consumers, or any other no-clock
row fail. Synthetic topology mutations prove these rejections.

The raw row and vendor netlist remain evidence. All functional unconstrained-path
counts must stay zero. The reference and both generated clocks require setup, hold, recovery, removal, and
minimum-pulse results at every required corner. Exact adjacent reset-stage
setup/hold reports prove the release chain remains timed. CDC/MTBF reports are
retained; their reset-chain identification is not a hardware reliability claim.
The functional netlist writer's exact diagnostic 10905 explains that MAX 10
supports functional, not timing, simulation netlists; TimeQuest supplies timing.
The exact diagnostic 176127 is explained only for the verified system/pixel
pair and its generated file: their distinct required ratios prevent PLL merging.
Bandwidth, routing and other timing diagnostics remain failures.

[lock-guide]: https://docs.altera.com/r/docs/683047/21.1/max-10-clocking-and-pll-user-guide/pll-control-signals
## Software oracle

`python tools/build.py sw oracle --tag <tag> --json` runs the pinned upstream
RGBASM/RGBLINK against original encoding/relocation fixtures. The
[software SPEC](../sw/SPEC.md#implemented-oracle) owns supported hosts, verified
cache/offline behavior, expected-byte checks and retained artifacts. Builder CI
runs this actual software oracle alongside host contract tests; it does not
provide licensed Questa simulation.

`python tools/build.py sw assemble <target> --tag <tag> --json` emits validated
relocatable objects. `sw conformance` runs complete instruction-family coverage
against actual RGBDS; `--mutate` proves a changed encoded byte fails. The
[assembler contract](../sw/SPEC.md#implemented-assembler) owns target/object
schemas, source bounds, cache rules and diagnostics. Shared atomic text records
use explicit LF so deterministic objects have identical bytes across hosts.

`python tools/build.py sw build <target> --tag <tag> --json` links and packages
validated objects into the explicit direct-profile image. `sw link-conformance`
compares actual RGBDS linked bytes/symbols and independent header/checksums,
including deliberate relocation/checksum mutations. The
[linker contract](../sw/SPEC.md#implemented-linker-and-packager) owns layout and
output schemas, placement, entry eligibility, complete cache inventory and
failure publication. These software commands share the existing tag lock and
manifest handling and do not claim physical or CPU verification.

Version-two software targets declare original shade sources and authorship.
`sw assemble` and `sw build` convert them into immutable ASSET inputs with the
same tag/cache/failure rules. `sw asset-conformance` verifies the original fixture
with an independent decoder; plane/bit-order mutations must fail. The
[asset contract](../sw/SPEC.md#original-assets) owns schema, ordering, diagnostics
and retained evidence. No licensed simulation is involved.

## Preloaded execution target

A declared simulation driver may set boolean `preload` to select the
[validated preload boundary](../../src/dv/preload/SPEC.md). Its Python peer
prepares the software image and initialization files before it publishes
readiness. The builder rechecks the image and every declared
initialization-file hash after the peer is ready and immediately before
launching the run; missing or changed artifacts fail the attempt and reap the
peer. Under Verilator the run is the [Verilator peer driver](#verilator-peer-driver);
the retired `questa` targets used the same peer through their Tcl scripts.
Generated files remain under the immutable attempt directory. This target is
separate from real-UART loading and does not replace its checks.


## Python fixture preflight

`python tools/build.py sim preflight TARGET --tag TAG --json` validates one
Python target and its catalogue entry, declared source/import closure and actual
selected wrapper/test import in a fresh process (30-second bound), then
executes the same fixture preparation and preload verification as simulation.
It does not discover a simulator or acquire a simulator/board resource. The tag is
exclusive; generated files and measured host time remain under `workdir/builds`.
The existing whole-process supervisor enforces300 seconds, including its normal
cleanup reserve; target-specific simulation allowances do not extend preflight.
Use the pinned cocotb 2.1.0 environment for cocotb targets; missing
modules or symbols fail before preparation. No dependency installation is implicit.
This is host preparation, not compilation, RTL execution or behavior acceptance.

A declared preload that produces no manifest fails with its preload name and
prepare-dispatch diagnostic. Normal Python preparation applies the same manifest
and setup checks before compile/run commands. Generated preload files remain
hash-checked; the two source probes compare complete shared sections with a fresh
source build.

The initial explicit source probes cover `entities-render305` variants (all174
uploaded tiles, including unused source tiles) and `entities-oam305` groups
(selected ordinary source writes against existing scratch/state/preservation
checks). They reuse the independent SM83 source model with finite instruction
bounds, not simulator traces. Neither changes the runtime oracle. The renderer
stops at LCD enable; OAM stops at its source terminal/HALT. Runtime retirement,
DMA/pixels, held pause, END and fault acceptance remain mandatory.

Results name each applied check; bank/scratch probes outside these two families
are **not applicable**, not a claim of equivalent coverage. External Mooneye
preparation still uses its pinned-tool workflow and is explicitly refused by
this standalone command. A successful preflight is not a reusable simulation
PASS and does not replace required suites. Unknown or changed inputs must still
meet their existing acceptance. The finite host mutation checks are in
[the preflight tests](../../../tools/n2m/tests/test_fixture_preflight.py).

### Advisory affected-test report

`python tools/build.py tests affected --base REF --json` explains impact against
an explicit Git commit using the current catalogue and simulation input lists.
It does not run tests, accept prior evidence, change `tests run`, or replace the
required PR checks. Each entry explains selection or an input-equal review
candidate. A candidate still needs a valid prior result, matching tool/runtime
identity and independent scoped review.

Standalone host dependency closure is unknown, so host units remain selected.
New, deleted, renamed, unmapped, tool, configuration or catalogue changes force
conservative fallback. Invalid input closure, dynamic data/import behavior,
preloads/drivers, non-Python and unresolved import qualification select the
corresponding simulation too. Candidates are restricted to declared modules with plain imports and call-free
function/data bodies. Only the literal no-argument `@cocotb.test()` entry
decorator is qualified; other calls, attributes, decorators, classes, context
managers, comprehensions and implicit callable constructs remain selected. This
is a small positive subset, not general Python dependency analysis. Every
declared imported Python module must also qualify. Candidates carry exact
repository input hashes against the base; byte differences, including checkout line endings,
prevent equality. The report is advisory preparation cost, not proof of faster
delivery or permission to omit pixel, state, mutation or completion gates.
