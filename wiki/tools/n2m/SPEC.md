# Build system

Status: `doctor`, `check`, Questa `sim test`, and MAX 10 `fpga build` implemented; other stages planned.

## Purpose

The [PRD](PRD.md) owns the purpose and acceptance links.

The entry point is:

```text
python tools/build.py <command> [options]
```

`tools/build.py` is a thin dispatcher. Command logic belongs in small modules
under `tools/n2m/`.

## Available commands

```powershell
python tools/build.py doctor --json
python tools/build.py check --tag builder-check --json
python tools/build.py sim test builder-smoke --tag smoke --seed 1 --json
python tools/build.py sim test builder-smoke --tag smoke --json
python tools/build.py sim test builder-smoke-fail --tag deliberate-failure --json
```

The second identical simulation reports `CACHED`. The deliberate-failure target
must exit 1 and retain its mismatch log and waveform. Other successful commands
exit 0; errors exit nonzero. `--json` emits one result object on stdout.

`doctor` defaults to `--profile simulation`: it compiles, elaborates and runs
a checked Questa smoke. Quartus and devices remain explicitly untested in this
profile. See [environment doctor](#environment-doctor).
`sim test` proves compile, elaboration, run, and the target's expected signature.
`check` runs host contracts with controlled Questa doubles; these are not RTL
or license evidence.

Questa is the sole supported simulator and the default. `--sim questa` remains
an optional explicit spelling. Retired selections (`auto`, `icarus`,
`wsl-icarus`) and Icarus/WSL executable options fail argument parsing. Missing
tools fail with diagnostics; there is no fallback simulator.

## Questa simulation

Run an authorized registered target with default or explicit Questa:

```powershell
python tools/build.py sim test builder-smoke --sim questa --tag questa-smoke --json
python tools/build.py sim test tile-pixel --sim questa --questa-bin <directory> --tag questa-tile --json
python tools/build.py sim test tile-pixel-corrupt --sim questa --tag questa-corrupt --json
```

`--questa-bin` selects the directory containing `vlib`, `vmap`, `vlog`, and
`vsim`; omit it to resolve those executables on PATH. Missing or invalid explicit
selections fail without fallback. No command changes
environment variables or license settings. Versions and executable hashes are
recorded; `vlib` has no version query, so its path and hash identify it.

The target registry owns seed, expected exit and signature rules. Each Questa attempt creates an isolated library under
`compile/questa/<target>/<attempt>/` and local mappings in its compile and run
directories. A retained `run.do` uses the same finish/error handling as the
[doctor](#environment-doctor). Logs, mappings, macro, library, VCD/WLF files,
commands, and input/tool hashes remain beneath the tag. Unexpected warnings,
errors, timeouts, or missing signatures fail; expected nonzero targets require
their full diagnostic and reject additional errors.

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

## Environment doctor

```powershell
python tools/build.py doctor --profile environment --questa-bin <directory> --quartus-bin <directory> --uart-port COM5 --json
```

Executable discovery uses PATH or explicit directories, never changes global
PATH, and never falls back from an explicit selection. Tool versions are recorded;
commercial installations are user-provided, not bootstrapped or assumed pinned.
The [tool provenance](../../../tools/sim/THIRD_PARTY.md) owns installation boundaries.

Each invocation gets fresh logs and Questa libraries under
`workdir/builds/<tag>/doctor/<attempt>/`. Source/runner hashes, commands, versions,
artifact hashes, and per-check outcomes remain in ignored build evidence.
Readiness is never cached. Every profile runs the Questa smoke and checks
22 reset, count, and wrap observations.

The default profile checks Questa; the environment profile adds the remaining tools:

- Questa: compile and run that same source, requiring its checked completion
  signature. A compile-only success does not prove elaboration or a runtime
  license. Timeouts, warnings, error diagnostics, and missing signatures fail.
  A retained `run.do` macro handles breaks and errors. With `-onfinish stop`,
  only a normal `$finish` stop exits zero; fatal or other breaks, macro errors,
  and return without `$finish` exit nonzero. The checked signature is still
  required after a zero exit.
- Quartus: report version and edition. Lite needs no license file; other editions
  report unverified licensing. Unexpected diagnostics fail. Version discovery
  does not prove synthesis.
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

No command opens UART, drives modem lines, sends bytes, programs FPGA memory,
changes JTAG configuration, or proves physical operation. Those follow the
[current authorization](../../agents/bootstrap-plan.md#verification-and-hardware-authorization)
and hardware workflow. No extra Python packages are required.

`PASS`/exit 0 means all checks in the selected profile passed. `WARNING`/exit 2
means requested evidence is incomplete. `FAIL`/exit 1 means a check failed and
takes precedence over warnings. JSON includes `profile`, `checks`, `readiness`,
and `untested`; simulation success is not full environment readiness. Only PASS
updates `workdir/latest.txt`. This extends the previous binary exit contract.

Quartus license scope follows the [Intel 24.3 overview](https://www.intel.com/content/www/us/en/docs/programmable/683472/24-3/design-suite-overview.html).
Installed `jtagconfig --help` defines the read-only enumeration invocation.
The [gap register](../../preflight-gaps.md#gap-008-verification-baseline) records
the doctor's scoped licensed runtime evidence and the completed shared baseline from [#31](https://github.com/amichai-bd/nand2mario/issues/31). A failed
environment check still reports FAIL; a passing smoke is not full readiness.

## Installation

The [dependency definition](../../../tools/n2m/dependencies.json) pins Python
3.14.5. Host commands use the standard library. Install Questa separately under
its license and expose `vlib`, `vmap`, `vlog`, and `vsim` on PATH, or pass
`--questa-bin <directory>`. Paths with spaces are supported. There is no simulator
bootstrap, automatic download, WSL fallback or license configuration command.
Recorded executable versions/hashes identify the installed tool; they do not
claim a pinned proprietary distribution.

## CI execution boundary

Hosted PR/main [Builder checks](../../../.github/workflows/builder.yml) validate
generation and host contracts. [Tile runner checks](../../../.github/workflows/tile-pixel.yml)
validate standalone host contracts. Neither job executes a simulator or reports
licensed RTL acceptance. Their summaries state this limitation. Required
`PR policy` and `Wiki check` protection settings are unchanged.

Actual local Questa positive and deliberately failing runs are mandatory author
and independent-review evidence. No trusted remote Questa runner is currently
configured. [Issue #32](https://github.com/amichai-bd/nand2mario/issues/32) owns
its protected trusted-revision route and required product checks. That route
requires independent review of concrete workflow/launcher/configuration before
activation; an actual dispatched licensed sample must then prove it. If its
workflow must first land on main for dispatch, review and land the inert bootstrap
before activation and acceptance. Untrusted PR code must never execute on the
physical/self-hosted runner. Missing tools or licensing is a failure, never a
skipped job presented as a successful simulation. Quartus/board gates remain #32.

## First simulation target

`src/dv/builder/targets.json` defines sources, top module, plusargs, expected exit
class (`zero` or `nonzero`), and nonempty required output signature. The original smoke
fixture checks synchronous reset, counting through 4-bit wrap, and reset again:
22 comparisons on falling edges after rising-edge register updates. Its failure
variant injects expected=7 at cycle 3, where actual=3. Seed is recorded and passed
to the testbench; this directed fixture does not use randomness. A 1 us watchdog
and 60 s host command timeout bound execution. Partial timeout output is retained
in the failing command's log. Simulator warnings fail the stage.

Add simulation targets to this manifest when their contracts and tests are ready.
The [tile pixel checks](../sim/SPEC.md) use this interface for normal and
expected-corruption runs through either explicit backend.
Future software commands should have separate modules under `tools/n2m/`
and the output boundaries below. They are not implemented yet.
The [software contract](../sw/SPEC.md) defines the planned `sw build`
inputs, deterministic artifacts and independent conformance requirements.

## HDL includes

Simulation and FPGA builds share the [dependency resolver](../../../tools/n2m/hdl.py).
Sources are repository `src/` files. An include must name a literal, canonical
repository path such as `src/rtl/common/macros.svh`. Only `.svh` headers and
ASCII path letters, digits, underscore, hyphen, slash and period are accepted.
Relative traversal, missing files, escapes, symlink files, cycles, dynamic names,
extra include tokens and ambiguous source-directory shadow files fail before
cache lookup or compilation. Closure is limited to 256 source/header files.
Comments are ignored; includes in every conditional branch are dependencies.
This is deliberately bounded parsing, not a general preprocessor.

The repository root is the compiler include directory for Questa and Quartus. Every transitive header and the resolver implementation is fingerprinted;
a changed header rebuilds the stage. A missing or unsupported dependency cannot
reuse previous success. FPGA headers retain the existing prohibition on external
file reads; constraints retain their separate SDC checks. The
[standalone tile runner](../sim/SPEC.md#standalone-checks) uses the same resolver
and includes its header hashes in each fresh manifest, without caching.

## FPGA build

```powershell
python tools/build.py fpga build builder-smoke --quartus-bin <directory> --tag fpga-smoke --json
python tools/build.py fpga build builder-invalid --quartus-bin <directory> --tag fpga-invalid --json
```

The first command compiles, fits, assembles, and checks the owned MAX 10 fixture.
The invalid target deliberately supplies a negative clock period and must FAIL
with exit 1; it never becomes a passing build. No command programs the board,
opens UART, or proves physical operation. Design-specific PLL/frame/fit evidence
belongs to [#79](https://github.com/amichai-bd/nand2mario/issues/79) and
[#80](https://github.com/amichai-bd/nand2mario/issues/80), using the
[timing contract](../../src/clocks-resets-cdc.md).

The [target registry](../../../src/fpga/de10_lite/targets.json) has exactly
`schema_version: 1` and a `targets` object. Each named target has exactly
`device`, `top`, ordered nonempty `sources` and `constraints` lists, a `pins`
port-to-package-pin object, and a `virtual_pins` port-pattern list. The device
is `10M50DAF484C7G`; top names are identifiers. Inputs are unique existing
repository-relative `.sv` and `.sdc` paths under `src/`, without traversal or
symlink escapes. Physical pins are unique `PIN_<letters><digits>` names; port
names permit an optional numeric or wildcard array index. Physical assignments
use 3.3-V LVTTL. HDL uses the bounded [include contract](#hdl-includes); HDL file reads and
external/dynamic SDC loads are rejected. SDC permits one literal clock,
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
(default 600; discovery at most 60). Timeout kills the invoked process tree and
retains partial output. Missing tools, nonzero exits, and incomplete reports fail.

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

### Diagnostic classification

Keep every diagnostic in the logs and result. Unknown warnings, critical
warnings and errors fail. The following exact messages are classified for this
bounded build flow; different text under the same number fails:

| Diagnostic | Meaning and limit |
|---|---|
| 292013, LogicLock requires a subscription | Lite does not provide this optional placement feature. The generated QSF has no LogicLock assignments; this does not excuse missing required IP/tool licenses. |
| 169177, MAX 10 3.3/3.0/2.5-V interface advisory pointing to AN 447 | The fitter reminds the user of electrical requirements. A generated image does not verify wiring, voltage, or physical acceptance; those remain required before use. |
| Exact `TBBmalloc` `_msize` replacement notice | The installed allocator cannot replace that CRT allocation hook. It is not a failed compilation or timing check; retain the notice and require all execution/report evidence. |
| `check_timing` virtual_clock = 1, exactly “No virtual clock was found.” | The fixture's I/O delays reference its physical clock. No virtual reference clock is required. Every other structural check still must be zero. |

The installed Quartus messages and `report_ucp`, `check_timing`, `report_sdc`
reports own the diagnostic text and timing observations. Independent review
checks these narrow classifications against the actual retained reports. The
[host tests](../../../tools/n2m/tests/test_fpga.py) inject unexpected diagnostics,
negative/malformed timing, missing evidence, invalid inputs, cache corruption,
tool failures and timeouts. Real positive/invalid-constraint runs prove execution;
test doubles alone do not establish Quartus readiness.

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

Each backend treats compilation and simulation as one stage: any source,
runner module, dependency definition, target configuration, seed, or discovered
tool identity change rebuilds both. Artifact hashes are also checked before reuse.
`check` and `doctor` always rerun. A lock left by an interrupted process requires
confirming that writer stopped before manually removing the tagged `.lock` file.
There is no age-based lock stealing.

Named tags support fast iteration. Timestamp tags preserve isolated run history.
Different tags may share downloaded tools and immutable cache content, but not
mutable stage directories.

`workdir/latest.txt` identifies the latest successful build. It is updated only
after the requested command succeeds.

## Output layout

Implemented commands create only their needed directories. The larger layout
below includes implemented FPGA attempts and reserves planned regression and software locations.

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
│       ├── summary.json
│       ├── junit.xml
│       ├── level0/
│       │   ├── summary.json
│       │   └── <test-name>/
│       └── level1/
│           ├── summary.json
│           └── <test-name>/
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

A regression test writes to:

```text
workdir/builds/<tag>/sim/regress/level0/<test-name>/
```

The implemented simulation stage publishes `result.json` atomically. It records
status, fingerprint, provenance, commands, and hashes of immutable artifacts under
`attempts/<id>/` and `compile/<backend>/<test-name>/<id>/`, with `questa` as the backend directory. A new attempt never
modifies an old attempt. `sim.log` beside `result.json` is a convenience copy;
the record's hashed paths are authoritative. Each attempt contains `sim.log`,
`result.json`, `waves/`, and `coverage/` (empty until coverage is implemented).

Before execution, the published record becomes `RUNNING`, preventing reuse after
interruption. Completion publishes `PASS` or `FAIL`; a failed forced rebuild
invalidates the earlier success for that stage and preserves both attempts.
Discovery or preparation failure also invalidates that target's prior success.
`manifest.json` and `status.json` describe the latest command on the tag. The
latest pointer changes only after command success; it records the last successful
invocation's tag, whose later contents may change when explicitly reused.

Planned regression layout:

For multiple test seeds, use `seed-<number>/` below the test name. The
level directory contains an aggregate `summary.json`. The full regression also
produces `summary.json` and `junit.xml`.

Verification sources under `src/dv/` will define regression membership and
levels. Directory placement reflects output; it does not define regressions.

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

## Planned cleanup

Timestamp builds can consume significant disk space. These cleanup commands
are planned; the current CLI rejects them:

```text
python tools/build.py builds list
python tools/build.py builds inspect <tag>
python tools/build.py builds clean <tag>
python tools/build.py builds prune --keep 10
```

Cleanup resolves and validates the exact path under `workdir/builds/` before
removal. It never removes checked-in tools or source files.

## Interface generation

The [interface contract](../../src/rtl/interfaces/MAS_interfaces.md) owns shared
behavior; [cfg/interfaces.json](../../../cfg/interfaces.json) owns numeric values
and ordered layouts. Its [generated table](../../cfg/interfaces.md) is the
checked documentation export.

Run `python tools/n2m/interfaces.py` to regenerate the marked SV package, Python
exports, assembly prelude and Markdown tables. `python tools/n2m/interfaces.py --check` renders
in memory and fails on a missing or changed export, including documentation.
The required Builder check runs this and the interface unit tests. The normal
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

<<<<<<< HEAD
## Verification baseline runner

`python tools/n2m/baseline.py` composes registered fixture simulations and checks
retained evidence and transaction traces. It is a host entry point alongside
`tools/build.py`; no new dispatcher subcommand is implied. The
[baseline contract](../../src/dv/baseline/SPEC.md#execution-and-regression) owns
its options, regression levels, wall-budget semantics and trace checks.
=======
## Generated clocking inputs

An FPGA target may declare the bounded `pll` definition for `n2m_pixel_pll`:
input period 20000 ps and output multiplier/divisor 63/125. The generator owns
50% duty, zero phase, normal operation and CLK0 compensation. These settings
implement the [clock contract](../../src/clocks-resets-cdc.md), which owns the
selected rates. Other PLL definitions are rejected.

`qmegawiz` comes from the explicit Quartus directory. Its executable, ALTPLL
definition/rules/wizard XML and primitive declaration hashes enter the request
fingerprint. The generated HDL, generation command/log and vendor auxiliary
files remain under the immutable attempt. The generated HDL is checked against
the requested parameters and loaded directly; generated QIP Tcl is retained but
not evaluated. Reuse requires this evidence as well as the complete fit/timing
inventory. On Windows a verified filesystem short-path alias for the same
attempt accommodates generator path limits. Timeout cleanup still kills the
Windows process tree; a new console process group is not required.

Optional declarative `timing` assignments produce owned SDC with checked exact
asynchronous-reset pins and output clock/port collections. Every collection must
match its declared count. Reset exceptions terminate only at named `clrn` pins;
they do not cut synchronized reset consumers or whole clock domains. Output
delays explicitly include source latency. Arbitrary Tcl bodies and external
constraint loads remain unsupported in source SDC.
>>>>>>> c15debf (Implement clocking control and begin generated PLL timing proof)
