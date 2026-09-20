# Build system

Status: host-native Verilator on Linux and Questa wherever it is installed and
[licensed](#questa-runtime-license), in practice Windows, support `doctor`,
`sim test`, `tests run` and `regress`. `check`, the
[Questa compile gate](#questa-compile-gate) `lint questa`, MAX 10 `fpga build`,
[software build/conformance](../sw/SPEC.md), [host load/control](host/SPEC.md),
the [test catalogue](#test-catalogue), [declared regression subsets](#regression-subsets)
and [tagged cleanup](#cleanup) are implemented.

## Purpose

The [PRD](PRD.md) owns the purpose and acceptance links.

The entry point is:

```text
python tools/build.py <command> [options]
```

`tools/build.py` is a thin dispatcher. Command logic belongs in small modules
under `tools/n2m/`.

## Available commands

Simulation commands run on Linux with Verilator, native or under WSL, or with
Questa wherever its executables and a
[runtime license](#questa-runtime-license) are present. Omit `--sim` for the
host-native default, which is Verilator off Windows and Questa on it:

```bash
python3 tools/build.py doctor --json
python3 tools/build.py check --tag builder-check --json
python3 tools/build.py sim test builder-smoke --tag smoke --seed 1 --json
python3 tools/build.py sim test builder-smoke --tag smoke --json
python3 tools/build.py sim test builder-smoke-fail --tag deliberate-failure --json
python3 tools/build.py sim test builder-smoke --verilator-bin <prefix>/bin --tag smoke --json
python3 tools/build.py sim prepare preload-fixture --tag smoke --json
python3 tools/build.py sim test preload-fixture --tag smoke --prepared <attempt-id> --json
python3 tools/build.py tests validate --json
python3 tools/build.py tests list --level 0 --json
python3 tools/build.py tests run --level 0 --tag level0 --json
python3 tools/build.py tests run --label springtrail --tag springtrail --budget 600 --broader --json
python3 tools/build.py tests record --tag level0 --json
python3 tools/build.py tests mutations --tag mutations --json
python3 tools/build.py tests mutations --confirm --tag mutations-confirm --json
python3 tools/build.py tests closure-trace --unit tools/n2m/tests/test_baseline.py --tag closure-trace --json
python3 tools/build.py regress pre-merge --tag pre-merge --json
python3 tools/build.py regress builder-fault --tag deliberate-aggregate --json
python3 tools/build.py sw library --tag flash-library --json
python3 tools/build.py tools verilator --tag pinned-verilator --json
python3 tools/build.py clean --tag deliberate-aggregate --json
```

`fpga build` and the [Questa compile gate](#questa-compile-gate) run wherever
Quartus and Questa are installed, on Linux or on Windows PowerShell; see
[FPGA build](#fpga-build). `--sim questa` additionally needs a `vsim`
[runtime license](#questa-runtime-license), which the gate does not.
`vendor accept` records reviewed installed vendor bytes as accepted for an
installation's platform; see [accepted vendor sources](#accepted-vendor-sources).
`fpga program` names a missing programmer rather than a host and chooses
between its two backends inside the stage; see
[programming backends](#programming-backends). Writing to a board still needs
the owner's explicit authorization for that run and serialized access to the
board:

```bash
python3 tools/build.py lint questa --tag questa-gate --json
python3 tools/build.py lint questa --inject-fault --tag questa-gate-fault --json
```

The second identical simulation reports `CACHED`. The deliberate-failure target
must exit 1 and retain its mismatch log and waveform. The `builder-fault` subset
must exit 1 naming `builder-smoke-fail`. Other successful commands
exit 0; errors exit nonzero. `--json` emits one result object on stdout.

`doctor` defaults to `--profile simulation`. It compiles, elaborates and runs a
checked smoke in the selected host-native simulator. The Verilator check
consults no license; a Questa PASS records that its runtime checkout succeeded.
Quartus and devices remain explicitly untested in this profile. See
[environment doctor](#environment-doctor).
`sim test` proves compile, elaboration, run, and the target's expected signature
under the selected backend. An unsupported target/backend pair fails before
workspace creation, tool discovery or child launch; there is no fallback.
`check` runs host contracts with controlled simulator doubles; these are not RTL
evidence. It also proves the [test catalogue](#test-catalogue) still
covers every test in the tree, and fails naming the first uncovered file.

## Progressive build menu

Either spelling opens the same keyboard menu:

```text
python tools/build.py -tui
python tools/build.py --tui
```

The menu requires an interactive input and output terminal. Redirected or
non-interactive use exits promptly and points to `--help`; automation continues
to use the ordinary CLI and `--json`. Each screen asks one question. Up and Down
move, Enter selects, and typing filters a list. Backspace edits the filter.
Escape returns to the preceding decision; Escape from the first intent screen
cancels the menu. Long lists show at most ten choices around the current row.

The first decision reaches every top-level builder family: `doctor`, `check`,
`sim`, `regress`, `tests`, `clean`, `fpga`, `sw`, and `host`. It also reaches the
separate [game launcher](host/LAUNCHER.md). Later decisions come from the current
argparse command tree and owning registries. Simulation targets are read from
`src/dv/builder/targets.json` and filtered by the selected backend. Python
preflight lists the registry's Python testbenches. FPGA and software targets,
regression subsets, test levels and labels, external images, build tags, and
peek stores come from their existing registries.
[Recording a wall](#recording-a-measured-wall) lists only the retained runs whose
record holds a measured wall, and asks for a typed tag when this checkout retains
none. Programming lists only
successful, unmodified, in-place `.sof` attempts accepted by the programmer's
record check. Launcher identities come only from those checked `v05-board`
attempts. Package loading lists only immutable attempts accepted by the package
reader.

The menu offers current healthy Windows UART ports from the doctor's read-only
PowerShell CIM PnP query, followed by recent retained selections and manual
entry. Opening a UART selection screen may start that discovery subprocess. It
does not import the serial backend, open a port, drive DTR/RTS or send a byte.
Manual entry accepts `COM` followed by a positive port number and normalizes it
to uppercase before Review.
The selected host command still repeats fresh PnP identity and health checks
before serial open. Recent simulator, Intel-model and Quartus directories come
from retained manifests; manual entry remains available. If ordinary `PATH`
discovery lacks the selected simulator and exactly one retained directory has
all of that backend's executables, the menu preselects its `--verilator-bin` or
`--questa-bin` option. Verilator requires `verilator`; Questa requires `vlib`,
`vmap`, `vlog`, and `vsim`. Stale directories and incomplete tool sets do not
qualify. Zero or multiple qualifying directories leave ordinary discovery in
place. **Advanced options** shows an automatic selection and can replace it or
clear it back to ordinary discovery. These browse-time decisions inspect only
the filesystem and executable search path; tool identification and execution
remain part of the confirmed child command.

Applicable optional flags live under **Advanced options** with the ordinary CLI
defaults. Options that do not apply to the selected simulator, doctor profile,
or mutually exclusive input stay hidden. `--intel-sim-lib` appears only when
the selected live target, regression subset, or test-catalogue selection
includes an Intel vendor-model simulation. FPGA `--build-id` appears only when
the selected live target definition carries an identity macro. The identity-bound `host crc-proof`
and `host keyboard` actions accept a manually reviewed build identity only when
it is exactly 32 hexadecimal digits and nonzero. They also hide
`--endpoint-restarted`. The doctor asks
for scope first: simulation scope then
offers either backend, while the full hardware environment fixes Questa and
Windows because its JTAG discovery is Windows-owned. A simulation-scope Questa
plan names the current host: its
[runtime license](#questa-runtime-license), not an operating system, decides
whether the run proceeds.
`--json` is intentionally absent.

The final screen names the native host and whether the selection builds, runs a
simulation, deletes a build, programs the FPGA, transmits over UART, or launches
a GUI. A runnable current-host command displays the actual Python interpreter.
A foreign-host command uses the repository's portable `python` spelling for
Windows or `python3` for Linux, because the current interpreter belongs to the
wrong host. The relative script and arguments are quoted for POSIX, PowerShell,
or classic `conhost.exe cmd.exe` as required. A PowerShell display uses the
invocation operator. A classic interactive `cmd.exe` display quotes every token
with Windows CRT argument rules, keeping `&`, `|`, `<`, `>`, `(`, `)`, `^`, spaces,
and backslashes inside the token. It refuses values containing CR, LF, NUL, `%`,
`!`, or a double quote because those cannot be presented as one honestly
copyable interactive command; the display is not batch-file syntax. `host
keyboard` names that classic console explicitly. It offers **Run now** only
after a read-only check proves
the TUI's parent is `cmd.exe` and its console window is visible and foreground;
Windows Terminal, PowerShell and WSL get a copy instruction instead. This
display is not the execution mechanism. **Run now** starts
`[sys.executable, <absolute tools/build.py>, ...]` or the existing
`gb_launcher.py` as an argument vector with `shell=False`. Builder selections
therefore re-enter the public dispatcher; `sim test` and `sim preflight` remain
under `test_budget.py` supervision, and every command keeps its locks, records,
progress and exit status. The launcher remains its own one-window process.

No selected operation or child command starts until **Run now** is selected.
The read-only Windows UART discovery subprocess above is the sole browse-time
exception. A foreign-host review shows the native command but offers no run
choice; it never crosses Linux and Windows. Programming, UART transmission,
cleanup and GUI launch cannot occur while browsing, moving back or cancelling.
The terminal restores its prior input and output modes before a confirmed child
starts or the menu exits.

## Human terminal progress

Without `--json`, a single simulation or FPGA command reports live, flushed
stage lines. `[....]` marks work that is running. `[done]` and `[PASS]` name a
completed operation and its measured wall duration. `[FAIL]` names the stage
that stopped and its retained diagnostic path. `[CACHED]` says that checked
evidence was reused; it never presents recorded work as a new execution.

Simulation names the target and backend, tool discovery, each compile or
elaboration command, execution, and the checked result. Its final summary gives
the compile and simulation logs, authoritative `result.json`, retained waveform,
and the current-host command that starts the `v05-board` FPGA build.
FPGA build names Quartus discovery, including target-specific IP identities,
cache checking, generation when applicable,
compile/fit/assembly/timing, the timing audit, optional netlist generation, and
final evidence checking. Its summary gives the immutable attempt record and
checked `design.sof`, followed by the exact `fpga program` command for that
artifact. Arguments that contain spaces or PowerShell metacharacters are
single-quoted, with embedded quotes escaped.
A failed build may name a produced `.sof` only as an unverified artifact; it
never labels that file checked or offers it to the programmer.
A comparison-only result produced with `--build-id` prints no programming
handoff, matching the programmer's existing refusal of that image. Every other
fit prints that handoff for the host that ran it, in that host's own shell and
with the Quartus directory it was given, because programming follows its
installed programmer rather than a host. The `.sof` keeps its repository-relative
path, so programming it from a different checkout needs that image in place
there first. Writing to a board still needs the owner's explicit authorization
for that run and serialized access to the board. The simulation's own
`v05-board` handoff above is the one that writes a `<Quartus-bin>` placeholder,
because a simulation has no Quartus directory of its own to name.

Programming checks the attempt record before JTAG discovery. An early refusal
writes `failure.log` in the program operation directory and names that retained
diagnostic on the failed stage and final summary. A valid attempt reports the
selected cable and device, then reports programming and its explicit success
check separately. Its final summary gives `program.log`; a failed summary adds
`Device state: <state>; no automatic replay` from the
[program record](#program-records). For a build with a
recorded identity it also gives the UART on-wire identity: the byte reversal of
the checked FPGA attempt's `build_id`. A checked `v05-board` attempt carries its
producing target into the program result, and only that playable target places
the identity in a copyable [`gb_launcher.py`](host/LAUNCHER.md) command with an
explicit `<UART-port>` placeholder. Other proof targets never advertise the
game launcher. [Flash programming](#flash-programming) reports the record
check, the chain, the flash program and its success check the same way, then
the measured time, the `.pof` hash and the power-cycle step; its dry run
reports the record check and the written command only.

These handoffs never execute their next command. Linux remains a Verilator host
and Windows PowerShell the launcher host. The `fpga build` handoff
names the current host, because an installed Quartus runs it on either one, and
so does a Questa simulation handoff, because Questa follows its executables and
its [runtime license](#questa-runtime-license), and so does the programming
handoff, because `fpga program` discovers its own programmer. No command silently
crosses a host boundary. The ordinary
hardware safeguards still apply before a person runs the printed programming or
launcher command.
With `--json`, none of these human lines is written and stdout remains exactly
one parseable result object for aggregate and child callers.

## Simulator policy

The supported backends are Verilator v5.052 on Linux, native or under WSL, and
native Questa on any host that has the executables and a `vsim` runtime license.
`doctor`, `sim test`, `regress` and `tests run` accept
`--sim verilator|questa`; omission selects Verilator on non-Windows hosts and
Questa on Windows. `--verilator-bin` belongs only to Verilator.
`--questa-bin` and `--intel-sim-lib` belong only to Questa. Supplying an option
for the other backend fails before discovery. `auto`, Icarus and WSL proxy
backends remain unsupported. Missing tools and license failures are FAIL, never
SKIPPED, and no command falls back to the other simulator.

`--sim questa` requires a `vsim` [runtime license](#questa-runtime-license); it
names no operating system. Discovery decides both halves of availability, so a
host with no Questa fails naming the missing executable and a host with Questa
and no license fails naming the license.

Questa evidence has two parts. The [Questa compile gate](#questa-compile-gate)
is the standing Questa evidence for the product RTL: every PR that changes
`src/rtl` or `src/fpga` records its PASS for the PR head, and the hosted
`PR policy` check refuses the merge without that record under the
[PR policy](../../agents/pull-requests.md#hosted-and-local-checks). The gate
compiles and elaborates without a runtime license. Runtime acceptance, meaning
`sim test`, `tests run`, `regress` and the
[verification tiers](../../src/dv/integration/SPEC.md#verification-tiers), runs
on Verilator on Linux; every registered target declares that backend. Questa
runtime execution stays supported for the targets that declare it and for the
[doctor](#environment-doctor) smoke, which records a successful
checkout when the caller's license environment provides one and otherwise names
the missing [runtime license](#questa-runtime-license). No acceptance
criterion requires a licensed Questa run.

One build tool serves two operating systems. Linux owns Verilator execution.
`fpga program` names a missing programmer rather than a host, and writing to a
board still needs the owner's explicit authorization for that run and serialized
access to the board. Questa runtime execution follows its
install and its license; in practice the licensed host is Windows.
`fpga build` and the compile gate follow their installed tools on either host.
Caches and fingerprints stay per backend and OS under `workdir/`.
[Command ownership](#command-ownership) names the refusals.
Where RTL instantiates
an Intel primitive, the predefined `VERILATOR` macro selects a behavioral double
and Quartus always sees the vendor instance; the
[memory MAS](../../src/rtl/common/MAS_memory_primitives.md) owns that rule.
Four-state assertions are removed during migration as an authorized behavior
change: Verilator runs with `--x-initial unique` and
`+verilator+rand+reset+2`, so an uninitialized read fails by value mismatch
rather than by an `X` check.

Every registry target records its supported [simulators](#simulator-field).
Capability remains explicit per target. A single-target `sim test` of an
undeclared backend is a configuration failure. An area run (`tests run`,
`regress`) reports such a target as `SKIPPED unsupported-backend` by name,
counting it as neither pass nor defect, and never falls back; see
[execution](#execution-and-contention) and [regression subsets](#regression-subsets).

### Command ownership

One build tool serves two hosts. Only physical access and a source build are
operating-system facts; everything else follows the installed toolchain.

Linux owns Verilator simulation. Windows refuses it before any workspace is
taken, reporting `Verilator simulation runs on Linux`, because the
[pinned Verilator](#pinned-verilator-installation) is an autoconf, `make` and
`g++` source build: there is no supported Windows Verilator for discovery to
find. Questa simulation carries no operating-system refusal; see the
[runtime license](#questa-runtime-license). Windows refuses `tools` with
`Pinned host tool installation runs on Linux`, because the pinned Verilator is
an autoconf, `make` and `g++` source build.

`fpga build`, `fpga program`, `lint questa` and `--sim questa` carry no
operating-system refusal. Each discovers its own executables and reports the
real result, so an absent tool fails naming that tool:
`missing explicit Quartus tool: quartus_sh` for the fit,
`missing vlib; select the Questa tool directory explicitly` for the gate and
for a simulation, and `no JTAG programmer found: missing jtagconfig (Quartus)
and openFPGALoader; select a tool directory explicitly` for programming. A
tagged workspace is taken before that discovery, exactly as on the host that
already owned the command.

`fpga program` carried an operating-system refusal while Linux JTAG access was
unverified. It is verified for reading, so the refusal became the
[backend decision](#programming-backends) inside the stage. Writing to a board
still needs the owner's authorization for that run; no command programs a board
on its own.

Every command header and simulation record carries `os` (`platform.system()`),
and caches, fingerprints and compiled objects live under the running host's own
`workdir/`. [`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py)
covers the Verilator refusal, the absence of a Questa one, the programming
refusal, the permitted sides and the Linux fit with a mocked platform;
[`test_questa.py`](../../../tools/n2m/tests/test_questa.py) covers the license
probe, its argv and the missing-tool failure, and
[`test_doctor.py`](../../../tools/n2m/tests/test_doctor.py) the doctor's
license naming;
[`test_lint.py`](../../../tools/n2m/tests/test_lint.py) covers the gate on both
hosts and its missing-tool failure, and
[`test_fpga.py`](../../../tools/n2m/tests/test_fpga.py) the fit's.
[`test_fpga_program.py`](../../../tools/n2m/tests/test_fpga_program.py) covers
the programming refusal naming both programmers rather than a host.

### Questa runtime license

`vsim` is the only Questa executable a run launches that checks out a runtime
license. `vlib`, `vmap`, `vlog` and `vopt` check out none, which is why the
[compile gate](#questa-compile-gate) needs no license on any host: it never
launches `vsim`. `vsim -version` prints its banner without a checkout as well,
so identifying `vsim` proves only that it is installed, never that it can run.

`--sim questa` therefore probes the checkout during discovery, after the four
banners and before any workspace work depends on it. The probe is
`vsim -c -nolog -lic_noqueue -do "quit -f"`: it loads no design, writes no
transcript into the caller's directory, and refuses to wait behind a busy
license server. Its argv, exit code and output join the discovery record on a
pass, and travel on the refusal to the failure `result.json` under
`discovery/`, whose `failure.log` keeps the same output.

Refusal needs both halves: a nonzero probe exit and one of three wordings. Each
means exactly what the vendor prints, no more:

1. `Unable to find the license file` — neither license variable is set. `vsim`
   reads only `SALT_LICENSE_SERVER` and `QUESTA_LICENSE_PROXY`; with
   `LM_LICENSE_FILE` or `MGLS_LICENSE_FILE` set instead it prints this same line,
   so the refusal names only the two that work.
2. The `run 'lmutil lmdiag'` wording — a variable **is** set and the checkout
   failed. It carries no cause beyond that: an unreachable server, a nonexistent
   path, a garbage file and a syntactically valid file with a bogus signature all
   produce byte-identical output. It is matched deliberately, so a configured but
   unusable license is named during discovery instead of part-way into a run.
   `vsim` wraps it across two lines, which is why both the match and the quote
   read the whole output.
3. `Couldn't connect to proxy` — the exchange with the proxy named by
   `QUESTA_LICENSE_PROXY` failed. It does not say the proxy is unreachable: an
   unresolvable name, a refused connection, a listener that accepts and closes at
   once and one that accepts and sends garbage all print it identically. Without
   this wording such a host, holding no license at all, reached the run before
   failing there.

The quoted cause is every line before the closing pair, stripped and rejoined
with single spaces, never a single matched line that would start mid-sentence.
Spacing inside a line stays as `vsim` wrote it, double spaces included.
The command then fails naming the license and quoting that cause, never an
operating system:
`no Questa runtime license: vsim could not validate one. Set
SALT_LICENSE_SERVER, or QUESTA_LICENSE_PROXY, to a license that grants vsim and
retry; vsim reads no other license variable. The Questa compile gate needs none
because it never launches vsim`.

The closing lines are never matched. `Unable to checkout a license.  Vsim is
closing.` and `Invalid license environment. Application closing.` follow every
failed startup checkout whatever the cause, so classifying on them would refuse
any contention at all.

Everything else passes through and is recorded, not refused: a `vsim` broken for
another reason reports its own detail, and a zero exit is a working license
whatever its output mentions. This repository's own contention passes through
too. Its license is one node-locked seat, and a held seat is refused with exit 12
and `an instance of QuestaSim is already running`. That phrase and that exit are
what the record holds, and neither matches any wording above, so such a refusal
reaches the run.

This is why the two Questa paths differ on the same host. The Quartus-bundled
Questa on a Linux host compiles and elaborates the gate to PASS, and the same
installation cannot run `sim test --sim questa`, because only the second needs
the checkout. `doctor --sim questa` reports both: the `questa` smoke fails
naming the license while `questa-lint` passes on the gate tools' availability.
No acceptance criterion requires a licensed Questa run.

#### Known limit: a floating license with every seat taken

On a floating license with no free seat, `-lic_noqueue` turns the queue wait into
the same validation failure a broken license produces, so wording 2 matches and
such a host is refused and told to configure a license it already has. A license
proxy at capacity that declines connections reaches wording 3 the same way, since
accept-then-close prints it. The vendor puts no distinction in either output, so
the probe cannot draw one.

Both halves of this limit are derived from the checkout path and from a socket
standing in for a proxy, not observed: no seats-exhausted license and no Questa
license proxy were available here, and none was sought. The limit is not reachable
on this repository's node-locked license, whose contention is the exit-12 case
above.

## Test catalogue

[`src/dv/builder/catalogue.yaml`](../../../src/dv/builder/catalogue.yaml) holds
one entry per **runnable unit**: every registered simulation target and every
standalone `test_*.py` unittest file in the tree. A runnable unit is the
smallest thing that can be executed alone, which is what makes a recorded
duration meaningful.

The file holds `version` 1, a `labels` vocabulary, a `units` mapping, a
`not_runnable` mapping and optional `external_imports` and `retired` mappings.
Each unit declares exactly:

- `kind`: `sim` for a registered target, `unit` for a `test_*.py` file;
- `level`: `0`, `1` or `2`, single-valued and ordered. Level 0 buys simple
  confidence that nothing broke and is optimised for speed; level 1 is more
  thorough; level 2 is everything. Selecting a level runs every level below it.
- `labels`: a set, orthogonal to level. Every label must be declared in the
  file's own `labels` vocabulary; an undeclared label fails validation.
- `duration_seconds`: the wall of one deliberate measurement, or `null` before
  the first. Running a test never writes it; only
  [`tests record`](#recording-a-measured-wall) does, and it is not edited by
  hand. Nothing is bounded against it: a host unit's
  [CPU budget](#what-one-host-unit-may-spend) is a multiple of the CPU in its
  `measured` conditions, because a wall has no worst case in load and a bound taken
  from one would move with the host rather than with the work. A measured wall is recorded with two decimals and never below 0.01
  seconds, so `0.00` can only mean an entry nothing measured: `tests validate`
  and `check` fail on it by name.
- `measured` (optional): the conditions the recorded wall was measured under, as
  exactly `at`, `commit`, `host` and `wall_cpu`, plus `cpu` where the run reported
  per-child CPU and `build` for a simulation. `cpu` is the CPU that run spent and is
  the figure a host unit's [budget](#what-one-host-unit-may-spend) is a multiple of;
  a unit whose conditions omit it keeps the default budget.
  `at` is the UTC minute of the run, so two entries sharing it were measured in
  one sitting, which is the only span their walls are comparable over; `commit`
  is the first twelve characters of the commit measured; `host` is the operating
  system and machine, such as `Linux-x86_64`; `wall_cpu` is that run's wall
  divided by its own CPU time, or `null` where the host reports no per-child CPU,
  and below 1 where the work ran on more than one core. `build` is the compile
  inside that wall, never more than the wall itself, because a simulation's wall
  is nearly all compile: `baseline-good` measured 44.71 s with 43.45 s of compile
  and 0.02 s of run, and 29.88 s with 28.75 s of compile in the same sitting.
  Every recorded simulation compiles, because the compile directory is keyed by a
  fresh attempt id per run and the only compile-free outcome is a cache hit,
  which is never recorded. An entry may carry no conditions, which says the
  sitting behind its wall is unknown, which is the state of most figures the
  catalogue carries: `baseline-good` records `0.41` and nothing says what produced
  it. Such an entry is not treated as measured for any purpose that needs a
  condition, which is why an unmeasured host unit keeps the default budget rather
  than one derived from a figure with no sitting. An entry may never carry
  conditions without a wall.
- `inputs` (host units only, optional): the repository files or directories the
  unit reads as data, sorted. Its module imports are never listed; they are
  [derived](#host-unit-closure). Declaring `inputs`, even `[]`, asserts that
  the derived modules plus these paths are the unit's whole input closure.

`external_imports` maps a package name outside the tree that a host unit's
import closure reaches, such as `cocotb` or `serial`, to its provenance. An
import that resolves nowhere in the tree, is not a standard-library module and
is not listed here fails `tests validate` as an undeclared import.

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
under `VERILATOR`. It also records `python-v05-continuous`, whose 600-frame
schedule (about 10 s simulated) exceeds the 900-second wall ceiling at the
measured Verilator rate; `python-v05-continuity` is its bounded replacement.

The file is a strict YAML subset so the builder keeps its stdlib-only
dependencies: block mappings, flow mappings, flow sequences, plain and quoted
scalars, and whole-line comments. Inline comments are refused, because a `#`
inside an unquoted value would otherwise be silently truncated. `tests validate`
and `tests run` rewrite nothing, and `tests record` rewrites only the unit lines
it records, so comments and order survive.

### Coverage is a build gate

`tests validate` and `check` both prove the catalogue still covers the tree. A
`test_*.py` file present in the tree fails the build unless it is a catalogued
unit, a `not_runnable` entry, or already an input of a catalogued registry
target — the last case covers cocotb modules, which run through their target
and never alone. A registered target absent from the catalogue, a catalogued
target absent from the registry, and a catalogued path naming no file each fail
the same way. This is the control that stops the catalogue drifting out of date.

Both also check every preload target's
[fixture inputs](#preload-fixtures-under-verilator), for either testbench
kind, so a target that would refuse to run fails here instead of at simulation
time. An input the builder reads but the target does not declare fails as
`registry <target>: preload_inputs omit fixture inputs: <paths>` for a
SystemVerilog target and
`registry <target>: python inputs omit fixture inputs: <paths>` for a Python
one.

### Host unit closure

[`host_closure.py`](../../../tools/n2m/host_closure.py) derives a host unit's
module closure statically from its `test_*.py` file. It follows every import
statement, including ones inside functions and branches, transitively across
the repository in the order the [runner](#execution-and-contention) gives the unit:
the module's own evaluated `sys.path` edits, its directory, the repository root
and `tools/`. Evaluation covers `Path(__file__)` chains with `resolve`,
`parent`, `parents[N]`, `with_name` and `/ 'constant'`, names bound to such
chains once, string constants naming repository directories, and a single
constant beside a caller-supplied root such as `root / 'tools'`. An import no
search directory serves resolves to every module of that name in the tree; an
edit that cannot be evaluated widens every absolute import in the closure the
same way. Both over-approximate and never omit. Generated output under
`workdir/`, `worktrees/` and virtual environments is never an input.

`tests validate` and `check` check every host unit, declared or not: an import
that resolves nowhere, is not a standard-library module and is not in
`external_imports` fails as `undeclared import NAME at line L of PATH`. A
declared unit also fails when an input is missing or outside the tree, when it
declares a module its imports already reach, or when the test module anchors a
repository path at its own location, through `__file__`, that is neither a
declared input, under a declared directory, nor a derived module. A declared
`.py` input is a module the test loads dynamically, for example through
`importlib.util.spec_from_file_location`; its imports are followed too. A
declared child of a wider referenced directory is accepted as the author's
narrowing.

The guard is a positive heuristic, not a proof. Bare string paths such as
`Path('src/sw/x.json')`, and paths a helper reads inside a function from a
root the test passes in, are not detected; the author accounts for them in
`inputs` or leaves the unit undeclared, which keeps it on the
[affected report's](#advisory-affected-test-report) unknown-closure fallback.
A unit whose real closure is the whole tree, such as
[`test_catalogue.py`](../../../tools/n2m/tests/test_catalogue.py), which walks
every test file, stays undeclared for that reason. The declarations are
proved dynamically by
[`tests closure-trace`](#conservativeness-proof), which runs each declared
unit under a file tracer and fails by name on a tracked file read outside its
closure; a declaration change re-runs that trace for the changed unit before
it is trusted.

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

`src/dv/builder/catalogue.yaml` is tracked, so no run writes it. `sim test`,
`tests run` and `regress` leave every tracked file exactly as they found it: a
measured wall goes into that run's own retained record, beside the run that
produced it, and into the command's text output. A `sim test` reports
`Measured <target> <wall>s against <recorded>s recorded (wall/CPU <ratio>)`, a
`tests run` names every unit whose wall stands more than twice from the recorded
figure, and both name the command that would record it. The
[wall budget](#test-wall-budget) record and `tests/summary.json` hold the figures
themselves: a selection carries `measured_walls`, each unit's own
`cpu_seconds` and `recorded_seconds`, and a `drift` list; a `sim test` manifest
carries `timing.locked_seconds` and `timing.locked_cpu_seconds`.

The rule that flags `0.00` is reported by `tests validate` and `check` rather
than by the coverage gate of `tests run`, so the run that measures such a unit is
never blocked by the entry it is about to fix.

### Recording a measured wall

```bash
python3 tools/build.py tests record --tag level0 --json
```

`tests record` is the only command that writes `duration_seconds`. It measures
nothing itself: it reads one retained run record, either
`workdir/builds/<tag>/tests/summary.json` from a selection or
`workdir/builds/<tag>/manifest.json` from a `sim test`, and writes the walls that
run actually measured, with the sitting that produced them. So the figure
committed is the one the author saw, and a tag with no retained record fails by
name. It creates no workspace; its output is a reviewed source change like any
other.

Only a wall that describes actual work is recorded. A cache hit times the cache
check, a skipped unit never ran, a failure has no trustworthy wall, and a name
outside the catalogue has nowhere to record one; each is reported under
`not_recorded` rather than written. Those are the only refusals. Every wall that
is written is named against the figure it replaced, in whichever direction is the
multiple, with its conditions and a `DRIFT` mark past the reporting threshold:

```text
Recorded DRIFT baseline-good 29.88s against 0.41s recorded, 72.9x higher, wall/CPU 0.61, 28.75s of it compile
```

A `sim` unit's own child record travels into the selection as `units.<name>.timing`,
so a recorded selection carries the same compile split a lone `sim test` does.

### Why nothing is refused for the state of the host

A recording does not judge whether the host was busy, because nothing in a run's
own retained record separates a busy sitting from a quiet one across the
populations the catalogue holds. Inside one population a run's own wall-to-CPU
ratio does track contention, and the
[host-play loop](../host-play/SPEC.md#what-each-budget-measures) is budgeted on
exactly that. A recording covers every unit, and each candidate fails on a
different one:

- CPU is not invariant under contention. Four competing spinners moved the CPU of
  every host unit costing over 5 s by 1.00 to 2.02 times, and their walls 1.5 to
  3.4 times; the units that did not move were already saturating the host. It does
  have a [ceiling](#contention-has-a-ceiling-in-cpu-and-none-in-wall), which the
  wall does not.
- Contention moves the wall far further than the CPU, so an honest wall can sit
  at any ratio. This suite's own three groups, run beside a second worktree's
  `check` at load average 12 to 22, took 604.6, 637.8 and 383.4 seconds of wall
  for 135.6, 160.0 and 127.6 seconds of CPU — ratios of 4.46, 3.99 and 3.01 —
  against 226.6, 282.8 and 204.3 seconds of wall for 115.2, 145.4 and 115.2 of
  CPU on the same content at load average 9 to 11. The wall moved up to 2.7
  times; the CPU moved 1.10 to 1.18. Every one of those walls describes real
  work, and a two-times ratio gate would have refused all three.
- A `sim` wall moves while its CPU does not. `baseline-good` measured 44.71 s
  then 29.88 s back to back in one sitting, a 1.50-times swing, with its CPU at
  49.61 then 48.61 s; the ratio therefore went 0.90 to 0.61 on identical work.
  A parallel compile puts the ratio below 1 whatever the load, so no threshold
  above 1 can ever reach the class whose walls move most.
- A `unit` wall moves and its CPU moves with it. `test_endurance_current.py`
  measured 76.62 s then 195.28 s in one sitting with its CPU at 71.9 then
  124.4 s, and a host unit compiles nothing. Frequency on this host can account
  for at most about 1.08 times of that, so the rest is
  [contention](#contention-has-a-ceiling-in-cpu-and-none-in-wall).
- A unit that sleeps sits at a high ratio while computing almost nothing:
  `test_live_viewer.py` measures about 7.4 s of wall against 2.0 s of CPU, a
  ratio near 3.8, on an idle host. A ratio threshold would refuse that honest
  wall.
- The load average is worse still, having read the idle 0.27 while six
  competitors were live.

Instruments outside a run's own record do better. Sampling `/proc/stat` around a
run, against four competing spinners, moved idle core-seconds inside the window
20.8 to 0.00, other processes' CPU 41.4 to 214.4 seconds and involuntary context
switches 4,541 to 17,384, while the run's own ratio moved only 1.10 to 2.26.
Idle-in-window is population-independent: it does not care whether the run
compiles in parallel, sleeps or computes, which is where the ratio fails. Reading
one is not this command's business and would not change it, because a busy
sitting does not by itself make a wall untrustworthy — the three `check` sittings
recorded above include honest walls at a ratio of 3.99 under load average 12 to
22.

So the conditions are recorded for the reader and never used as a gate. Whether a
sitting was quiet enough is the operator's judgement, and `at`, `wall_cpu` and
`build` are what that judgement is made from afterwards. A recorded wall remains
one sample: compare figures only inside one `at`.

A `sim` unit runs as the ordinary `sim test` worker under the run's tag, with
the same backend, `--seed`, `--rebuild` and selected backend tool options, under the
same [per-target wall budget](#test-wall-budget). A `unit` runs as
`unittest discover` over exactly that one file, with the file's own directory as
the top level and `tools/` on `PYTHONPATH`. Its stdout and stderr share one
pipe; the whole output is kept, and the one-line `error` is the first
`FAIL:`/`ERROR:` header, else the `FAILED` verdict, else the last line. A unit's
own trailing print is never reported as its failure.

Every selected simulation unit is validated before any child is launched; a
registry problem fails the selection. A valid unit that does not declare the
requested backend is skipped with reason `unsupported-backend` and never
launched, so a label that mixes Verilator-capable and Questa-only rows runs its
supported rows on either host. There is no fallback to the other simulator. A
unit labelled `needs-cocotb` is skipped with reason `cocotb-environment` when
the pinned `src/dv/python` interpreter is absent. A unit labelled
`needs-wiki-env` runs on the pinned [wiki environment](../wiki/SPEC.md), which
the selection builds for itself: before the aggregate clock starts, and only
when such a unit is selected, the run creates that environment if it is absent,
so the unit runs rather than skips on a host that has never built it. Creating it
installs [`requirements.txt`](../../../tools/wiki/requirements.txt) with
`--require-hashes`, which reaches the network unless pip can satisfy the pin from
its own cache; that is the one command in a selection which does. The result
is recorded as `preparation.wiki-environment` with `PRESENT`, `BUILT` and its
wall, `UNAVAILABLE` and the reason the build could not complete on this host, or
`BROKEN` and the reason the checkout could not say where the environment belongs,
and the text summary names it. Only `UNAVAILABLE` leaves the unit skipped with
reason `wiki-environment`; a failure inside a built environment is a unit
failure, never a skip. `BROKEN` is a repository defect rather than a host
condition: [`check.py`](../../../tools/wiki/check.py) missing or unreadable, or a
lock file it hashes gone. No host can supply a tracked file that is absent, so
the unit fails and the selection fails with it, including a selection narrowed to
`needs-wiki-env` alone.
Installing an interpreter is preparation, not test work, so its wall is reported
beside the aggregate rather than inside the budget. The
environment's location and build rules both live in
[`check.py`](../../../tools/wiki/check.py) and are read from there, never
repeated. A skip is not a defect, and
is never silently swallowed: the summary lists every skipped unit in
`skipped`, the unit's record carries its `reason`, and the text summary names
each skipped unit with that reason.

The default aggregate budget is the ordinary 300-second pre-merge aggregate.
`--budget` declares another; above 300 seconds it also needs `--broader`, as a
regression subset does. The result is published as
`workdir/builds/<tag>/tests/summary.json` and as the tag's `manifest.json`;
`tests/.lock` holds the tag for the whole selection.

## Verilator simulation

Verilator v5.052 on Linux is the executing simulator for every registry target
whose `simulators` includes `verilator`. [`verilator.py`](../../../tools/n2m/verilator.py)
builds the commands and checks transcripts; [`simulator.py`](../../../tools/n2m/simulator.py)
discovers the tool; [`simulation.py`](../../../tools/n2m/simulation.py) runs the
stage and publishes the record.

### Simulator field

Every target in [`targets.json`](../../../src/dv/builder/targets.json) declares
`simulators` as a nonempty, duplicate-free ordered list drawn from `verilator`
and `questa`. A missing, empty, duplicate or unknown value fails the target
validator, `tests validate` and `check`. `sim test`, `tests run` and `regress`
validate the selected backend against every target before tool discovery or
child launch. The list states capability, not preference; host-native omission
selects the backend first.
`vendor_model` on a `verilator` target records the synthesis binding of the
RTL under test (`intel-memory`, `intel-adc` or `intel-controls`). The Verilator
stage compiles no vendor source: the wrapper selects the repository double
under `VERILATOR`, and the record's `options.vendor_model` names the binding
and the double. `intel_mixed_mode_instances` is the Questa model's
coercion-diagnostic inventory. A target may declare it only when its capability
list includes Questa. A dual-capable target may therefore retain the inventory,
but only the Questa run consumes it; the Verilator double emits no such
diagnostic (see the [memory MAS](../../src/rtl/common/MAS_memory_primitives.md#writes-and-collisions)).
An `intel-adc` target receives the [channel fixture files](#intel-adc-binding-under-verilator)
beside its run. `defines` lists `NAME` or `NAME=VALUE` identifiers that the
build passes as `+define+`; elaboration-time selection is a build option, not
a runtime plusarg, and the validator refuses any other shape.
`preload` runs on the Verilator stage; see
[preload fixtures](#preload-fixtures-under-verilator). A `driver` runs through
the [Verilator peer](#verilator-peer-driver). `sources` may list
[lint waiver files](#lint-waiver-files) beside the HDL. The migrated targets
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
targets and the two `tb_preload_load` targets), the two `tb_memory_decode`
targets `memory-decode` and `memory-decode-alias`, the three `tb_clocking` targets `clocking`, `clocking-bad-numerator` and
`clocking-drop-tick`, and the five `tb_async_assert_macros` targets
`async-assert-macros`, `async-assert-direct`, `async-assert-hold`,
`async-assert-never` and `async-assert-no_reset`, and the 127 Python cocotb
targets of the [Python area](../../../src/dv/python/README.md), which declare
`["verilator"]` only, including the three `tb_python_mooneye` targets that
build the [locked Mooneye fixture](../../../src/dv/mooneye/README.md) with the
re-recorded native host pin. No registered row declares `["questa"]` alone;
`builder-smoke` and `builder-smoke-fail` declare both backends.
`ppu-shift-unknown` and `async-assert-known` are [retired](#test-catalogue):
their expected fatal was a four-state `N2M_ASSERT_KNOWN` that a two-state
simulator never raises. `python-v05-continuous` is retired because its
600-frame schedule cannot finish inside any declared wall allowance; the
[continuity schedule](../../../src/dv/python/v05/README.md#continuity-schedule)
replaces it under a declared 900-second allowance.

### Lint waiver files

A target's `sources` may list Verilator configuration files (`src/**/*.vlt`)
beside its `.sv` and `.svh` sources. [`hdl.py`](../../../tools/n2m/hdl.py)
accepts them as inputs: each enters the record's `inputs` and the fingerprint
like HDL, is never read for `` `include ``, cannot itself be included, and is
refused as an FPGA source. [`verilator.py`](../../../tools/n2m/verilator.py)
passes every listed `.vlt` on the build command line before the HDL, and
before the generated [peer access list](#verilator-peer-driver) so both
configurations apply. `tests validate`, `check` and the
[SystemVerilog style checker](../../../.agents/skills/rtl-coder/scripts/check_sv_style.py)
accept them; the style checker reads only `.sv` and `.svh`.

A waiver file holds the lint waivers a testbench induces in RTL it does not
own, such as `MULTIDRIVEN` from a testbench `force` or `UNOPTFLAT` from a
zero-delay testbench memory loop. It lives beside the testbench, and every
target whose testbench induces the warning lists it. Each waiver is a
`lint_off` line naming the rule (`-rule`), the RTL file and signal or entity
(`-file` with `-match`, or `-lines`), preceded by a comment naming the
testbench construct and the reason. A comment must not open with the word
`verilator`, which the lexer reads as a lint meta-comment.
[`cpu_lint.vlt`](../../../src/dv/cpu/cpu_lint.vlt) is the CPU area's file.
`/* verilator lint_off */` comments inside RTL are reserved for warnings the
RTL itself owns; a testbench-induced warning is waived in a `.vlt`, never in
the RTL.

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

### Fixed cost of a Verilator run

A composed-system run spends almost nothing on its prepared fixtures. Measured
with Verilator 5.052 on the recorded development host, reading the menu
fixtures: `$readmemh` of `menu-library.hex` (573,440 lines) takes 0.020 s,
`menu-frames.hex` (207,360 lines) 0.007 s and `menu-splash.hex` (391,680 lines)
0.013 s. The whole setup phase of `tb_menu_system` -- process start, both
`$readmemh` calls, the 286,720-word SDRAM preload and device initialization --
takes 0.20 s, measured by running the model to its fixture selection and no
further. Packing those files denser therefore cannot pay for itself: the parse
it shortens is under a tenth of a second of a run that lasts a minute or more.

The fixed cost is simulated time and the trace. The menu's first frame body
arrives 76.6 ms into simulated time, which is most of the wall each menu target
spends before its first comparison, and the FST trace of the whole top costs
more wall than everything else together. The same sources and fixtures, traced
and untraced, with every signature unchanged: `menu-frame` 73.6 s and 31.4 s,
`menu-phase` 112.4 s and 46.0 s, `menu-splash` 114.1 s and 45.5 s. Each traced
menu attempt writes about 227 MB of FST.

The trace stays mandatory: every attempt retains one and a missing wave is a
`FAIL`, as above. Verilator has no runtime selection of individual signals, so
the declared `python.waves` list cannot narrow it, and the alternatives that
would (a shallow `trace` depth, or `tracing_off` on the design's modules) keep
the file while dropping the internals the wave exists to show. The cost is
recorded here so it is chosen knowingly rather than rediscovered.

A boot receipt that saved one settled state and restored it into every menu
target is not available: Verilator refuses `--savable` together with `--timing`
(`V3Options.cpp`), and every SystemVerilog target here builds with `--timing`.

### Python testbenches under Verilator

`testbench: "python"` targets keep the [testbench contract](#testbench-types):
the same `python` object, import closure, pinned interpreter and one named
completed test. The build adds `--vpi --timing --timescale 1ns/1ps`, a
generated `compile/verilator/<target>/<attempt>/access.vlt` that makes every
object of the top module public (`public_flat_rw -module "<top>" -var "*"`)
and nothing below it, and `-CFLAGS -O2`; `--public-flat-rw` would expose the
whole design and cost Verilator the optimizations the composed systems need
inside the wall budget. `--timing` stays because the wrappers own their clocks,
settled-sample delays and fault arming. The build links
`-lcocotbvpi_verilator` from the installed cocotb 2.1.0 library
directory and compiles cocotb's own `share/lib/verilator/verilator.cpp` as the
main. A registry `args` entry of the form `-g<NAME>=<VALUE>` is a top-level
parameter override: the build passes it as `-G<NAME>=<VALUE>` at verilate time
and the run never sees it (`python-v05-identity` and its fault set `BUILD_ID`
this way); every other entry stays a run plusarg. The run adds `--trace --trace-file
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
`SIM_PRELOAD` and `INIT_FILE("preload-rom.mif")` resolve to the prepared
files, as they did under Questa. A driver target that sets `driver.preload`
instead prepares through its Python peer, and the same recheck runs after the
peer is ready and before the run launches.

`preload-fixture` ([`tb_preload_fixture.sv`](../../../src/dv/preload/tb_preload_fixture.sv))
proves the pipeline without product RTL: it reads the ROM MIF, presence MIF and
CRC hex from its run directory (both MIFs declare the `PROFILE_STORE_BYTES`
store depth; the image fills the first 32768 addresses and the presence bitmap
is zero above them), rebuilds the 32768 bytes, requires the CRC-32
of the rebuilt image to equal the hex the loader reads, and checks the
integration image's entry stub and title. Measured on WSL: build 4.5 s, run
under 0.1 s, `CACHED` on rerun. `preload-lifecycle` and `preload-crc-fault`
([`tb_preload_load.sv`](../../../src/dv/preload/tb_preload_load.sv)) run the
loader against the initialized RAM double with the same `preload: "integration"`
declaration and rebuild their expected bytes from the prepared ROM MIF. The
Python targets that declare `preload` run through the same stage: the wrapper
selects the prepared image under `+define+PRELOADED` from the target's
`defines`, and the Python test adopts the verified manifest instead of loading
the image over UART.
[`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py)
`PreloadTests` cover validation, preparation, the pre-launch recheck, the
record, and fingerprint invalidation by a changed fixture input or Mooneye tool
identity, with doubles.

### Verilator peer driver

A `driver` target steers a SystemVerilog testbench from the builder-owned
Python peer through a live byte bridge. The catalogue schema is unchanged:
`driver` holds `script`, `peer`, `inputs`, `access` and optional boolean
`preload`. For a Verilator-only driver target, the `script` is the Verilator peer,
a cocotb module ending in `.py` that defines one test named `peer`; `access`
must be a nonempty list of top-level identifiers. The validator, `tests
validate` and `check` refuse a driver whose capability is not exactly
`simulators: ["verilator"]`, whose script is not a `.py` module, whose access
list is empty, or whose script, peer or inputs are missing or outside the tree.
Selecting Questa for one of these targets fails before tool discovery; no
legacy Tcl driver is registered or run.

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
sends `WAIT 5` after the first request; it is registered
`expected_exit: "nonzero"` with signature `SMOKE_DRIVER_WAIT_RANGE`, so it
passes only by the peer raising that name (the peer-raised failure form
below), and a run whose peer passes fails it as `unexpected exit 0`;
`verilator-peer-fatal` passes `+echo_fault`
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
`timing` with the four separately measured walls and the locked CPU listed under
[prepared attempts](#prepared-attempts), so the preparation and compile cost
against the wall budget are visible, `elapsed_seconds`,
`exit_code` and `timeout_seconds` on each command, `preload` when the
target declares a fixture, and `peer` plus `python_results` when it declares
a driver. Measured on WSL: the
`builder-smoke` build takes about 4 s cold and under 0.3 s with `ccache`, the
run milliseconds; `python-joypad` builds in 0.3 s and runs in 0.4 s.
[`test_verilator.py`](../../../tools/n2m/tests/test_verilator.py) covers
discovery, command shape, transcript classification, the record fields, target
capability checks and host ownership with doubles; the runs above are the simulator
evidence.

## Questa simulation

Native Questa executes each target whose `simulators` includes `questa`, on any
host holding the executables and a [runtime license](#questa-runtime-license).
Command construction, macro handling and Intel model bindings live in
[`questa.py`](../../../tools/n2m/questa.py),
[`intel_memory.py`](../../../tools/n2m/intel_memory.py) and
[`intel_adc.py`](../../../tools/n2m/intel_adc.py). Unselected backend options
are rejected. A missing tool, license checkout failure or diagnostic is FAIL,
never a fallback or skip. Legacy Tcl driver scripts remain unregistered;
registered peer-driver targets are explicitly Verilator-only.

### Testbench types

The [target registry](../../../src/dv/builder/targets.json) defaults to
`testbench: "systemverilog"`; existing SV commands and expected-exit rules stay
unchanged. `testbench: "python"` explicitly selects cocotb with a closed `python`
object requiring `module`, `test` and `inputs`, with optional `waves`. No other
keys are accepted. The module/test are identifiers;
inputs name checked-in files including exactly one module file. Unsupported
types, missing inputs and driver settings fail without fallback.
`expected_exit` names the Python verdict, as the
[Python contract](#python-testbenches-under-verilator) defines. The
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

`preload: "menu"` builds the [game menu](../../src/sw/menu/SPEC.md) image
through `sw build menu` and writes, beside the usual Intel files, the
fixture SDRAM library `menu-library.hex` and the scripted reference frames
`menu-frames.hex` that [`tb_menu_system`](../../../src/dv/menu/tb_menu_system.sv)
reads with `$readmemh`; its inputs are the menu sources and assets, the
[fixture builder and reference](../../../src/dv/menu/README.md) and the
software tools.

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

`vendor_model: "intel-adc"` resolves the installed control core, canonical
synchronizer, public and encrypted MAX10 atoms, and PLL models, each
[unchanged since that installation accepted it](#accepted-vendor-sources). It
uses the same installation discovery and explicit `--intel-sim-lib` selection as
memory did while that option was accepted, and it takes the executables
directory from the installation's own layout rather than naming `quartus/bin64`.
Every source digest and PLL generation dependency enters the fingerprint before
reuse. Each attempt records the actual PLL generator command, verifies its
parameters against the FPGA configuration, and retains the generated hash.
Vendor compilation separates `n2m_intel_adc_atoms` from the control library
`n2m_intel_adc`. Control resolves its canonical synchronizer locally; it does
not overwrite the alternate definition embedded in `altera_mf.v`. Explicit
run mappings and `-L` binding preserve that separation. Repository substitutes
for these modules are rejected.

The installed top wrapper contains CR-CR-LF around its timescale. Only its
exact vlog2083 line24 diagnostic is explained, with that wrapper's accepted
record, path, single occurrence and one-warning/zero-error summary required. Raw logs and
`explained_compile_diagnostics` retain that one actual warning. Other compiler
or runtime warnings remain failures. No vendor bytes are edited or compiler
warnings suppressed. Host dependency tests are not hardware behavior evidence.

### Intel ADC binding under Verilator

A `verilator` target with `vendor_model: "intel-adc"` or `"intel-controls"` lists the PLL and control
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
compiles the repository double. The Questa adapter requires the
installed source set [dependencies.json](../../../tools/n2m/dependencies.json)
names. It finds `quartus/eda/sim_lib` beside the selected Questa
distribution, or takes `--intel-sim-lib <directory>` explicitly, which must sit
inside a recognized Quartus installation. Each required source must exist and be
[unchanged since that installation accepted it](#accepted-vendor-sources) before
cache reuse or compilation. A missing model, or one that changed under accepted
evidence, fails; there is no portable fallback. Repository HDL that defines a
shadow `altsyncram` or `altsyncram_body` is rejected.

Each attempt compiles the unchanged source into its own `n2m_altera_mf` library,
maps that library in the run directory, and binds through `vsim -L n2m_altera_mf`.
The record's `options.vendor_model` retains release, source paths/hashes,
compilation options and binding options, and whether each source was unchanged
since it was accepted or recorded for the first time. These and the
wrapper/fixture sources, parameters, dependency record and builder options enter
the fingerprint. Accepting a changed vendor source changes the fingerprint;
removing or changing an installed source cannot reuse an older PASS. Vendor
source is never copied into tracked files.

`intel_mixed_mode_instances` names the exact vendor instances expected to emit
the accepted model's mixed-port coercion warning. This inventory is part of
the Questa descriptor and fingerprint. A target may declare it only when its
capability list includes Questa, because the Verilator double emits no coercion
diagnostic. The forbidden collision it classifies is checked under both
simulators by the wrapper's `INTEL_RAM_MIXED_PORT_A/B` assertions, which
`intel-memory-collision` witnesses. Only the accepted model's exact two-line
time-zero diagnostic is classified, and only during runtime. Missing, duplicate,
wrong-instance, wrong-time and other warnings fail. `explained_diagnostics`
records each original pair, the model digest it read and the reason; raw logs
remain unchanged. The exception applies only to the forbidden collision described
by the memory MAS. Synthesis must read the same accepted model source and must
not produce Quartus critical warning 15003.

The pinned ADC model has a separate, exact elaboration diagnostic profile:
seven protected-model width messages, nine ignored `$rewind` return messages,
and two messages for its unused FIFO `eccstatus` output. The same profile occurs
with 50 MHz and 25 MHz control clocks. The protected internal widths cannot be
inspected; this classification does not prove arbitrary ADC configurations.
Actual channel/sample/lock recovery checks and fitted product port/clock checks
remain required. The ADC classifier checks that each source it explains is an
accepted record, and then the complete messages, locations, counts and summary
lines. Any drift or additional warning fails.
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
is no fictional off-chip pixel input budget. The virtual system inputs carry a
1-2 ns bookkeeping budget: they land directly on M9K input registers, whose
clock arrives about 0.8 ns after the PLL-compensated logic clock, so a zero
minimum would report a hold violation on a pin that does not exist. The audit
checks the exact
63 system input names, all existing timing gates, and setup/hold paths from
every pixel request register into memory at all three timing corners. Each
path must use the same pixel launch/capture clock and have nonnegative slack.
It also checks four logical RAM shapes and ten fitted M9Ks. Fitted atom checks bind data and byte lanes, the system PLL
and pixel PLL clock nets, B address/read-control clocks, unregistered outputs, disabled B writes,
and absent memory clear/initialization. The fitter's physical new-data mode
may include NBE handling; the MAS permits simultaneous A read/write only with
all public lanes enabled, where that mapping preserves the defined result.

The `memory-stores` FPGA target constrains the seven direct-profile stores at
25 MHz with virtual service inputs and outputs, including explicit packed-struct
member names for the paired OAM port. Every store port other than `clk_sys` is
a virtual pin with a 0-2 ns input budget; a port added to the store without a
registry entry fails the fitter's pin-assignment check, and
[`test_fpga_memory_stores.py`](../../../tools/n2m/tests/test_fpga_memory_stores.py)
compares the registry with the module header. Its checker requires the exact
seven logical depths, 657,784 bits and 84 fitted M9Ks. It checks both port
register stages, the common clock, disabled B writes, whole-byte enables,
physical bit inventory, and absent primitive reset/initialization. The ordinary
timing and diagnostic gates still apply. This proves the raw storage slice;
CPU routing, arbitration and full-system initialization require their own
composition evidence in the [memory contract](../../src/rtl/memory/MAS_memory.md).
`memory-stores-preloaded` is the same target with a
[carried ROM image](#carried-rom-image); the two together are the fitted evidence
for both power-up states.

### Registered target execution

Run a Questa-capable target with the host-native default or explicit selection.
Windows is the licensed host in practice, so its default needs no `--sim`:

```powershell
python tools/build.py sim test builder-smoke --sim questa --tag questa-smoke --json
python tools/build.py sim test builder-smoke --sim questa --questa-bin <directory> --tag questa-explicit --json
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

### Questa compile gate

```bash
python3 tools/build.py lint questa --tag <tag> --json
python3 tools/build.py lint questa --questa-bin <directory> --tag <tag> --json
python3 tools/build.py lint questa --inject-fault --tag <tag> --json
```

`lint questa` proves that a second front end accepts the product RTL that
Verilator simulates and Quartus synthesizes. It compiles and elaborates; it
never launches `vsim`, so it needs no runtime license. That is the whole reason
the gate passes on a host where `sim test --sim questa` cannot run; see the
[runtime license](#questa-runtime-license). It is a required local
check for every PR touching `src/rtl` or `src/fpga` under the
[PR policy](../../agents/pull-requests.md#hosted-and-local-checks).
[`lint.py`](../../../tools/n2m/lint.py) owns the command;
[`test_lint.py`](../../../tools/n2m/tests/test_lint.py) covers its contracts
with tool doubles. Any host with the four executables runs it; no operating
system is refused. A host without them fails naming the missing tool, such as
`missing vlib; select the Questa tool directory explicitly`.

Discovery resolves `vlib`, `vmap`, `vlog` and `vopt` on PATH or in
`--questa-bin <directory>`, records each path, SHA-256 and `-version` banner,
and never falls back between the two. The compile set is fixed by the tree:

1. every `.sv` file under `src/rtl`, packages first, each package after the
   packages it names with `::`; a package cycle fails before any tool runs;
2. every source of every target in every board registry, the
   [DE10-Lite](../../../src/fpga/de10_lite/targets.json), the
   [DE10-Nano](../../../src/fpga/de10_nano/targets.json) and the
   [DE2-115](../../../src/fpga/de2_115/targets.json), validated by the
   same [target definition](#fpga-build) and synthesis
   [dependency resolver](#hdl-includes) as `fpga build`. Every registered top
   is elaborated once, whichever board registers it;
3. the elaboration stand-ins
   [`questa_lint_vendor.sv`](../../../src/dv/builder/questa_lint_vendor.sv):
   port- and parameter-compatible empty modules for exactly `n2m_system_pll`,
   `n2m_pixel_pll`, `n2m_adc_pll`, `altera_modular_adc_control`, `altsyncram`
   and `altera_onchip_flash`, the units Quartus generates or installs during
   `fpga build`.
   They are elaboration stand-ins, not models: no behavior, no vendor
   parameter checking. Only this command compiles them; they belong to no
   synthesis source set and are not the `VERILATOR` doubles. The result
   lists them under `stand_ins` so a reviewer sees the gate's blind spots, and
   a file declaring any other set of units fails the plan;
4. with `--inject-fault`, the deliberate fault
   [`questa_lint_fault.sv`](../../../src/dv/builder/questa_lint_fault.sv): an
   `initial` writer beside `always_ff`, legal to Verilator and rejected by
   `vopt` (vopt-7061). The command must then FAIL naming
   `questa_lint_fault.sv` and record `fault_detected: true`. A run that
   compiles the fixture clean is reported as FAIL with
   `fault injection not detected`, and a failure naming anything else records
   `fault_detected: false`.

The plan above is validated before any tool is probed. No testbench is compiled. `SYNTHESIS` and `VERILATOR` stay undefined, so the
RTL presents its Questa view: `` `ifdef SYNTHESIS `` branches are excluded and
Intel instances bind to the stand-ins. The repository root is the include
directory, as for every other Questa compile.

Each run creates the immutable attempt
`workdir/builds/<tag>/lint/questa/<attempt>/` and runs, in order and each with
a 300-second bound: `vmap -c`, `vlib work`, `vmap work <library>`, one
`vlog -sv -work work +incdir+<root> <ordered sources>`, then
`vopt -work work <top> -o <top>_opt` for every distinct registered top in name
order. Every top is elaborated once, however many targets share it. A step
fails on a nonzero exit, a timeout, or the shared
[strict transcript policy](../../../tools/n2m/questa.py): any warning line
other than a zero-warning summary, any `Error`/`Fatal` line or a nonzero
`Errors:` count. Notes pass; the only Note the installed tools emit is the
`-220` ini-file notice. Nothing is suppressed, and the first failing step ends
the run.

The attempt retains `commands.log` (one JSON argv per line), `ini.log`,
`library.log`, `map.log`, `compile.log`, `elaborate-<top>.log` and
`result.json`; the `work` library is regenerated and not hashed. `result.json`
and the tag manifest carry `status`, `error`, `provenance` (commit, dirty-tree
fingerprint, host, Python, OS), `tools` (path, `sha256`, `version` per tool),
`sources` in compile order, `inputs` (SHA-256 of every source and included
header), `tops` (each top's registry `targets` and `sources`; the injected
fault carries `injected: true`), `stand_ins`, `commands` (label, argv, cwd,
log, `exit_code`, `elapsed_seconds`; a timed-out step records `exit_code:
null`), `elapsed_seconds`, `artifacts` (relative path to SHA-256), and on
failure `failure` with the failing `label`, `problem`, every error line under
`errors`, the source files and design units those lines name under `names`,
and the `log`. PASS exits 0 and updates `workdir/latest.txt`; FAIL exits 1
and names the failing step and the offending file or unit in `error`. The
gate is never cached: every invocation compiles again.

The [doctor](#environment-doctor) with `--sim questa`, on any host, adds the
`questa-lint` check: it discovers the four executables, records their banners
and the exact command, and reports PASS without running the gate. The
simulation smoke's runtime license status does not affect that check.

## Feedback and budgets

Required validation follows the [PR check policy](../../agents/pull-requests.md#hosted-and-local-checks).
Affected-test selection never owns, replaces or reduces a required check: the
[affected-test report](#advisory-affected-test-report) is advisory, and the
[conservativeness proof](#conservativeness-proof) is what makes its reasons
reviewable. Setup defects have their own host-only gate in
[Python fixture preflight](#python-fixture-preflight), which is preparation, not
acceptance. Every simulation still obeys the budgets below.

### Test wall budget

Ordinary simulations have a maximum 300-second total wall budget. Target at most 120
seconds per simulation and 300 seconds aggregate for ordinary pre-merge checks;
declare broader milestone aggregates before execution. A target that demonstrably
needs more may [declare an allowance](#declared-wall-allowance) above 300 and up to
900 seconds; 300 remains the default for every target that declares nothing. Before
shortening a composed-system target to fit, read its
[fixed cost](#fixed-cost-of-a-verilator-run): simulated boot and the mandatory
trace, not fixture parsing, set the floor. The user's bounded
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
command into a silent cache hit: its backend-qualified
`sim/test/<target>/<backend>/result.json` was
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

`check` runs the host suite ([host_suite.py](../../../tools/n2m/host_suite.py))
as three `unittest discover` subprocesses over `tools/n2m/tests` at the same
time, one per alphabetical module group (`test_[a-e]*.py`, `test_[f-l]*.py`,
`test_[m-z]*.py`), each inside a 180-second budget on the CPU time that group
spends. `unittest` runs modules one after another, so the groups balance measured
module time recorded once in the source, not live timings; a new module joins the
group its name falls in, and a module no group matches fails `check` by name. A
group that fails or exceeds its budget fails `check` naming the group and its
first failing test; a stalled group is never a partial pass. `check.log` carries
each group's status, wall, CPU and the host's one, five and fifteen minute load
averages before its output, and the record's `groups`, `wall_seconds` and
`cpu_seconds` keep them. Nothing decides anything from load; it is recorded so a
reader can see what the machine was doing. The 300-second aggregate above is a
target on wall time, and a contended host takes this suite past it — 311.4 and
337.7 s wall have both passed — while the CPU budget is what decides the verdict
and `WALL_CEILING` is the only wall `check` enforces. All three averages, because
the one-minute figure alone reads a lull as a quiet host: it has been seen at 1.86
with the five-minute average at 4.27 and the load back at 5.68 immediately
after. The CPU time is the suite's own; only the wall shrinks to the slowest
group. About twenty seconds is the practical ceiling for one unit, and three
reach it: [`test_catalogue.py`](../../../tools/n2m/tests/test_catalogue.py)
walks every test file,
[`test_affected_mutations.py`](../../../tools/n2m/tests/test_affected_mutations.py)
derives a closure for each recorded mutation, and
[`test_standalone_imports.py`](../../../tools/n2m/tests/test_standalone_imports.py)
imports every module of the suite once each. Anything costlier runs opt-in
instead: the real-clone reports of the
[conservativeness proof](#conservativeness-proof) run under
`tests mutations --confirm`.

Every module under `tools/n2m/tests` imports on its own. A group is one
interpreter, so the first module to insert the repository's `tools/`
directory into `sys.path` repairs it for every module imported after it: a
module that never does so of its own accord still passes inside its group,
and fails the moment someone runs it alone to look at a failure, or if the
group ranges are rebalanced so that module leads. A module that imports a
package under `tools/`, or loads a file that does, therefore makes that
insertion itself.
[`test_standalone_imports.py`](../../../tools/n2m/tests/test_standalone_imports.py)
is what keeps that true: it loads every `test_*.py` in that directory in a
fresh interpreter with no inherited `PYTHONPATH`, exactly as
`unittest discover` would, and names each module that needs another
imported first. Its list is the directory rather than a table, so a module
added tomorrow is covered without being enrolled, and a second test proves
the probe fails a module written without the insertion. It probes twice the
core count at a time and spends 13 to 21 s of wall for 25 to 40 s of CPU on a
four-core host, almost all of it importing the modules. The probes run `-B` like
the rest of the suite, so a worktree holding no bytecode caches recompiles every
module and pays the upper figure.

The budget measures user plus system CPU time for the group's subprocess and
every descendant it waits for, read from `os.wait4` on that one pid as the
process is reaped. `RUSAGE_CHILDREN` cannot serve: it sums every child this
process reaped, and the groups run at the same time. The budget does not measure
wall time. Up to four agents work this machine at once, so a group's wall is
mostly how long it waited for a core, while the CPU it spends is its own work.
The `test_[f-l]*.py` group over an unchanged tree measured 149.1 s of CPU in
260.1 s of wall at load average 6.3, 151.3 s in 337.7 s beside its two sibling
groups at load 7.0 to 9.7, and 144.3 s in 461.0 s under six added CPU burners at
load 10.8: a 5% spread in CPU against a 77% spread in wall. Contention is not
free in CPU either, because a contended process pays more system time and more
cache misses: the same group spends about 112 s on a host at load 3, so a busy
host can cost it about a third more. Beyond that the figure is noisy in both
directions rather than monotone in load, and independent runs have put it at
127.9 s under load 9.4 and 146.4 s under load 8.2. Read it as a quantity that
moves tens of percent with the machine, not as one that rises with load. The wall
has no such bound: healthy groups have been measured from 171.1 s up to 345.5 s,
which is why a group's wall carries no information about whether that group is
slow. One pair of runs showed the consequence directly, though reproducing it
needs a quiet host and has not been repeated: a healthy group passed at 151.3 s of
CPU in 337.7 s of wall while a group given 90 s of deliberate extra work failed at
201.7 s of CPU in 230.5 s of wall, so ranked by wall the healthy group was the
worse of the two.

240 is the budget, and it is derived from each group measured alone. `check` runs
all three groups at once, so no group's CPU had been measured on its own until
this derivation. One group at a time, nothing else deliberately running, on the
four-CPU Linux host:

| Group | modules | CPU alone, three sittings | wall/CPU | idle core-seconds in window |
| --- | --- | --- | --- | --- |
| `test_[a-e]*.py` | 13 | 68.7, 71.6 s | 1.12 | 197 to 208 of 308 to 320 |
| `test_[f-l]*.py` | 38 | 77.3, 81.5, 89.2 s | 1.14 to 1.15 | 190 to 250 of 353 to 408 |
| `test_[m-z]*.py` | 41 | 78.2, 89.1, 94.5 s | 0.86 to 0.90 | 127 to 167 of 281 to 340 |

The worst group alone spends 94.5 s, and across sittings each group's own solo
cost spans 1.04 to 1.21 times. The three are still balanced within 1.4 times of
each other even though the order has changed and `test_[m-z]*.py` is now the
heaviest. Note that the ratio does not say the host was quiet for the third group:
that group runs parallel probes and sits below 1 by construction, exactly as the
ratio fails [across populations](#why-nothing-is-refused-for-the-state-of-the-host).
What says
the host was quiet is the idle core-seconds inside each run's own window, which is
population-independent, and which is why they are recorded above.

Against four deliberate CPU burners, in one sitting, the same three content sets
spent 116.9, 135.4 and 118.1 s of CPU — up to 1.75 times their own solo cost —
while their walls went 2.0 to 3.0 times and idle-in-window fell to 0.00 for all
three.

So 240 is 2.5 times the worst group measured alone. Judged against the
[worst case](#contention-has-a-ceiling-in-cpu-and-none-in-wall) rather than one load
level, the quietest group sample of 78.2 s reaches 195 s under full contention and
the most frequency can add, and 240 is **1.23 times** that.

The 180 it replaces was not derived: it was the old wall budget carried across to
the stricter quantity, which was safe because a group's CPU never exceeds its wall
and so nothing that passed before could fail. Measuring the groups alone moved the
answer in the opposite direction from the one expected. The solo cost is about 60%
of the contended figures the 180 was validated against, so the margin over a busy
host was smaller than it looked rather than larger: 180 stood only 1.13 times above
the worst group CPU ever recorded here, and the same worst case that 240 clears at
1.23 times — 195 s — **would have failed it**. Rebalance the group ranges against a
fresh measurement when growth reaches the new margin.

A CPU budget does not catch a group that grows slow by blocking instead of by
computing. A test that sleeps, waits on a socket or waits for a lock spends wall
and no CPU, and stays inside the budget however long it takes. The budget also
does not charge a group for a descendant it abandons rather than waits for.
[#881](https://github.com/amichai-bd/nand2mario/issues/881) tracks enforcing this
at the level of the test, which is where a blocking check can name the test that
blocks. `WALL_CEILING`, five times the CPU budget, guards only against a group
that has stopped making progress: the worst contention measured here stretched a
group's wall to 4.5 times its CPU, so a group spending the whole budget would
take about 1070 s, and five times the budget leaves margin above that. It is not
a performance budget, and its failure names the CPU the group had spent. A host
that reports no per-child CPU time, Windows among them, judges the wall against
the same 240 seconds and says so in the failure. It reaches that verdict later than a wall
budget did, because the group runs to completion, or to the ceiling, and is judged
afterwards, where a `subprocess.run` timeout killed it at 180 s.

Measured on the 4-CPU Linux development host (1157 tests then present, load
average 7.0 to 9.7 from two other agents, one of them compiling with Quartus; a
quiet host was not available): PASS in 337.7 s wall, with groups spending 121.5,
151.3 and 93.2 s of CPU over 290.6, 337.7 and 240.3 s of wall; and at load 5.6 to
7.7, PASS in 227.9 s wall, with 107.7, 124.9 and 87.0 s of CPU over 202.6, 227.9
and 185.1 s of wall.
Every group wall in both runs would have failed the 180-second wall budget, which
on this host failed a passing suite whether the machine was busy or merely in
use. Earlier, on the shared Linux WSL2 host
(22 CPUs, 912 tests, load average 4 to 5.5 from other agents' host suites): 62 s
wall (groups 43, 55 and 39 s; 112 s user and 13 s system CPU), and 59 s with one
concurrent Verilator `regress pre-merge` (groups 42, 53 and 38 s). Before the
split, the single subprocess took 170 s at that load and timed out at 180 s under
load average 5.8; its direct run cost 155 s user and 21 s system CPU. Do not raise
either number without a measured justification; move or rebalance the work instead.

#### Contention has a ceiling in CPU and none in wall

This is why both budgets are on CPU, and it is the reason a value can be judged at
all. On this host — two physical cores with symmetric multithreading, four logical
processors, 500 to 2700 MHz, package 78 °C of a 105 °C limit — one fixed serial
workload measured against a rising number of CPU burners:

| competitors | 0 | 2 | 4 | 8 | 16 |
| --- | --- | --- | --- | --- | --- |
| CPU | 2.06 s | 3.57 s | 4.76 s | 4.73 s | 4.74 s |
| inflation | — | 1.74x | 2.31x | 2.30x | 2.31x |
| wall/CPU | 1.00 | 1.01 | 1.36 | 2.52 | 4.31 |

**CPU saturates at about 2.31 times its solo cost and then stops. The wall does
not stop.** Four times the competitors past saturation changes the CPU by 0.01
times and the ratio by 1.7. That ceiling is the SMT limit: a serial run alone has a
logical processor and its sibling's execution headroom to itself, and a saturated
machine takes both away, once. A workload that was already saturating the host has
nothing to lose and reads 1.01 — measured on a four-way parallel workload leaving
0.1 idle core-seconds when run alone.

So a CPU budget can be sized against the worst case rather than against whichever
load a sample happened to be taken at, and a wall budget cannot be sized at all.

**The mechanism is contention, not a thermal soak.** The inflation appears within a
second of the burners starting and is gone within a second of their death: 2.10 and
2.11 s quiet, then 4.74, 4.73 and 4.70 loaded, then **2.14 in the first quiet sample
after the load stops**. Nothing thermal switches state that fast in both directions.
Frequency is bounded separately and small: all four logical processors sat at 2496 MHz
under load, in mean and in minimum, against a 2700 MHz maximum. 2700 over 2496 is
**1.08**, and that is the whole of what frequency can contribute on this host — not
1.6 and not 2.

Both figures are what the budgets below are judged against: worst case is a unit's
quietest measured CPU times 2.31 for contention times 1.08 for frequency. Separating
them matters because they are the only two mechanisms measured here, and bounding each
means the margins do not depend on any claim about how large a cross-sitting spread is.

**The limits of the ceiling.** It was measured on one host with one instruction mix.
A workload that contends for something else — memory bandwidth, a lock, the page
cache — could exceed 2.31, which is why the margins below are about 1.2 times and not
1.0. Re-measure the ceiling before trusting it on different hardware.

#### What one host unit may spend

Every catalogue runner bounds one host unit at `max(240, 3 x measured cpu)` seconds
of its own CPU: the user plus system time of its interpreter and the descendants it
waits for, read from `os.wait4` as the child is reaped
([cpu_budget.py](../../../tools/n2m/cpu_budget.py)). That is the same quantity, the
same reaping hook and the same bounded run the check groups above use, defined once
for both. Five times the budget is a liveness ceiling on the unit's wall.
`tests run`, `tests mutations --confirm` and `tests closure-trace` all run a unit
under it, and a run's record carries each unit's `cpu_seconds` beside the
`cpu_budget_seconds` it was judged against.

The multiple is of the CPU in that unit's recorded `measured` conditions, never of
its `duration_seconds`. A wall has no worst case in load, so a bound taken from one
would rise with whatever else the host was doing rather than with the work: the same
`check` content has measured 229.8 and 637.8 s of wall for 141.6 and 160.0 s of CPU,
and a wall recorded at the high end would have carried that 2.8 times straight into
the bound. Measuring CPU also covers the units that spend more CPU than wall by
running in parallel, which a wall understates by up to 2.7 times here. A unit whose
conditions name no CPU gets the default, so there is no wall anchor to fall back to.
Exactly one of the 180 host units is above the default today.

It replaced a 300-second bound on the unit's wall, which failed units that had not
grown: `test_state_play.py` measured 239.4 s of wall alone and 1325.3 s beside
eight competing processes, passing both times, and `test_state_player.py` 75.8 s
and 670.6 s. The play loop's own inner wall guard had been aborting the expensive
comparison before the outer bound could be reached, so the defect became visible
only when that guard became a [CPU budget](../host-play/SPEC.md#what-each-budget-measures).

**Why the bound is per unit rather than one number.** One sweep of all 180 host
units in one sitting put 170 of the 178 that ran under 30 s of CPU, seven between
33 and 88, and one at 162. A single bound has to clear the largest, and at the 478
seconds that unit's own measurement earns it, a 30-second unit could grow
sixteenfold before anything failed. The default clears the ordinary population; a
unit whose conditions name more CPU than the default's own share of the factor is
bounded against that instead, so its expense is stated in its catalogue entry
rather than hidden inside a constant sized for it.

**Where the numbers come from.** Every expensive unit measured alone in four sittings,
with the host state inside each run's own window, then against four deliberate CPU
burners paired in one sitting. `other` is other processes' CPU in the window and
`idle` is idle core-seconds in it, both from `/proc/stat`; `w/c` is the run's own
wall over its own CPU.

| Unit | sitting | CPU | other | idle | w/c |
| --- | --- | --- | --- | --- | --- |
| `test_state_play.py` | s1 | 184.68 | 221.3 | 345.2 | 1.02 |
| | s3 | 184.03 | 202.6 | 362.5 | 1.02 |
| | s2 | 161.80 | 54.6 | 434.5 | 1.01 |
| | s5 | 161.01 | 46.3 | 440.4 | 1.01 |
| | s3, four burners | **318.97** | 1688.7 | 0.0 | 1.57 |
| `test_endurance.py` | s2 | 87.88 | 81.9 | 191.1 | 1.03 |
| | s5 | 85.92 | 62.6 | 203.3 | 1.03 |
| | s3 | 78.60 | 26.7 | 215.4 | 1.02 |
| | s3, four burners | **148.63** | 654.5 | 0.0 | 1.35 |
| `test_state_player.py` | s5 | 72.05 | 56.5 | 163.2 | 1.01 |
| | s3 | 67.09 | 34.2 | 169.1 | 1.01 |
| | s1 | 66.20 | 20.0 | 180.2 | 1.01 |
| | s2 | 63.93 | 14.4 | 178.7 | 1.01 |
| | s3, four burners | **129.59** | 639.2 | 0.0 | 1.48 |
| `test_endurance_current.py` | s5 | 65.16 | 38.6 | 160.2 | 1.01 |
| | s3 | 64.84 | 46.5 | 150.8 | 1.01 |
| | s2 | 63.22 | 28.5 | 163.1 | 1.01 |
| | s3, four burners | **119.10** | 569.3 | 0.0 | 1.45 |
| `test_acquisition_host.py` | s2 | 40.65 | 81.9 | 48.2 | 1.05 |
| | s3 | 36.66 | 55.0 | 58.4 | 1.03 |
| | s5 | 33.43 | 22.8 | 78.8 | 1.01 |
| | s3, four burners | **63.62** | 441.1 | 0.0 | 1.98 |
| `test_standalone_imports.py` | s3 | 35.99 | 15.9 | **0.6** | 0.36 |
| | s2 | 34.87 | 3.6 | 1.5 | 0.29 |
| | s5 | 28.97 | 7.8 | 1.2 | 0.33 |
| | s3, four burners | **35.85** | 42.7 | 0.0 | 0.55 |

Each burner row is paired with the `s3` solo row of the same unit, one sitting: the
inflations are 1.73, 1.89, 1.93, 1.84, 1.74 and **1.00**. The last is the unit that
was already saturating the host — 0.6 idle core-seconds with nothing else running —
which is the row the whole mechanism rests on, and it agrees with the 1.01 measured
independently on a four-way parallel workload.

**240** is the default, sized against the worst case rather than a load level. The
worst unit outside `test_state_play.py` is `test_endurance.py`, whose quietest sample
in the table above is 78.60 s of CPU, and 78.60 x 2.31 x 1.08 = **196 s** covers full
contention and everything frequency can add, so 240 is **1.22 times** that. Under
four burners it actually measured 148.6 s, 1.61 times inside the budget. 240 is also
below the 300 it replaces, so it tightens the bound for every unit but the one it
cannot.

**3** is the factor, and the same ceiling is what sizes it: a unit cannot spend more
than about 2.31 x 1.08 = 2.5 times its recorded CPU without doing more work, so 3
clears the worst case with 1.2 times over. `test_state_play.py` records 159.29 s of
CPU, so its budget is 478 s against a worst case of 397 s, **1.20 times**. It is also
above `DRIFT_FACTOR`, so a unit that grows is named by a drift report before its
budget fails it.

**5** is the wall stretch, matching the group ceiling's own multiple. The worst honest
wall measured for an ordinary unit is 670.6 s against this 240, 2.8 times.

**The residual risk, stated rather than left to a reader.** Every margin above is
about 1.2 times, which is thinner than the headline multiples of the budgets over
their solo costs, and it is the honest figure. Two things bound it and one does not.

The margin depends on the
[ceiling](#contention-has-a-ceiling-in-cpu-and-none-in-wall) holding for the work it
is applied to. It does hold there: an interpreter-bound victim, which is what every
host unit and every check group is, measured 2.18 times against ALU rivals and 1.80
against memory-heavy ones, and the six units tabulated above sit at 1.73 to 1.93. It
does not hold universally — a bandwidth-bound victim against bandwidth-bound rivals
reached **3.30 times** — so 2.31 is a property of the victim's instruction mix and not
of the machine. A unit costing what the worst ordinary unit costs, in that regime,
would reach 78.60 x 3.30 x 1.08 = **280 s** against this 240. Re-measure the ceiling
before applying it to work of a different shape, and treat a unit that starts
contending for memory bandwidth as a reason to re-derive rather than to trust the
margin.

The 1.08 is weaker still, and deliberately kept separate for that reason. It is the
clock ratio 2700 over 2496: the most a quiet anchor taken at turbo can understate the
same work at the clock this host sustains under load. That makes it an observation of
what this host sustained — 2496 MHz at 78 °C against a 105 °C limit, on hardware whose
range is 500 to 2700 — and not an architectural bound the way the SMT ceiling is. A
host that thermally throttled further would need it re-measured.

What the margin no longer depends on is a claim about how far identical work varies
between sittings, which is what every earlier derivation here rested on and none could
establish. That variance is now accounted for by mechanisms that can be re-measured
rather than by a spread taken on trust. The risk moved from unboundable to measured
and re-measurable, which is the whole of the improvement and not more than it.

**Multiplying the two is not double counting.** Every loaded sample behind the 2.31
sat at 2496 MHz, in mean and in minimum, so the ceiling was measured with both sides
of that comparison at one clock and contains no frequency component at all. What the
1.08 covers is a different thing: an anchor measured on a quiet host may have run at
turbo, above the 2496 the loaded case sustains, which makes the anchor smaller than
the same work would be at that clock. The two factors act on different steps of the
derivation and in the same direction, so they compose rather than overlap.

**A recorded CPU on a busy host still loosens the bound, but no longer without
limit.** The factor multiplies whatever CPU the recording sitting measured, and that
sitting could have been saturated: recording `test_state_play.py` under four burners
would write about 319 s and set its budget near 957 rather than 478. The ceiling is
what bounds that — at most 2.5 times too generous, where a wall anchor had no bound at
all — and `tests record` names the conditions beside every figure so a reader can see
which sitting produced one. Record an expensive unit on the quietest host available.

**What a solo measurement is worth, and what reads it.** A unit's solo CPU varies
across sittings — 1.03 to 1.24 times over the table above — and where it varies it
tracks other processes' CPU inside the run's own window. Four of the six units are
monotone in that figure across every sample: `test_state_play.py` 184.68, 184.03,
161.80, 161.01 against 221.3, 202.6, 54.6, 46.3, and `test_state_player.py` 72.05,
67.09, 66.20, 63.93 against 56.5, 34.2, 20.0, 14.4, with `test_endurance.py` and
`test_acquisition_host.py` the same shape over three samples each. The two that are
not monotone are the unit with the smallest spread of all, 1.03 times, and the
saturating one. An independent measurement extends the relation by a point below the
quietest here: 159.7 s of CPU in a window holding 40.0 core-seconds of other CPU.

That is fourteen samples over **four sittings**, not fourteen independent
observations, and every one of those runs reported a wall-to-CPU ratio between 1.01
and 1.05 — so a run's own record called them all equally quiet while their CPU
differed by up to 1.15 times. The claim this supports is therefore narrow: a solo
figure is only as quiet as its window, and its own ratio cannot tell you. It is not
needed for the budgets, because the ceiling bounds the worst case whatever the cause.
The earlier reading of this spread as a frequency and thermal effect is withdrawn:
inflation here appears and vanishes within a second of load starting and stopping,
and frequency on this host is bounded at about 1.08 times.

`test_state_play.py` is the one unit that does not fit the default, and not by
accident: it drives several complete play loops, each separately budgeted at 240 s of
its own CPU, so no outer bound below that can be honest for it. Its bound comes from
its own measured CPU for that reason, and it is a level 1 unit rather than a level 0
one because it costs what it costs.

The conditions in the table are recorded here because they earned their place: they
explain a cross-sitting spread that the runs' own records could not, and idle
core-seconds is the one reading that works for the parallel unit as well as the
serial ones. They are deliberately not read by any runner, for the reason
[above](#why-nothing-is-refused-for-the-state-of-the-host): a busy sitting explains a
large figure, it does not make that figure untrustworthy. Recording a condition is
not a gate, and this derivation adds no gate.

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
the verification baseline this integration established.

### Prepared attempts

Host preparation of a target (fixture and image build, preload MIF and CRC
files, the Mooneye fixture build, ADC stimulus, the Questa macro) needs no
simulator tool and no license. `sim prepare TARGET --tag TAG [--sim B]
[--seed N]` performs exactly that preparation
([`simulation.prepare`](../../../tools/n2m/simulation.py)) without taking the
tag `.lock`, so it runs while another command holds the tag for its compile,
licensed run or board phase. `sim test TARGET --tag TAG --prepared ID` then
takes the tag lock and runs compile, simulation and checking from that attempt.
The default `sim test` without `--prepared` is unchanged: it prepares inline
under its own lock hold.

This is a split of one target's work, not a queue. The licensed-simulator slot
and board access remain orchestrator-coordinated as [above](#test-wall-budget);
nothing waits for a held tag lock, and a second holder is impossible exactly as
before: the [tag lock rules](#cache-rules) are untouched, and the
[lock racer](../../../tools/n2m/tests/lock_racer.py) `--adopt` mode proves in
real processes that two prepared runs on one tag yield one holder and that the
other is refused by the live-pid rule, not admitted because it was prepared.

Preparation writes only a fresh immutable attempt
`sim/test/<target>/<backend>/attempts/<id>/` and its receipt `prepared.json`
there. It never writes the stage `result.json`, `manifest.json`, `status.json`
or `workdir/latest.txt`; those belong to the tag lock's holder. The attempt
holds its own `pid=<n>` `.lock` while preparation runs, and `clean --tag`
refuses a tag whose attempt lock records a live writer (`tag <tag> has a
preparation in progress`); a dead preparer's lock does not hold the tag. The
receipt records `PREPARING` first, then `PREPARED` or `FAIL` with the error,
the target, backend, seed, the same input hash map and fingerprint the
simulation stage computes (sources, registry, runner modules, fixture inputs,
tool identity, options), the hash of every prepared file, the preparer pid,
`started`, `finished` and `prepare_seconds`. `sim prepare` is supervised like
`sim preflight` under the ordinary 300-second ceiling regardless of the
target's own allowance; an expired preparation leaves no tag lock, a stale
attempt lock and an unadoptable `PREPARING` receipt.

The stage cache check precedes adoption: with a valid cached `PASS` of the
same fingerprint, `sim test --prepared ID` returns `CACHED` and the attempt is
neither adopted nor refused, so it stays adoptable; `--rebuild` then adopts or
refuses it. Otherwise adoption happens under the tag lock, before `RUNNING` is
published and before any tool runs. The stage recomputes every input hash and the fingerprint with
the tools it discovered and hashes every file now in the attempt; it refuses
by name a receipt that is not `PREPARED`, an attempt already adopted, a
different target, backend or seed, any changed, missing or added input or
prepared file (`prepared attempt <id> inputs changed: <paths>`) and any tool or
option change (`tools or options changed since preparation`). A refusal runs
nothing and is published as a stage `FAIL` like any preparation failure. An
adopted attempt is single use: `adopted.json` marks it and a later `--prepared`
of the same id is refused; prepare again instead. The existing preload recheck
immediately before launch still applies.

Every simulation record splits the walls: `timing.prepare_seconds` (inline
preparation under the lock, or the receipt's value for an adopted attempt),
`build_seconds`, `run_seconds` and `locked_seconds` from tag lock acquisition
to record completion, and `locked_cpu_seconds`, the CPU that same window spent in
this process and every child it reaped, absent where the host reports no
per-child CPU; `lock_acquired` and, for an adopted attempt,
`prepared.prepared_started`/`prepared_finished` place the preparation against
another run's lock window, so the overlap is measured from receipts rather
than claimed. `prepared.mode` is `inline` or `adopted`.

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

Before the first child runs, every member is validated; a registry problem
fails the regression before any child launches. A valid member that does not
include the selected backend in its `simulators` list is `SKIPPED` with reason
`unsupported-backend`, listed in `skipped`, never launched and counted as
neither pass nor defect; no backend fallback occurs. A single-target `sim test`
of the same pair still fails before launch.
Members run in order, each as the `sim test` worker under the same tag with the
regression's backend, `--seed` (default 1), `--rebuild` and matching backend
tool options. The regression supervises each child exactly as a standalone
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

The aggregate is `PASS` only when every launched member passes within the
budget; an `unsupported-backend` skip does not fail it. Otherwise it is `FAIL`
and the error names each non-passing member and its status, for example
`regression builder-fault failed: builder-smoke-fail FAIL`.
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

Executable discovery uses an explicit directory, then PATH, then the
[repository-pinned Verilator](#pinned-verilator-installation); it never changes
global PATH and never falls back from an explicit selection. The Verilator check
records which of the three found the tool as `discovery`. Tool versions are
recorded; commercial installations are user-provided, not bootstrapped or assumed
pinned.
The [tool provenance](../../../tools/sim/THIRD_PARTY.md) owns installation boundaries.

Each invocation gets fresh logs under
`workdir/builds/<tag>/doctor/<attempt>/<backend>/`. Verilator uses a fresh
`obj_dir`; Questa uses a fresh local work library and mappings. Source/runner hashes, commands,
versions, artifact hashes, and per-check outcomes remain in ignored build evidence.
Readiness is never cached. Every profile runs the selected host-native simulator
smoke and checks 22 reset, count, and wrap observations.

The default profile checks the host-native simulator; the environment profile
adds the remaining tools:

- Verilator (Linux only): `verilator --version` must report a `Verilator <release>`
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
  check removes `SALT_LICENSE_FILE`, `SALT_LICENSE_SERVER`, `LM_LICENSE_FILE`
  and `MGLS_LICENSE_FILE`
  from the child environment and records `license` as none consulted, so a
  PASS cannot depend on a license. `--verilator-bin <directory>` selects the
  directory holding `verilator`; otherwise it is resolved on PATH, and then in
  the [pinned installation](#pinned-verilator-installation). The compile
  step has a 300-second bound; the runs keep the 60-second default.
- Questa (any host with the tools and a license): discover and record `vlib`,
  `vmap`, `vlog` and `vsim`, probe the
  [runtime license](#questa-runtime-license) and record the probe argv and exit,
  create isolated mappings and a work library, compile the same smoke, and run
  the positive and `+inject_failure` cases through the retained `run.do` macro.
  The positive run requires the exact PASS signature and zero diagnostics. The
  fault run requires nonzero exit, the exact mismatch and one expected error.
  A PASS records that the runtime license checkout succeeded. A missing tool,
  license failure, unexpected diagnostic, wrong exit or missing signature fails;
  an absent license fails naming the license, not the host.
  `--questa-bin <directory>` selects the four native executables.
- Questa compile gate (any host, with `--sim questa`): the `questa-lint`
  check discovers `vlib`, `vmap`, `vlog` and `vopt`, records their banners
  and the `lint questa` command, and PASSes on availability alone; see the
  [compile gate](#questa-compile-gate). A missing executable fails it.
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
- JTAG: enumerate through whichever [programmer](#programming-backends) is
  available, and report which one was used. No image is selected, so no single
  board is expected: exactly one cable must report exactly one
  [registered board's](#programming-backends) device, and the check names that
  board, the backend, the resolved tool, the exact command, the matched chain
  position and the reason every rejected attempt was rejected.
  `--jtag-cable <cable>` selects one cable, `--programmer` one backend,
  `--openfpgaloader-bin` and `--probe-firmware` its tool directory and cable
  firmware. Nothing is written: both programmers only read. This is reported
  identity, not wiring, voltage, or programming proof.
- UART: Windows and Linux enumerate serial ports into the same records, so one
  selection rule serves both hosts. Select with `--uart-port`, `--uart-vid`,
  `--uart-pid`, or exact `--uart-identity` (the OS identity, which may include a
  serial). Combined selectors must all match exactly one port. No selection is a
  warning; a missing, ambiguous, or unhealthy explicit selection fails. A healthy
  port reports `Status=OK` and `ConfigManagerErrorCode=0`. Any other host reports
  a warning and enumerates nothing. See
  [serial port enumeration](#serial-port-enumeration) for each host's inventory
  and health rule.

### Serial port enumeration

Both hosts produce records carrying `DeviceID`, `PNPDeviceID`, `Status` and
`ConfigManagerErrorCode`, so `select_uart` and the
[host session](host/SPEC.md#commands) read one contract. Enumeration is
read-only on either host: no port is opened, no modem line is driven and no byte
is sent.

Windows queries CIM `Win32_PnPEntity` with `PNPClass='Ports'` through PowerShell.
A port needs a serial `(COM<number>)` friendly-name suffix and a PnP identity;
parallel ports and malformed names are excluded, and neither the COM number nor a
hardware serial is ever inferred from a PnP identity tail. `Status` and
`ConfigManagerErrorCode` are Windows' own.

Linux reads udev's stable `/dev/serial/by-id` names and the sysfs USB attributes
behind each one. A port is reported only when it has both: the by-id link gives
the stable name, and the first ancestor of the tty's bound device carrying
`idVendor` gives the vendor and product. A tty with no USB device behind it, such
as a built-in `ttyS*`, has nothing to select by and is not reported. `DeviceID` is
the device node the link resolves to (`/dev/ttyUSB0`), which is what the host
opens. `PNPDeviceID` is `USB\VID_<vid>&PID_<pid>\<by-id name>`: the same shape as
the Windows identity, built from the USB ids and udev's own name, which survives
replug and renumbering. The record also keeps `ByIdPath`, `SysfsPath`, `Serial`,
`Manufacturer` and `Product` as read. Health is the device node itself, not a
driver database: `ConfigManagerErrorCode` is 0 when the node is a character device
this user can read and write, 1 when the node the link names is unavailable, 2
when it is not a character device and 3 when it cannot be read and written, each
with its own `Detail`. The enumerated records are retained as `ports.log`.

The doctor never opens UART, drives modem lines, sends bytes, programs FPGA memory,
changes JTAG configuration, or proves physical operation. Those follow the
[current authorization](../../agents/bootstrap-plan.md#verification-and-hardware-authorization)
and hardware workflow. No extra Python packages are required.

`PASS`/exit 0 means all applicable checks in the selected profile passed;
`NOT_APPLICABLE` entries are informational and excluded. `WARNING`/exit 2
means requested evidence is incomplete. `FAIL`/exit 1 means a check failed and
takes precedence over warnings. JSON includes `profile`, the selected
`simulator`, `checks`, `tools`, `inputs`, `readiness`, and `untested`;
simulation success is not full environment readiness. Only PASS updates
`workdir/latest.txt`. The simulation check is keyed by the selected backend.
It records that backend's tool identities, release, positive run, fault
detection and license status. [`test_doctor.py`](../../../tools/n2m/tests/test_doctor.py)
proves elaboration, runtime, signature, undetected-fault, missing-tool, license
failure and host-selection cases with controlled doubles. Actual readiness
requires a native run on the selected host.

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

A fresh Linux machine, native or WSL Ubuntu 24.04, needs the repository, the
build prerequisites and two commands. The first is paid once per host, not once
per worktree: it installs into the
[shared host tool cache](#shared-host-tool-cache) outside every checkout. The
prerequisites are the upstream
Verilator git-build set recorded under `verilator.install` in the dependency
definition, including `liblz4-dev` because Verilator 5.052 compiles its FST
writer against the system `lz4.h` and links `-llz4` for every `--trace-fst`
build. Then:

```bash
python3 tools/build.py tools verilator --tag pinned-verilator --json
python3 -m venv workdir/builds/python-dv-env/.venv
workdir/builds/python-dv-env/.venv/bin/python -m pip install -r src/dv/python/requirements.txt
```

The [wiki build](../wiki/SPEC.md) owns its own pinned environment. Neither
command above creates it: `python3 tools/wiki/check.py` does, and so does a
`tests run` selection that includes the `needs-wiki-env` unit. Paths with spaces
are supported. There is no license configuration command.

### Pinned Verilator installation

```bash
python3 tools/build.py tools verilator --tag pinned-verilator --json
```

`tools verilator` builds the pinned tag from
[`dependencies.json`](../../../tools/n2m/dependencies.json) and installs it into
the [shared host tool cache](#shared-host-tool-cache),
`<cache>/verilator/v<version>`, outside every checkout so no build tag owns it,
`clean --tag` never removes it and removing a delivered worktree cannot take it.
The source is cloned at the pinned tag into `v<version>.source` and its `HEAD`
must equal the pinned commit; any
other commit fails before anything is built. The build runs `autoconf`,
`configure --prefix`, `make -j<jobs>` and `make install` as argv, with
Verilator's own `VERILATOR_ROOT` and `VERILATOR_BIN` removed from the child
environment, and every step keeps its transcript under the build tag. Each
transcript is written when its step exits, so a multi-minute `make` shows nothing
until it finishes. The shallow clone of an annotated tag reports
`warning: refs/tags/<tag> <sha> is not a commit!`: git is describing the tag
object it fetched, and the `rev-parse HEAD` check that follows is what the pin is
actually held to. A missing prerequisite is named rather than guessed. The
installed `verilator --version` must report the pinned release. The command then
writes `installation.json` beside the prefix: the pin, the resolved commit, the
banner, the installed tool hashes, the covered `tree` of every installed file
with its digest, the `uncovered` names, the resolved build tools with their
hashes, the host, the interpreter, the job count and the elapsed build. `--jobs` sets
the parallel build, `--timeout` the per-step bound and `--offline` builds only
from an already fetched source. Each of the first two must be at least 1: zero
is refused by name before anything is cloned rather than folded into the host
CPU count or the default bound.
Running it again with that record in place reuses the installation and builds
nothing. The clone is kept beside it at `v<version>.source`, which is what lets
`--offline` rebuild without the network; no build tag owns it and no command
reclaims it, so remove that directory by hand when the space is wanted. The clone
itself is about 65 MB: 54 MB across 10,295 tracked files plus an 8.3 MB `.git`
whose pack is 7.2 MiB, or about 94 MB on disk once block rounding over that many
small files is counted. The directory reaches about 1.8 GB because `make` builds
in tree, so all but that 65 MB is object files a rebuild would replace rather
than source it needs to keep.

Discovery reads the record: an installation counts only with `installation.json`
beside it, so a partially removed tree is never used. `--verilator-bin` wins,
then PATH, then the pinned installation, so an operator-supplied Verilator keeps
working and a host with none needs no PATH edit. No Verilator source or binary is
committed; the cache is outside the repository and the legacy prefix is ignored
build output.

#### Shared host tool cache

The installation lives in one cache per host, so every worktree runs the same
verified build and a fresh worktree never rebuilds it.
[`verilator_install.py`](../../../tools/n2m/verilator_install.py) `cache_root`
resolves it: `N2M_TOOL_CACHE` wins when it names a path (a relative value is
taken against the checkout), otherwise the per-user default outside every
checkout, `$XDG_CACHE_HOME/nand2mario/tools`, on Windows
`%LOCALAPPDATA%\nand2mario\tools`, else `~/.cache/nand2mario/tools`. The
installation is at `<cache>/verilator/v<version>` and the retained clone at
`<cache>/verilator/v<version>.source`. The build child's environment never
selects the cache; a stripped child environment cannot redirect the
installation.

The path is never trust. On every discovery the record beside the tree must name
this pin's `version`, `tag` and `commit`, and every covered installed file must
still hash to the digest the record holds for it, so a stale, foreign, hand-made
or damaged tree is refused by name rather than becoming a silent fallback. A
covered file that is missing, changed, or present but absent from the record is
refused, each by its own path, and a record carrying no `tree` at all proves
nothing and is refused with the command that rewrites it.

A cached installation that fails this check refuses the command; discovery does
not fall through to a per-checkout tree or to PATH behind it. Falling through
would let one worktree's surviving copy mask a poisoned host cache that every
other worktree is about to fail on, so the first bad candidate is reported where
it is found.

The covered set is the whole installation except `bin/verilator_bin_dbg` and
`bin/verilator_coverage_bin_dbg`, the two paths the record names in `uncovered`.
The scope is deliberately wider than the executables: `share/verilator/include`
is compiled into every simulation binary, so a tampered header there changes what
runs exactly as a tampered compiler would. Those two are excluded because no
command here passes `--debug`, so no run reaches them, and they are 236 MB of the
259 MB installed: covering them takes every discovery from about 0.4 seconds to
about 4.4 seconds, for bytes no simulation touches. Checking the other 125 files, 22.7 MB, costs
about 0.4 seconds on the recorded host, which is one pass over those bytes:
`tools` is compared against the `tree` entry for the same path rather than by
reading the file again, so the 21 MB `verilator_bin` is hashed once per discovery
rather than twice.

Every exclusion matches the relative path, never the basename: the two exempt
paths, and `installation.json` at the prefix root. A basename match would also
exempt the `share/verilator/bin` redirectors of the same two names, whose 236 MB
justification does not apply to them, and would let a file planted anywhere in the
tree skip the check by being named after one of them or after the record itself.
An allow-list keyed on a filename is defeated by choosing that filename, which is
the opposite of what this check is for. The
`verilator --version` banner is checked against the pinned release as well,
because the banner is what says which compiler will run: a pinned tree that
disagrees fails, while an operator's `--verilator-bin` or PATH tool keeps its
precedence and its release is recorded as `pin_match` false and carried as a
notice in the simulation record, printed with the run. `doctor` records the same
`pin` and `pin_match` and fails only on the pinned tree's own mismatch.

One installation runs at a time per host. Everything that writes the cache holds
`<cache>/verilator/install.lock`, which records the holding pid, and it follows
the [tag lock's](#cache-rules) rule exactly: a lock whose recorded writer is dead
is the leftover of a killed process, reclaimed once with a stderr notice, while a
live owner keeps the cache and nothing steals by age. An owner that cannot be
read counts as live, so the refusal never advises removing the lock of a running
26-minute build and the empty window between the exclusive create and the pid
write is not mistaken for an abandoned one. Reuse never takes the lock, so one
worktree's discovery is never blocked by another's build, and the reuse check runs
again under the lock in case a concurrent installation finished meanwhile.

`tools verilator` adopts two per-checkout trees an earlier run may have left, and
adopts them independently, because they are separate directories with separate
lifetimes. An installation at `workdir/tools/verilator/v<version>` is verified
against the pin, moved into the cache, its record's `prefix` restated with the
`adopted_from` it came from, and verified again where it lands. Nothing is
rebuilt, because the installed `bin/verilator` resolves its own `VERILATOR_ROOT`
relative to that wrapper's directory, so the prefix relocates. A tree that fails
the check is left where it is for the caller to inspect.

A clone at `workdir/tools/verilator/v<version>.source` is published even when the
cache already holds the installation, which is the ordinary case: gating the
clone's rescue on the prefix's would lose the clone exactly when the prefix is
already safe, and with it `--offline` as a property of this host. A clone is never
a trusted build input wherever it came from: `install` holds its `HEAD` against
the pinned commit and refuses by name before `autoconf` runs, so adoption does
not re-run that gate. `tools verilator` reports both moves as
`adopted: {prefix, source}`.

#### This host builds the pin

The pinned Verilator builds on the recorded development host, so a missing
binary means an unbuilt tool and never an unavailable simulator. The
installation record measured `1599.05` seconds, 26.6 minutes, at `jobs=4`,
producing `Verilator 5.052 2026-09-05 rev v5.052`, while other work ran
concurrently.
There was no compiler failure, no out-of-memory kill and no retry; it needed
neither `-j1` nor a quiet window. A second clean build on the same host at the
same `jobs=4`, under heavier load, measured `2301.22` seconds, 38.4 minutes, so
expect the cost to track the load rather than a fixed figure. The installed prefix is 248 MB, of which the
two `uncovered` debug binaries are 236 MB. Every prerequisite was already
present: `git`,
`autoconf`, `make`, `g++`, `flex`, `bison`, `perl` and `help2man` on PATH, plus
the `lz4.h` and `zlib.h` development headers the FST writer compiles against.
Only `ccache` is absent, and it is optional. Because one host build now serves
every worktree, an author pays that time at most once on this machine.

Native Questa expects `vlib`, `vmap`, `vlog` and `vsim` on PATH or
`--questa-bin <directory>` and uses the caller's license environment. Questa
2025.2 requires `SALT_LICENSE_SERVER` to name a valid SALT service; a legacy
FlexNet feature file in `SALT_LICENSE_FILE` or `MGLS_LICENSE_FILE` is not a
substitute. Obtain the server setting from the license administrator, keep its
value out of repository files and logs, and validate checkout with the installed
`lmutil lmdiag` before running `doctor --sim questa`. Recorded executable
versions and hashes identify the installed tool.

## CI execution boundary

[Builder checks](../../../.github/workflows/builder.yml) validate generation
and host contracts. [Tile runner checks](../../../.github/workflows/tile-pixel.yml)
validate standalone host contracts. Both run locally before merge and by
`workflow_dispatch`, per the [PR policy](../../agents/pull-requests.md#hosted-and-local-checks);
neither executes a simulator or reports licensed RTL acceptance, and their
summaries state this limitation. `PR policy` is the only required hosted check.

Actual local simulator positive and deliberately failing runs are mandatory author
and independent-review evidence; they run under Verilator on Linux. No trusted
remote simulation runner is currently configured. The protected trusted-revision route and required product checks
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
expected-corruption runs through Verilator. The standalone tile runner remains
Verilator-only and does not inherit shared builder selection.
Software commands use modules under `tools/sw/` and the output boundaries below.
The [software contract](../sw/SPEC.md) defines implemented `sw build`
inputs, deterministic artifacts and independent conformance requirements.

## HDL includes

Simulation and FPGA builds share the [dependency resolver](../../../tools/n2m/hdl.py).
Sources are repository `src/` files. An include must name a literal, canonical
repository path such as `src/rtl/common/macros.svh`. Only `.sv` source files, `.svh` headers,
simulation [lint waiver files](#lint-waiver-files) (`.vlt`, hashed but never included
or synthesized) and ASCII path letters, digits, underscore, hyphen, slash and period are accepted.
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

## Accepted vendor sources

Recording an installed vendor file's digest is provenance: it says which bytes
produced a result. Comparing that digest with one fixed constant is a pin: it
ties the project to one vendor installation. The same numbers did both jobs, so
Quartus shipping a different `altera_mf.v` and different ADC control sources on
Linux refused most DE10-Lite targets while the provenance those digests recorded
was never in doubt.

[`vendor_sources.py`](../../../tools/n2m/vendor_sources.py) separates them.
[`accepted_vendor_sources.json`](../../../tools/n2m/accepted_vendor_sources.json)
holds the digests each installation platform has been accepted with, and every
stage that reads an installed vendor file compares what it hashed against that
record:

| The ledger holds | Result | What the record says |
| --- | --- | --- |
| nothing for that source | the digest is written to the ledger | `accepted: recorded`, and a notice names the source and digest in both the `fpga build` and the Questa simulation record |
| the same digest | the stage proceeds | `accepted: unchanged` |
| a different digest | the stage refuses before any tool runs | the refusal names the source, the platform, the accepted digest, the installed one, both releases and how to accept the change |

The platform comes from the installation's own layout: Quartus keeps its 64-bit
executables in `quartus/bin64` on Windows and ships `quartus/linux64` beside the
launcher scripts on Linux, so the tree being hashed names itself and no host
setting can disagree with it. That one fact also resolves the executables
directory, which is why no stage spells one platform's path. A directory outside
a recognized installation has no accepted provenance and is refused there.

The release in `quartus/version.txt` is recorded as provenance and named in a
refusal. It never decides whether a stage may proceed, because an installation
need not carry one and two releases can ship the same bytes. It is deliberately
not part of the ledger key either: an upgrade that changes a vendor file under
retained evidence is exactly what this record exists to catch, so it refuses
rather than starting a fresh record.

A build may only add a source the ledger does not hold, and it never replaces a
digest the ledger already holds. The merge re-reads first, so a concurrent
build's additions survive. That load-modify-save is not locked, so a write
landing inside it could leave a run holding bytes the ledger does not accept; the
read-back afterwards refuses that run instead, naming the digest the ledger ended
up with. One command changes an accepted digest:

```bash
python3 tools/build.py vendor accept --quartus-bin <dir> --source <installation-relative path> --reason "<why>" --json
```

It requires a reason of at least twenty characters, refuses a source whose
digest already matches, and appends the date, the reason and each `from`/`to`
pair to that installation's history. The command writes a tracked file, so an
acceptance is a reviewed source change like any other; that, and not the
command, is the control. A first sighting records for the same reason: the new
ledger line is a working-tree change, and the build's notice says the result was
produced against bytes this installation had not recorded before.

Licence, redistribution terms, purpose and the installation each digest first
came from stay in [dependencies.json](../../../tools/n2m/dependencies.json),
which also names which sources each Intel simulation descriptor resolves. The
ledger holds digests only. Together they answer, for a retained result, which
vendor bytes produced it and whether that installation had recorded them before.

The `windows` entry was seeded from the digests this repository already recorded
for the installation it was developed on, so no check that installation passed
before is weaker now. Every vendor file a stage records goes through the ledger
except two named cases: the six Quartus executables tool discovery probes,
whose control is the matching `--version` banner it records for each of them,
and the simulation model on a
[family exempt from it](#de10-nano-uart-endpoint-image). Everything else is
compared: 33 installed sources, against the 17 the digest constants and the
dependency record pinned before. The 16 that were recorded but never compared are

- the `altsyncram` definition and declaration every family synthesizes through,
  `altsyncram.tdf` and `altsyncram.inc`;
- eleven clock-generation dependencies of [MAX 10 ALTPLL](#max-10-altpll) and
  [Cyclone V Altera PLL](#cyclone-v-altera-pll) — both generators, `altpll.tdf`,
  `altera_pll.v`, `cyclonev_atoms.v`, the three `xml_info/altpll_*.xml` files and
  the three Altera PLL component Tcl files;
- three Intel ADC definitions — `altera_modular_adc_control.sdc`,
  `altera_modular_adc_control_hw.tcl` and `top/altera_modular_adc_hw.tcl`.

[Cyclone IV E ALTPLL](#cyclone-iv-e-altpll) reads one compared source of its own,
`cycloneive_atoms.v`. It was never recorded or pinned before, so it enters the
ledger the ordinary way on its first build and is compared from then on.

Nothing that was compared stopped being compared. Comparing these 16 is why the
rule above needs no further exception, and none of them carries a `--version`
banner, so the ledger is the only thing that would notice a Quartus patch changing
one under a retained fit.

A diagnostic classifier that explains one vendor file's warnings names the
sources it read and refuses a descriptor whose source never reached the ledger.
It states no expected digest: the ledger already refused a source whose digest
changed, and the exact warning text, line numbers, counts and node names the
classifier requires still fail on any other bytes.

## FPGA build

`fpga build --build-id <32 lowercase hex digits, nonzero>` is a comparison-only option for the
targets that carry an identity macro (`controls_proof`, the `v05` board
targets, `sdram_proof` and `nano_uart_proof`). It replaces the fingerprint-derived `N2M_CONTROLS_BUILD_ID` /
`N2M_V05_BUILD_ID` / `N2M_SDRAM_BUILD_ID` / `N2M_NANO_UART_BUILD_ID` constant with the given nonzero value so two builds of
different sources can be compared with `tools/fpga_netlist_compare.py`; the
constant is folded into logic, so fingerprint-derived identities never match
across sources. The record carries `build_id_override: true` and a notice, the
override is part of the cache fingerprint. `fpga program` fails closed: it
programs only an `output/design.sof` still in place beside a readable attempt
`result.json` whose `artifacts` list that file with its current hash, and it
refuses a record that carries the override. A copied, moved or altered `.sof`,
or one without a record, is refused. Other targets reject the option.

An image that lists the [flash reader](../../src/rtl/storage/MAS_flash_library.md#on-chip-flash-ip-boundary)
resolves the installed Intel On-Chip Flash IP through
[`fpga_flash.py`](../../../tools/n2m/fpga_flash.py): the four synthesis files
of `ip/altera/altera_onchip_flash/` and its two hw.tcl definitions must be
[unchanged since that installation accepted them](#accepted-vendor-sources),
the four files are copied beside the generated
project and named as `VERILOG_FILE` assignments, and the QSF carries
`INTERNAL_FLASH_UPDATE_MODE "Single Comp Image"`. No generator runs: the
reader instantiates `altera_onchip_flash` with the derived parameters itself.
The record keeps the IP identity under `tools.onchip_flash`, the cache
requires the staged copies, and the evidence checks `UFM blocks : 1 / 1` and
the configuration mode assignment under `onchip_flash`. `flash-proof` is the
bounded fit of that path. The same image also carries the
[flash library](#flash-library-image): the builder assembles `library.hex`
before the cache check, names it on the reader instance and checks the `.pof`.

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

The external-control synchronizer audit in
[fpga_controls](../../../tools/n2m/fpga_controls.py) reads the fitted netlist
for every button and UART chain. Each first stage must be the sole sink of its
input buffer, reached either directly or through a chain of at most two unary
LUTs; each LUT has one live input, a buffer or inverter mask, no carry, and no
fanout beyond the next stage, and the combined polarity must match the
declared inversion. Two LUTs are accepted because the fitter may pack the
first-stage inverter behind a separate feeder LUT; the fit varies with the
identity constant, so both packings are legal results of the same RTL. Wider
logic, longer chains, ambiguous drivers or bypass fanout fail.

### DE10-Nano UART endpoint image

`nano-uart` places the unchanged UART endpoint behind the
[Cyclone V clocking](#cyclone-v-altera-pll) on that board's
[recorded GPIO pins](../../src/de10-nano-board.md#uart-endpoint-pins). It
requires a nonzero producing identity through `N2M_NANO_UART_BUILD_ID`;
generated assignment and compiled constant must agree, exactly as the DE10-Lite
board images require theirs. Unused package pins are reserved as inputs, which the
fitter reports as tri-stated with a weak pull-up, and every output pin states a
drive strength and a slew rate because the family requires both.

Cyclone V has no M9K block, so a Cyclone V target that lists
[`n2m_intel_ram`](../../src/rtl/common/MAS_memory_primitives.md#vendor-family-selection)
carries the `N2M_RAM_CYCLONEV=1` macro, which selects the M10K text in that one
wrapper. A MAX 10 build preprocesses unchanged.

The Intel memory model requirement is written as one named exemption, so a
family nobody has considered is checked rather than skipped. Cyclone V is the
exemption: no Quartus stage and no Questa gate compiles `altera_mf.v` for it, and
that model is the simulation counterpart of MAX 10 product memory. Its mixed-port
coercion is a Questa diagnostic that
[`intel_memory`](../../../tools/n2m/intel_memory.py) classifies against the same
model, and no Quartus build of either family produces it. A Cyclone V build
therefore records the installed definition, declaration and model hashes as
found, the way the Quartus executables are recorded; every MAX 10 target that
lists the wrapper still refuses a model that
[changed since it was accepted](#accepted-vendor-sources) before any stage runs.

[`fpga_uart_cyclonev`](../../../tools/n2m/fpga_uart_cyclonev.py) owns this
family's evidence and reuses the external-control audit above for everything
that is not family-specific:

- the receive line's four-corner setup and hold paths between the two
  synchronizer stages, analysed at 1100 mV and this board's four corners, each
  met and launched by the fitted system clock;
- the fitted netlist structure: the external port reaches one input buffer, that
  buffer reaches the first stage and nothing else, through at most two checked
  unary Cyclone V LUTs whose combined polarity matches the register's reset
  value, and both stages run on the generated system clock with the qualified
  system reset;
- the fitted memories: exactly the endpoint's six stores with their shapes,
  register stages and read-during-write modes, 13 M10K blocks and 76,272 bits,
  and nothing else.

`nano-uart-invalid` names the MAX 10 ALTPLL system clock as the checked
output-delay clock of the `uart_tx` group. No Cyclone V netlist contains it, so
the Fitter refuses the collection and the build fails naming that endpoint; it
never becomes a passing build. Neither target programs the board or opens a
serial port: the pair ends at a checked fit.

The composed memory check accounts for every logical store and physical atom:
seven direct-profile stores (84 atoms), four 5760-byte snapshot stores (32),
three dual-clock VGA banks (18), and six UART stores (13). The complete inventory
is 20 logical stores, 147 M9Ks and 1,056,616 bits. Existing store, VGA and UART
checkers validate their explicit composed hierarchy, clock/reset roles,
initialization, read shape and bit partitions; the outer inventory rejects
missing or extra atoms and inconsistent fitted capacity. Diagnostic placement
targets retain their own scoped evidence.

```bash
python3 tools/build.py fpga build builder-smoke --quartus-bin <directory> --tag fpga-smoke --json
python3 tools/build.py fpga build builder-invalid --quartus-bin <directory> --tag fpga-invalid --json
python3 tools/build.py fpga build nano-smoke --quartus-bin <directory> --tag nano-smoke --json
python3 tools/build.py fpga build nano-invalid --quartus-bin <directory> --tag nano-invalid --json
python3 tools/build.py fpga build nano-clocking --quartus-bin <directory> --tag nano-clocking --json
python3 tools/build.py fpga build nano-clocking-invalid --quartus-bin <directory> --tag nano-clocking-invalid --json
python3 tools/build.py fpga build nano-uart --quartus-bin <directory> --tag nano-uart --json
python3 tools/build.py fpga build nano-uart-invalid --quartus-bin <directory> --tag nano-uart-invalid --json
python3 tools/build.py fpga build de2-smoke --quartus-bin <directory> --tag de2-smoke --json
python3 tools/build.py fpga build de2-invalid --quartus-bin <directory> --tag de2-invalid --json
python3 tools/build.py fpga build de2-clocking --quartus-bin <directory> --tag de2-clocking --json
python3 tools/build.py fpga build de2-clocking-invalid --quartus-bin <directory> --tag de2-clocking-invalid --json
python3 tools/build.py fpga build de2-vga --quartus-bin <directory> --tag de2-vga --json
python3 tools/build.py fpga build de2-vga-invalid --quartus-bin <directory> --tag de2-vga-invalid --json
```

`--quartus-bin` names the directory holding `quartus_sh`, `quartus_map`,
`quartus_fit`, `quartus_asm`, `quartus_sta` and `quartus_eda`; on Linux that is
the Quartus `bin/` launcher directory, whose scripts set the library path the
`linux64/` executables need. All six must be present, be recognizable and report
one version, or the stage fails naming the first missing tool.

The first command compiles, fits, assembles, and checks the owned MAX 10 fixture.
`nano-smoke` and `nano-invalid` are the same pair for the DE10-Nano: the
[flow proof](../../src/de10-nano-board.md#targets) fits a counter on that
board's LEDs, and it places a drive strength and a slew rate on each LED pin
because Cyclone V reports an output pin without both as an incomplete I/O
assignment. It has no PLL.
`nano-clocking` and `nano-clocking-invalid` are the DE10-Nano's clocking pair:
the [clocking proof](../../src/de10-nano-board.md#targets) fits the Cyclone V
wrapper's two generated Altera PLL instances with the shared reset controller and
timebase on virtual ports, and the invalid target names a MAX 10 ALTPLL clock as
a checked endpoint that no Cyclone V netlist contains.
`nano-uart` and `nano-uart-invalid` are that board's
[UART endpoint pair](#de10-nano-uart-endpoint-image).
`de2-smoke` and `de2-invalid` are the flow-proof pair for the DE2-115: the
[flow proof](../../src/de2-115-board.md#targets) fits a counter on that board's
red LEDs, and it places a drive strength on each LED pin because Cyclone IV E
reports an output pin without one as an incomplete I/O assignment. It has no
PLL.
`de2-clocking` and `de2-clocking-invalid` are that board's clocking pair: the
[clocking proof](../../src/de2-115-board.md#targets) fits the DE10-Lite's own
ALTPLL wrapper, with the shared reset controller and timebase on virtual ports,
for `EP4CE115F29C7`. The invalid target names the Cyclone V Altera PLL system
clock as the checked output-delay clock of the `ready`/`paused`/`sys_count` group;
no Cyclone IV E netlist contains it, so `read_sdc` refuses the collection with
`Error (332000): checked endpoint count mismatch: clock_0`, the Fitter exits
nonzero and the build fails.
Each invalid target must FAIL with exit 1, naming the missing or wrong endpoint;
neither ever becomes a passing build. No command programs the board,
opens UART, or proves physical operation. Design-specific PLL/frame/fit evidence
belongs to the [clocking](../../src/rtl/clocking/MAS_clocking.md) and
[VGA](../../src/rtl/vga/MAS_vga.md) owners, using the
[timing contract](../../src/clocks-resets-cdc.md).

One registry per supported board: the
[DE10-Lite registry](../../../src/fpga/de10_lite/targets.json), the
[DE10-Nano registry](../../../src/fpga/de10_nano/targets.json) and the
[DE2-115 registry](../../../src/fpga/de2_115/targets.json). Each has exactly
`schema_version: 3`, a `board` object and a `targets` object, and target names
are unique across boards, so one name still selects one board. The `board`
object has exactly `name`, `device`, `family`, `timing_corners`, `io_standards`
and `specification`: the device as it is written in the QSF, the Quartus family
name, at least three distinct analysed timing corners of the form
`<Slow|Fast> <n>mV <t>C`, the I/O standard this board supplies on each package
pin it uses, and the repository-relative `wiki/` page that owns that board's pin
and resource data
([DE10-Lite](../../src/board-bring-up.md),
[DE10-Nano](../../src/de10-nano-board.md),
[DE2-115](../../src/de2-115-board.md)). A registry whose specification page
is missing fails. `io_standards` maps a standard to the nonempty list of
`PIN_<letters><digits>` names the board supplies it on; a registry that names a
standard outside the builder's table, or one pin under two standards, fails.
Each named target has exactly `device`, `top`, ordered
nonempty `sources` and `constraints` lists, a `pins` port-to-package-pin
object, and a `virtual_pins` port-pattern list. A target's `device` must equal
its board's; top names are identifiers. The resolved definition carries the
board's `family`, `timing_corners` and the standard each of its pins is
recorded under, and every device-dependent assignment and evidence check reads
them from it, so no device is named in the build path.
Inputs are unique existing repository-relative `.sv` and `.sdc` paths under
`src/`, without traversal or symlink escapes. Physical pins are unique `PIN_<letters><digits>` names; port
names permit an optional numeric or wildcard array index. Each physical
assignment declares the standard its own board records for that pin, and a pin
the board does not record fails naming the port and the pin rather than
defaulting to a voltage the board may not supply. A port on the board's
Schmitt-trigger key input restates its recorded standard as that voltage's
Schmitt input, so the refinement cannot rename the voltage; a recorded standard
with no Schmitt input fails naming the port. An output pin also states whatever
the fitter needs before it stops calling the pin an incomplete I/O assignment
(Quartus 15714): on 3.3-V LVTTL, Cyclone V a drive strength and a slew rate and
Cyclone IV E only the drive strength; on 2.5 V, Cyclone IV E the slew rate as
well; MAX 10 neither. That table is per family and declared standard, not per
board, and a pair absent from it states nothing extra. The DE2-115 is the board
that exercises the per-pin standard: it declares 2.5 V on the nine pins its
[vendor table](../../src/de2-115-board.md#io-voltage-and-what-the-flow-proof-declares)
puts on banks the board does not power at 3.3 V. Declaring the board's
documented voltage is not authorization to program it. HDL uses the bounded
[include contract](#hdl-includes); HDL file reads that are not proven
simulation-only and external/dynamic SDC loads are rejected. SDC permits one literal clock,
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
summary checks for setup, hold and minimum pulse width at every corner the
target's board declares. The DE10-Lite declares Slow 1200mV 85C, Slow 1200mV 0C
and Fast 1200mV 0C, and the commercial Cyclone IV E of the DE2-115 declares the
same three; the industrial Cyclone V of the DE10-Nano declares
Slow 1100mV 100C, Slow 1100mV -40C, Fast 1100mV 100C and Fast 1100mV -40C.
Every reported slack must be finite and nonnegative with zero TNS. The audit
requires zero illegal/unconstrained clock/input/output setup and hold counts, no
ignored SDC assignments, and no structural timing problems. Missing/malformed evidence fails rather than passing
on the tool exit alone. Keep resource totals and all corner slack values.

### Measured reach on Linux

`fpga build` names a missing tool rather than an operating system, so which
targets a host can build is a measurement and not a rule. All 39 registered
targets of the three boards were built on the Linux development host at
`9375432`, against Quartus Prime 25.1std.0 Build 1129 Lite with `--quartus-bin`
naming that installation's `bin/` launcher directory, two builds at a time on its
two physical cores except where noted below. `adc-early` refused in that sweep and
was refitted alone once its cause was fixed, in 110 seconds of wall and 94 of CPU:

| Board | Targets | Reached its intended result | Did not |
| --- | --- | --- | --- |
| DE10-Lite | 25 | 23 | `controls-board`, `v05-controls-board` |
| DE10-Nano | 6 | 6 | — |
| DE2-115 | 8 | 8 | — |

An `*-invalid` target's intended result is its refusal, and each of the eleven
reached the one it names: an invalid clock period for `builder-invalid`,
`nano-invalid` and `de2-invalid`, a filter matching no port for
`de2-vga-invalid`, and a checked endpoint count mismatch for the rest. Every
passing fit kept its `design.sof`, its fit summary and a finite nonnegative slack
at each corner its board declares. No installed vendor file entered the
[ledger](#accepted-vendor-sources) that this installation had not already
accepted, so every result rests on recorded bytes.

Two DE10-Lite targets still refuse, and neither is a limit of this host or of
Linux. Each cause is a mismatch between repository sources that every
installation reads the same way — a constraint and a warning count — and not a
property of any installed toolchain, so no host builds them. `controls-board`
fails on the SDRAM and KEY1 constraints its top declares no ports for
([#904](https://github.com/amichai-bd/nand2mario/issues/904)), and
`v05-controls-board` fails because the ADC diagnostic classifier also counts the
On-Chip Flash IP's accepted warnings
([#908](https://github.com/amichai-bd/nand2mario/issues/908)). Neither is in a
regression subset, a catalogue unit or a CI workflow, which is why each break
went unmeasured. `adc-early` refused for a third such mismatch, an accepted
no-clock count that omitted the ADC backend's own lock row; that count is now
summed from the modules that name the rows and is compared with them for every
registered target by a host unit, without a fit.

Per-target wall ran from 43 to 683 seconds, 6,487 seconds across the 39 results,
so each one is an upper bound under that contention rather than a quiet cost.
The contention is enough to matter: `v05-controls-board` exceeded the 600-second
default per-tool timeout beside another fit, and reached its own refusal in 488
seconds alone at `--timeout 1800`, so the largest images want an explicit
`--timeout` on a host this size. Only that run and `builder-smoke` ran alone.
A second build of the same target reports `CACHED` in seconds.

### Hold path audit

The timing summary keeps one hold slack per clock, and the fitter optimizes
hold only to a non-negative value, so a shrinking slack has no visible
endpoint until it fails. For every image that drives the SDRAM (`sdram_proof`
and any top pinned to `DRAM_CLK`: `v05`, `v05-board`, `v05-controls-board`),
[`fpga_hold.py`](../../../tools/n2m/fpga_hold.py) appends to the audit script,
at each of the three corners, one
`report_timing -to_clock <clock> -hold -npaths 5 -detail full_path` for the
system clock (`u_clocking|u_system_pll|altpll_component|auto_generated|pll1|clk[0]`)
and for `sdram_clk`, written to `output/hold_<corner>_<system|sdram>.rpt`.
`-to_clock` selects paths by their latch clock, which is how the summary
attributes a hold check, so the first row of each report is the path behind
the summary's hold slack for that clock and corner. The six reports are
required evidence and part of the cache inventory.

The evidence records them under `hold_paths`: `npaths`, then `clocks.<label>`
with the `clock` name, `corners.<corner>` (`report`, `found`, `violated`,
`worst_slack_ns` and the `paths` rows: `slack_ns`, `from`, `to`,
`launch_clock`, `latch_clock`, `relationship_ns`, `clock_skew_ns`,
`data_delay_ns` and `hold_uncertainty_ns`, the clock uncertainty TimeQuest
applied to that path's hold check as read from its required-time detail,
entity prefixes stripped from the node names) and `worst`,
the tightest first row across corners with its `corner` and `report`. The
text output prints one `Worst hold (<label> <clock>)` line per clock, naming
the slack, corner and uncertainty. The system clock carries the
[0.150 ns added hold uncertainty](../../src/clocks-resets-cdc.md#timing-constraints),
so its reported slack is the margin above that constructed value. A
report whose delay model, header, table, latch clock, ordering, violation
count or uncertainty rows disagree fails as malformed evidence; a clock without paths records an
empty list and no `worst`. Slack signs are recorded, not judged: a negative
hold still fails through the timing summary as before, and this audit adds
no threshold.
[`test_fpga_hold.py`](../../../tools/n2m/tests/test_fpga_hold.py) covers the
script, parsing, the record shape and the summary lines with synthetic reports.

### Carried ROM image

A target may declare `rom_image`, a `src/sw/targets.json` package name, and the
fitted memory then powers up holding that program, so a board with no host
connection runs it. A target that declares none is unchanged: the declaration
reaches one store instance through a QSF parameter rather than a macro, so every
other target's generated project files and RTL preprocessing are byte-identical.

[`fpga_rom_image.py`](../../../tools/n2m/fpga_rom_image.py) owns the path. Before
the cache check it runs that package's software build, which is the packager, and
hands the image and the digest that build recorded to
[`preload.prepare`](#preloaded-execution-target), the same packager the simulation
preload uses. That rechecks the exact profile length, the digest and the header
and checksums, so an image failing any of them refuses the build rather than
warning. The attempt then holds `preload-rom.mif`, `preload-presence.mif`,
`preload-crc.hex`, `preload.json` and `program.gb`, the file digests enter the
fingerprint (a changed program is a new attempt), and the record names the
carried image under `rom_image` with its package, profile, length, SHA256 and
CRC-32.

The generated project carries
`set_parameter -name INIT_FILE "preload-rom.mif" -to "<store instance>"`
(`fpga_rom_image.rom_path`, one instance path per registered top; a top absent
from that table refuses the declaration by name). Only the
`dmg-direct-v1` profile is carried, whose whole image is the store's lower half;
the loader profile and its [flash library](#flash-library-image) remain the other
way to reach a program, and a target declaring both is refused because both want
one MAX 10 internal configuration mode.

A MAX 10 configures from its own flash, and without ERAM the fitter refuses
memory initialization outright (Quartus 16031), so an image-carrying MAX 10
target also states `INTERNAL_FLASH_UPDATE_MODE "Single Comp Image with ERAM"`,
the mode the Quartus libraries also name `Single Compressed Image with Memory
Initialization`. A family that configures from an external device states nothing
extra. The assembler still writes an `output/design.pof` for such an attempt, in
that mode rather than the flash library's; it is not a board image and
[`--pof` programming refuses it](#flash-programming). The
packager's file addresses the whole 65,536-byte store and defines the image's own
32,768 bytes, so Quartus reports the remaining addresses and the zero it writes
there (113028 and 113027); both lines are classified against the recorded image
length, and a different length changes the required text rather than passing
quietly.

The evidence checks that the QSF carries both assignments once, that every
prepared file still matches `preload.json`, that the fitted RAM summary row names
`preload-rom.mif` on that store, and that the fitted blocks hold the image
itself: each one-bit M9K holds one bit plane of one window of consecutive
addresses, and the multiset of the 64 blocks' `mem_init` words must be the
multiset the declared image requires, so a different, altered or wrongly sized
image fails, down to one bit. Which window a block holds is a fitter decision
recorded in the address decode rather than in the block, so the comparison is a
multiset and does not distinguish a permutation of the eight whole windows from
the image itself; every change inside a window is caught. Quartus states either the power-up attribute or the initialization, so the
initialized blocks carry no `power_up_uninitialized` and the other stores keep
`power_up_uninitialized=true`. The parameters the wrapper actually passed are
read back from the generated `db/altsyncram_*.tdf` of each memory shape: exactly
one must name the carried file and state `POWER_UP_UNINITIALIZED="FALSE"`, and
every other must state `"TRUE"` with no file, so one attempt witnesses both
states of the rule the
[memory primitives contract](../../src/rtl/common/MAS_memory_primitives.md)
gives that parameter.

### Flash library image

The [flash library contract](../../src/rtl/storage/MAS_flash_library.md#flash-layout)
places slot `i` at flash word `0x00800 + i * 0x2000` and the catalogue at
`0x22800`, mirroring the SDRAM layout: `flash_word(a) = 0x00800 + (a >> 2)`.
Its Terms fix the file convention: the IP's Avalon data slave, the Intel HEX
the assembler reads and the double's `$readmemh` image all number the same
words from 0, so `avalon_word(a) = flash_word(a) - 0x00800 = a >> 2`, and
the Intel HEX byte address of slot byte `b` of slot `i` is
`4 * avalon_word = i * 32768 + b`, the SDRAM device byte address itself.
[`flash_library.py`](../../../tools/n2m/flash_library.py) owns the assembly;
[`test_flash_library.py`](../../../tools/n2m/tests/test_flash_library.py)
checks the first and last word of every slot, the catalogue words, the erased
fill, the record format, the registry rules and the external resolution against
a fake pin table and fake cached files. Its `sw library` stage test reads the
real registry offline and skips, naming the missing pins, when the
[shared external cache](#external-rom-cache) has not been filled by one online
`sw library` run.

The registry [`src/fpga/de10_lite/library.json`](../../../src/fpga/de10_lite/library.json)
has exactly `schema_version: 2`, a nonempty `slots` object mapping decimal
slot indices `0`-`15` to entries, and `menu`, the entry at index 16. An entry
is an object carrying `image` and an optional `tagline`; any other key is
refused. An `image` is either a `src/sw/targets.json` package name or
`external:<name>`, a pin of the [dependency manifest](../../../tools/n2m/dependencies.json)
`external_roms.images`. A `tagline` is 1-18 upper-case letters, digits, spaces
or dashes, the text of that slot's
[tagline record](../../src/rtl/storage/MAS_sdram.md#address-space-layout); a
package may declare its own in its
[software target](../sw/SPEC.md) instead, and declaring it in both places for
one slot is refused, so a slot's tagline has one source. Omitting the key is
how a slot declares no tagline, and its record packs zero; an empty string is
refused rather than treated as none. Every package must carry a packaged
runtime profile,
the menu must be a package that runs in `dmg-loader-v1` (the contract's
`profile == LOADER_ID` validity rule), a value may occupy one index only across
both kinds, and each image must be exactly its profile's size: one 32 KiB slot
for `dmg-direct-v1` and `dmg-loader-v1`, two adjacent slots (64 KiB) for
`dmg-mbc1-v1`, whose index is at most 14 and whose second slot must not be
registered (its catalogue entry stays empty), so `n32 + 2 * n64 <= 16`. An
external value is resolved at registry load: an unknown pin, a pin missing
`url`, `sha256`, `size` or `license`, a pin whose `size` is neither 32768 nor
65536, or a 64 KiB pin whose next slot is registered is refused by name.
Today it lists `springtrail`, `stackdrop` and `v05` in slots 0-2, the seven
playing 32 KiB homebrew images in slots 3-9, the 64 KiB MBC1 game PostBot at
slot 10 (its continuation fills slot 11, which stays unregistered) and `menu`
at 16.

A slot is registrable when its image turns the LCD on and is an original game
or interactive demo, or a pinned freely licensed third-party game that has run
on this hardware. Our own registrable images are Springtrail, Stackdrop and the
v05 button demo, every playable image the repository builds. The other
`src/sw/targets.json` packages are verification inputs, not games, and stay
out of the registry: `flow`, `flow-s`, `render`, `render-s` and
`springtrail-unit` are Springtrail CPU unit fixtures whose builds
[`rom_build.py`](../../../tools/sw/rom_build.py) refuses on purpose
(`require_legacy_movement`, `require_legacy_scene`) because they encode the
movement and scene code that predates the current implementation, and
[`test_historical_motion.py`](../../../src/dv/springtrail/test_historical_motion.py)
and [`test_legacy_renderer.py`](../../../src/dv/springtrail/test_legacy_renderer.py)
assert that refusal; `stackdrop-unit` and `stackdrop-short` are routine
runners that keep the LCD off; `linker-basic` and `assets-basic` are toolchain
fixtures. The registry grows only with new game content, which arrives through
its own issues.

#### External images

The external slots hold the [homebrew games that run on this hardware](../../showcase/homebrew-library.md).
Their bytes follow the pin file's redistribution rule: fetched at build time
into the host's [shared external cache](#external-rom-cache) as `<cache>/<name>/`,
verified by size and SHA-256 on write and on every read, never committed; the `library.hex`,
`library.dat` and `.pof` that contain them are build artifacts under
`workdir/`. Each image is validated by its size before packing: a 32768-byte
image must carry header byte `0x147` = `0x00` (ROM ONLY) and `0x148` = `0x00`
(32 KiB) and is catalogued as `DIRECT_ID`; a 65536-byte image must carry
`0x147` = `0x01` (MBC1 without cartridge RAM; the profile has no RAM, so an
MBC1+RAM image is refused) and `0x148` = `0x01` (64 KiB) and is catalogued as
`MBC1_ID` under the `dmg-mbc1-v1` profile name; title bytes `0x134`-`0x143`
are each zero or printable ASCII, with `0x80` (the CGB-compatible flag) also
accepted at `0x143`. Wyrmhole and Rex Run are pinned but not registered:
neither [ever enables the LCD](../../showcase/homebrew-library.md#wyrmhole-and-rex-run-never-turn-the-lcd-on)
under the `dmg-direct-v1` entry state, so a slot for them would only ever show a
blank screen.

| Slot | Pin | Header title | Author | Licence | Pinned artifact |
|---|---|---|---|---|---|
| 3 | `libbet` | `LIBBET` | Damian Yerrick | Zlib | [libbet.gb v0.08](https://github.com/pinobatch/libbet/releases/download/v0.08/libbet.gb) |
| 4 | `airaki` | `AIRAKI1` | furrtek | GPL-3.0-or-later | [airaki.gb, gbdev/database @ 434b8d3](https://raw.githubusercontent.com/gbdev/database/434b8d35af69d6bf8184fe1bc9a4c41294c8ad42/entries/airaki/airaki.gb) |
| 5 | `gb-wordyl` | `GB-WORDYL` | bbbbbr | GPL-3.0-only | [GBWORDYL_0.85_en.gb, gbdev/database @ 434b8d3](https://raw.githubusercontent.com/gbdev/database/434b8d35af69d6bf8184fe1bc9a4c41294c8ad42/entries/gb-wordyl/GBWORDYL_0.85_en.gb) |
| 6 | `max-pirate` | `MAXPIRATE` | Marcel Wehrstedt | MIT | [maxpirate.gb v1.0](https://github.com/MWehrstedt/MaxPirate/releases/download/v1.0/maxpirate.gb) |
| 7 | `alien-invasion` | blank; pinned `ALIEN INVASION` | NiliusJulius | GPL-3.0-only | [Alien-Invasion.gb v1.0.0](https://github.com/NiliusJulius/Alien-Invasion/releases/download/v1.0.0/Alien-Invasion.gb) |
| 8 | `square-fall` | blank; pinned `SQUARE FALL` | bjorn_nah | MIT | [square_fall_v03.gb v0.3](https://github.com/bjorn-nah/square_fall/releases/download/v0.3/square_fall_v03.gb) |
| 9 | `unstoppable-knight` | `KNIGHT` | Rafagars | MIT | [knight.gb 2.2.2](https://github.com/Rafagars/Unstoppable-Knight-GB/releases/download/2.2.2/knight.gb) |
| 10-11 | `postbot` (64 KiB, `dmg-mbc1-v1`) | `POSTBOT` | Tobias Rojahn (MasterIV) | MIT | [PostBot.gb @ 5e9316a](https://raw.githubusercontent.com/MasterIV/PostBot/5e9316ae37761171870fd6350b55725b83d59e6c/PostBot.gb) |

The SHA-256 of every artifact and its licence text are the pin file's; the
library record repeats the licence, the pinned URL and the image hash per row
(`library.images[].licence`, `source`, `image_sha256`, `pin`, `notices`), so
the provenance travels with the flash image it describes.

The catalogue title is header bytes `0x134`-`0x143` verbatim, through the host
loader's own [`image_entry`](../../../tools/n2m/host/library.py). Two pinned
images carry an all-zero header title; for them the pin's `title` (upper-case
letters, digits, spaces and dashes, at most 16) stands in, under the
[catalogue entry rule](../../src/rtl/cartridge/MAS_loader_profile.md#boot-source)
that only an all-zero header takes the fallback and a named header is never
overridden. Four of the images (Libbet, Airaki, GB Wordyl, Unstoppable Knight)
set the CGB-compatible flag `0x80` at `0x143`, the last title byte; the
[menu](../../src/sw/menu/SPEC.md) draws `0x80` and `0xC0` in that cell as
blank, so the flag never shows. Every other title byte of the eight images is
a letter, digit, dash, space or zero, so the
[menu reference](../../../src/dv/menu/reference.py) draws them as written.

Capacity: the eleven registered images (ten 32 KiB, one 64 KiB in slots
10-11) and the catalogue define 106,752 words of the 188,416-word user range,
so four more 32 KiB slots (indices 12-15) remain addressable, and the user
range holds all sixteen slots and the catalogue by construction
(`16 * 8192 + 256 < 0x2E000` words). The compressed bitstream lives in the
separate 672 KiB CFM0, so the slot count does not compete with the design:
the practical slot capacity is the contract's sixteen. The CFM0 usage of a
build is measured in its `.pof` evidence, described below; the `v05-board`
build of this eleven-image registry records 369,711 of 688,128 CFM0 bytes
used (368,193 programmed, 318,417 spare) beside a 427,008-byte
library that matches the `.pof` user range exactly once.

`python tools/build.py sw library --tag <tag> --json` builds every registered
package through the same `sw build` stages under that tag (cached as usual;
`--rebuild` forces them), fetches every external image that is not yet cached
(`--offline` refuses to fetch and fails by name instead), assembles the words
with the host loader's own
catalogue code ([`host/library.py`](../../../tools/n2m/host/library.py)
`image_entry` and `build_catalogue`, so the flash catalogue and a UART load
carry identical entry bytes), collects each slot's
[tagline](../../src/rtl/storage/MAS_sdram.md#address-space-layout) from where it
is authored (the registry entry, or the software target of a package that
declares its own) and refuses one the menu font cannot draw before anything is
built, and writes under
`workdir/builds/<tag>/sw/library/runs/<attempt>/`:

| File | Content |
|---|---|
| `library.hex` | Intel HEX of the whole 736 KiB user range: 16-byte type 00 records, a type 04 extended linear address record at each 64 KiB boundary, one type 01 end record, every record checksummed. Words no image defines are written as `FFFFFFFF`: the assembler fills words a hex leaves undefined between its first and last record with zeros, so the explicit image is what makes the programmed flash read what the double reads. |
| `library.dat` | The Verilator double's `$readmemh` image: one `@<avalon word> <word>` line (5 and 8 upper-case hex digits) per defined word; undefined words read erased. |
| `catalogue.bin` | The 1 KiB catalogue bytes at flash word `0x22800` (17 entries, the 17 tagline records behind them, then zero words). |
| `result.json` | Status, the registry hash, one row per image (index, title, profile ID, CRC-32, flash word, `kind`; a package row adds its attempt, result path, fingerprint and image hash, an external row its pin, licence, pinned URL, notices and image hash) and the three file hashes; mirrored at `sw/library/result.json`. |

No Quartus is needed, so Linux fixtures load the real library through
`library.dat`. `fpga build` of an image that lists the flash reader runs the
same assembly as its `Assemble flash library` stage, offline: an external image
is read from its verified cache and a missing cache fails the build naming the
pin, so a Quartus run never waits on the network (`sw library` fetches). It
writes the three files
into the attempt, adds the registry to the inputs and the file hashes to the
fingerprint (a changed game image is a new attempt), records the same summary
under `library`, and generates
`set_parameter -name INIT_FILENAME "library.hex" -to "<reader instance>"`
(`fpga_flash.reader_path`, the instance the diagnostic classification already
names per top) beside the configuration mode. Quartus reports the file as an
auto-found memory initialization file in `design.map.rpt`. The assembler then
emits `output/design.pof` beside the `.sof`; both are required evidence of a
flash image and both are retained with their hashes. `fpga program --sof`
writes the `.sof`; [`fpga program --pof`](#flash-programming) writes the
`.pof` under the contract's
[programming rules](../../src/rtl/storage/MAS_flash_library.md#programming-the-flash).

The evidence under `onchip_flash` records `init_filename`, the `reader`
instance and `pof`: the `.pof` holds, after its header, the 736 KiB user range
then the 672 KiB CFM0, each 32-bit word stored with its bit order reversed
(`flash_library.pof_words`, observed on Quartus Prime 25.1std). The check
transforms the whole assembled user range, requires it to occur exactly once
in the `.pof` (`user_range_match`, `user_range_offset`), and measures CFM0
from the byte after it: `cfm0_used_bytes` is the last programmed byte,
`cfm0_programmed_bytes` the count of non-erased bytes and `cfm0_spare_bytes`
the remainder of 688,128. A `.pof` that ends before CFM0, holds a shifted or
altered library, or lacks the parameter assignment fails the build. The
assembler enforces the CFM0 fit and emits no `.pof` for an image that does
not fit, so the required `.pof` is the overflow evidence; the contract states
no numeric margin beyond fitting CFM0, so the numbers are recorded, not
thresholded. The text output names the `.pof` and the CFM0
usage after the bitstream only when the record carries `evidence.onchip_flash`;
a non-flash image, whose `.pof` Quartus also writes, prints neither line.

#### External ROM cache

The verified pinned images live in one cache per host, so every worktree reads
the same bytes and a fresh checkout never refetches.
[`host/external.py`](../../../tools/n2m/host/external.py) `cache_root` resolves
it: `N2M_EXTERNAL_ROM_CACHE` wins when it names a path (a relative value is
taken against the checkout), otherwise the per-user default outside every
checkout, `$XDG_CACHE_HOME/nand2mario/external-roms`, on Windows
`%LOCALAPPDATA%\nand2mario\external-roms`, else `~/.cache/nand2mario/external-roms`.
Each pin keeps `<cache>/<name>/image.gb` and `<cache>/<name>/notices/<file>`.

The path is never trust: size then SHA-256 are checked against the pin on write
and on every read, so a shared, stale or damaged cache is refused by name and
never silently replaced. A checkout that still holds the earlier per-checkout
cache `workdir/private/external-roms/<name>/` seeds the host with it: those
bytes are verified against the pin exactly like a download and then published
into the shared cache, and a mismatch is left alone for the caller to fetch or
refuse. Both locations stay ignored and no image byte is ever committed.

Offline reads fetch nothing. A pin the cache does not hold fails by name with
the command that seeds it, `python tools/build.py sw library --tag <tag>` online
once on this host, and names the cache root and the variable, so a fresh
worktree or a Quartus build says what to run instead of stalling on the network.

### Programming backends

Two programmers can configure a device over JTAG, and
[`fpga_jtag.py`](../../../tools/n2m/fpga_jtag.py) decides which one
[`fpga program --sof`](#flash-programming) uses. Quartus's `jtagconfig` and
`quartus_pgm` are tried first; `openFPGALoader` follows. The decision is not tool
presence alone: an available programmer that cannot read a chain holding the
expected board falls through to the next one, because Quartus's `jtagd` answers
without reading either attached cable on the Linux development host. Missing
shared libraries, device permissions, udev rules, stale daemon state and
interference from `openFPGALoader` were each ruled out there by measurement, the
two cables fail with two different errors, and the daemon was not diagnosed;
that diagnosis is not a prerequisite for programming.

`--programmer quartus|openfpgaloader` pins one backend, and `--jtag-cable` names
one cable the way the chosen backend names cables: a `jtagconfig` chain index, or
an `openFPGALoader` cable name (`usb-blaster`, `usb-blasterII`) which also
selects that backend. A pinned backend together with the other one's cable name
is refused rather than resolved, because ignoring either half would use a
programmer or a cable the operator did not choose. Omitted, every cable of every
candidate backend is enumerated read-only and the one reporting the expected
board is used. `--programmer` does not apply to `--pof`, which is refused rather
than silently ignored: the flash image is written by `quartus_pgm`.

Every cable a backend can reach is read before anything is selected, so
`exactly one cable` means the same on either backend: `jtagconfig` prints them
all in one command, and the openFPGALoader backend enumerates each cable and
selects across the results rather than taking the first that answers. Each read
keeps its own `chain-<backend>[-<cable>].log`; the read the programmer acted on
becomes `chain.log`, and a refusal for two matching cables names both. An
enumeration is bounded independently of the programming timeout, and its exit
status decides nothing:
`openFPGALoader --detect` returns success whatever it read, including an empty
chain and a garbled one. `jtagconfig` keeps the 60-second bound it has always
had, because the slow case is a cold Windows `jtagd`; `openFPGALoader --detect`
talks to the cable itself and gets 30. A `jtagconfig` chain is a candidate only
on a supported
board's programming cable, which that tool names `USB-Blaster` for the FTDI cable
and `DE-SoC` for the USB-Blaster II the SoC boards build in; a chain on other
hardware is never selected, however its device reads.

The expected device is the board the registry gives the attempt record's target,
so the check generalises to every supported board instead of naming one device.
A record whose target is not registered, or whose own `device` disagrees with the
registry, is refused: with nothing trustworthy to compare, an image built for one
board could reach another. A reported chain name is a `/`-separated list of the
ordering codes one IDCODE covers, with `(...)` revision groups and `*` for the
package family letters, and an alternative matches when it is a prefix of the
ordering code, because the ordering code continues with the package, speed and
temperature grade no IDCODE carries. `10M50DA(.|ES)/10M50DC` and `10M50D` are the
DE10-Lite's `10M50DAF484C7G`, `5CSEBA6(.|ES)/5CSEMA6` and `5CSE*A6/5CSX*6` the
DE10-Nano's `5CSEBA6U23I7`, and `EP4CE115` and `EP3C120/EP4CE115/10CL120` the
DE2-115's `EP4CE115F29C7`. Exactly one cable must hold exactly one matching device; other
devices keep their place, because a Cyclone V SoC chain also carries its ARM
debug access port, and the matched position is what addresses the write.

`openFPGALoader` has no `.sof` reader, so the checked image is converted in the
operation directory by `quartus_cpf -c <sof> <rbf>`, whose own success line is
required, and the result records the raw image and its hash. This backend is
therefore not a Quartus-free path: it needs `quartus_cpf` for that conversion and
refuses without it, naming the tool.

openFPGALoader is user-installed rather than pinned or vendored, under its
[tool provenance](../../../tools/sim/THIRD_PARTY.md) and the
[dependency ledger](../../../tools/provenance.json): Apache-2.0, contributing no
bytes to any artifact. The argv semantics above were read from release **v1.1.1**,
including `--index-chain` addressing the same chain vector `--detect` prints, and
the result records the banner of the release that performed each write so a later
one can be re-checked against it. Those semantics are not all guarded equally: a
changed success wording fails closed because both `Load SRAM` and `Done` are
required, and a changed device name is caught by the registry match, but a
changed `--index-chain` meaning would not be detected and would address the wrong
chain position. Re-read that relationship, and the MAX 10 routing above, before
accepting a different release. Before that, the
programmer identifies itself: `openFPGALoader --Version` must print a
recognisable `openFPGALoader v<release>` banner, recorded as `backend_version`
and `backend_banner`. The repository does not ship this tool, so a record that
cannot say which programmer wrote a board is not evidence; the version is
recorded, not pinned, and no version is trusted into the MAX 10 path. The load is
`openFPGALoader -c <cable> [--probe-firmware <hex>] --index-chain <position>
--file-type rbf --write-sram --bitstream <rbf>`; `--probe-firmware` defaults to
`blaster_6810.hex` beside the Quartus Linux executables, which a
[USB-Blaster II](../../src/de10-nano-board.md#jtag-chain) needs because its
firmware is volatile. Success requires both `Load SRAM` and `Done`. That proves
the bitstream was shifted, not that configuration completed: openFPGALoader does
not read `CONF_DONE` back, and the result's `scope` says so.

This backend refuses the MAX 10 family outright. openFPGALoader v1.1.1
`Altera::program` routes on family before it looks at the file or the requested
mode, so the `MEM_MODE` its constructor does set for an `.rbf` under
`--write-sram` is discarded and there is no volatile MAX 10 path to select.
`max10_program` then branches on the extension: only a `.pof` goes through
`POFParser`, and anything else — including the `.rbf` this backend builds — goes
to `max10_program_ufm`, which reads it with `RawParser` and, with no
`--flash-sector` given, calls `max10_flow_erase` with mask `0x3` and `writeXFM`.
That erases and rewrites UFM1+UFM0, the internal flash region this repository's
[game library](#flash-library-image) lives in.

On the DE10-Lite's own part that release aborts before any flash access, because
`max10_memory_map` holds only `10M08SAU`, `10M16SA` and `10M25SA` and the 10M50's
IDCODE `0x031050dd` is not among them: `Model not supported. Please update
max10_memory_map.`. That makes this refusal necessary rather than redundant — the
only thing between a `.sof` and a UFM erase on the qualified board is a missing
table entry any later release may fill — so the family is refused outright and no
release is trusted into that path. The MAX 10 stays with `quartus_pgm`, and the
refusal names it.

### Flash programming

`fpga program` takes exactly one image: `--sof <path>` configures the device
volatile as above; `--pof <path>` writes the flash image into the MAX 10
internal flash. [`fpga_program.py`](../../../tools/n2m/fpga_program.py)
`program_flash` applies the `.sof` rules to the `.pof`: the file must exist in
place, carry the `.pof` suffix, not be a link, sit under the repository and be
listed with its current hash in the `artifacts` of the readable `result.json`
two directories up; a `build_id_override` record is refused. The flash rules
follow: the record's `status` is `PASS`, `evidence.onchip_flash` exists, its
`configuration_mode` is `Single Comp Image`, and its `pof` evidence has
`user_range_match` true with a `sha256` equal to the file's current hash. Any
refusal writes `failure.log` before JTAG discovery and names it, as for the
`.sof`.

An attempt that [carries a ROM image](#carried-rom-image) also retains a
`output/design.pof`, and it is the one DE10-Lite `.pof` assembled in a different
configuration mode: `Single Comp Image with ERAM`, whose flash layout is not the
one the flash library's `.pof` evidence describes. It is not a board image and
`--pof` refuses it by name, because its record carries no `evidence.onchip_flash`
at all; the volatile `--sof` load is the only reachable path for such an attempt.
Do not reach past that refusal to `quartus_pgm` by hand.

`--dry-run`, valid only with `--pof`, stops after those checks: it writes
the exact programmer command to `dry-run.log` with `<cable>` in place of the
chain index (or the given `--jtag-cable`), records `dry_run: true`, and never
runs `jtagconfig` or `quartus_pgm`. It proves the record rules and the command
without a board.

Without `--dry-run`, `jtagconfig` is re-read and must report exactly one cable
holding the device its target's board is registered with. The
[backend decision](#programming-backends) does not apply: openFPGALoader's only
MAX 10 path writes the internal flash through its own POF parser, and a flash
write follows the documented `quartus_pgm` operation letters and timing, not a
substitute. Then
`quartus_pgm -c <cable> -m jtag -o "pvb;<pof>"` runs: program, verify and
blank-check. `quartus_pgm --help=o` of Quartus Prime 25.1std Lite lists `BPV`
among the valid operation combinations and gives `-o pvb;file.pof` as its
JTAG programming example, so the letters are used in that documented order.
`--timeout` defaults to 600 s for `--pof` (60 s for `--sof`): the MAX 10
configuration guide gives 52.9 s for CFM0, 22.7 s for CFM1 and 30.2 s for
CFM2 on the 10M50 before verify and system overhead. The explicit success
line `Quartus Prime Programmer was successful. 0 errors, 0 warnings` is
required. The result records `pof`, `pof_sha256`, `operation`,
`configuration_mode`, `cfm0_used_bytes`, `attempt_result`, the selected
`cable`, `devices` and `chain`, the exact `command`, `isp_seconds` measured
around the `quartus_pgm` call, `build_id` and `wire_build_id` when the
attempt carries an identity, `program_log`, `device_state` and `next_step`. The text summary
gives the JTAG chain, the program log, the measured time with the `.pof`
hash, and the next step: power-cycle the board with no host attached; a
bitstream with the boot copier shows the menu from flash. It never offers the
game launcher for a flash image.

### Program records

Both paths write `result.json` into their operation directory
`fpga-program/<id>/` beside `chain.log`, `program.log` or `dry-run.log`, and
the tag's `manifest.json` lists every file there with its hash. Every recorded
path is derived before JTAG discovery. The image paths (`sof` or `pof`,
`attempt_result`) come from the resolved image and the resolved checkout root
in repository-relative POSIX form
([`repository_relative`](../../../tools/n2m/fpga_program.py)); `chain_log` and
`program_log` use `display_path`, repository-relative for the operation
directory under `workdir/`. An image given
relative to the shell's directory, a checkout with spaces in its path and a
Windows UNC checkout such as `\\wsl.localhost\<distro>\...` all record the
same portable form, and nothing after a successful `quartus_pgm` computes a
path. The result carries `device_state`: `changed` after the success line,
`unchanged` for a dry run. A failed command derives it from the retained
`program.log` (`unchanged` when `quartus_pgm` never ran, `changed` when its
success line is present and only the host record failed afterwards,
`unconfirmed` otherwise) and never re-runs the programmer; the operator
decides on a second pass. Both backends' success signatures are read, because
neither one's wording can appear in the other's output.
[`test_fpga_program.py`](../../../tools/n2m/tests/test_fpga_program.py)
covers each refusal, the dry run, the command line, the measured time, the
chain and programmer failures, the CLI text with doubled tools, the portable
record paths for UNC roots, Windows separators, components with spaces and a
relative image input (as pure Windows paths, so the check runs on any host),
the pre-JTAG path derivation and the `device_state` of failed records. It also
covers each [backend](#programming-backends): the fall-through from an
unreadable Quartus chain to a converted volatile load, Quartus keeping the
operation whenever its own chain reads, the MAX 10 refusal, a successful
`openFPGALoader --detect` exit on a garbled chain refused before any write, a
DE10-Lite image refused against a Cyclone V and the reverse, two cables that both
report the board refused on either backend with both named, each board's own
volatile configuration end to end with its own cable and chain position,
`--programmer` refused with `--pof`, a failed conversion, a load without `Done`, and the device
string of every registered board against what each tool prints for it. A board added to the registry
without its own case fails that test rather than a board session. Every
programmer is a fake and no test touches hardware. The board session that programs the flash and observes the
menu at power-up is separate work under the
[bring-up procedure](../../src/board-bring-up.md#flash-programming-procedure).

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
| 15064, exact system PLL `clk[0]` feeding `DRAM_CLK~output` via non-dedicated routing, `sdram-proof` only | The [SDRAM contract](../../src/rtl/storage/MAS_sdram.md#clock-relationship-and-constraints) drives `DRAM_CLK` as the inverted system clock through the fabric to a pin that is not a dedicated PLL output. Exactly one line naming that PLL, that pin and the attempt's generated PLL file is accepted; the routed-clock jitter is inside the contract's 20 ns half-period I/O budget and the board memory test is the acceptance. |
| `check_timing` no_output_delay = 1, `sdram-proof` only | `DRAM_CLK` is the target of the `sdram_clk` generated clock and has no data path, so it is the one output port without an output delay; giving it one makes TimeQuest time the clock network as a data path. The unconstrained-path summary must still show zero output ports and paths, and the clock inventory binds the port to `sdram_clk`. |
| 10036, exactly the 20 vendor data-controller objects `fpga_flash.UNUSED_OBJECTS` in the staged `altera_onchip_flash_avmm_data_controller.v`, images that list the flash reader only | The read-only configuration of the pinned On-Chip Flash IP leaves its write and erase registers assigned but unread. The staged copy must carry the pinned hash and every line, name and line number must match once; any other 10036 fails. |
| 332060, exactly the IP's `flash_se_neg_reg` strobe under the registered reader instance, four lines in `compile.log` and one in `audit.log`, flash images only | The IP's sense-enable strobe register clocks one register inside the UFM atom (`ufm_block~XE_YE_TO_SE_FF`) without a clock assignment; the vendor's own generated project suppresses this message with `MESSAGE_DISABLE 332060`. Here it is classified by exact node and count and never suppressed. The same strobe is the one accepted `Unconstrained Clocks` row (setup and hold both 1) when `report_ucp` names it as the only unconstrained target, and it and the atom register are two accepted `no_clock` rows named exactly beside the PLL lock events. |
| `check_timing` virtual_clock = 1, exactly “No virtual clock was found.” | The fixture's I/O delays reference its physical clock. No virtual reference clock is required. Every other structural check still must be zero. |

The checked Quartus 25.1 `v05-board` 12125 set is
`n2m_system_pll_altpll.v`, `n2m_pixel_pll_altpll.v`,
`altsyncram_dam2.tdf`, `altsyncram_ram2.tdf`, `altsyncram_jll2.tdf`,
`decode_h7a.tdf`, `mux_l1b.tdf`, `altsyncram_9km2.tdf`, `mux_q1b.tdf`,
`altsyncram_pgm2.tdf`, `altsyncram_bam2.tdf`, `altsyncram_77m2.tdf`,
`altsyncram_v6m2.tdf`, `altsyncram_cbm2.tdf`, `decode_b7a.tdf`,
`mux_12b.tdf`, and `altsyncram_lgm2.tdf`. The classifier requires this
complete set when any 12125 line appears; the order of Quartus diagnostics is
not significant.

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

### DE2-115 video DAC

`de2-vga` places the existing pixel path on the DE2-115's ADV7123 video DAC,
behind the same two ALTPLL clocks
[`de2-clocking`](../../src/de2-115-board.md#targets) generates. The frame bridge,
the scan and the clocking wrapper are unchanged and their instance hierarchy is
the DE10-Lite's, so the
[VGA proof profile](#vga-proof-profile) above owns every CDC exception, bundle
bound, output bound, skew bound, RAM shape and corner report. The board page owns
the [bit alignment and the DAC control values with their vendor
sources](../../src/de2-115-board.md#driving-the-vga-dac).

Three things follow the board rather than the profile, and
[`fpga_vga_dac.py`](../../../tools/n2m/fpga_vga_dac.py) holds them:

- **The output profile.** A board states its channel names, its channel width and
  its two sync pins; `fpga_vga` derives the checked port list and the physical
  register behind each pin from them. `n2m_vga_scan` builds every channel by
  repeating the two-bit `gray_out` pair, so channel bit `k` carries
  `gray_out[k % 2]` however wide the channel is, and the fitter packs the original
  plus one duplicate per further pin of the same bit. The DE10-Lite's four-bit
  ladder gives twelve RGB pins and six copies of each bit; this board's eight-bit
  channels give twenty four and twelve. Both are checked as an exact
  register-to-pin map in the fitter table and in the output and skew reports; a
  missing, extra, shared or misnamed copy fails.
- **The family's fitted RAM atom.** `cycloneive_ram_block` where MAX 10 fits
  `fiftyfivenm_ram_block`, for the same M9K block. Only the atom's name follows
  the family: the three bank owners, the parameter set, the clock and reset roles,
  the shade bit each atom takes and the bit partition are the design's and are
  stated once. The M9K and memory-bit totals are checked as the used count the
  fitted design contains, 18 blocks and 138,240 bits; the capacity each row
  divides by is the device's, which the fit summary's `Device :` line already
  binds, so it is not part of what the check proves.
- **The DAC's own pins.** Every DAC pin states an 8 mA drive strength, which is
  all this family's 3.3-V LVTTL fitter asks for. `vga_clk` carries the pixel clock
  inverted, declared to the Timing Analyzer as the generated clock `vga_dac_clk`
  on that port, the same way the SDRAM image declares `sdram_clk` on `DRAM_CLK`;
  the clock inventory requires the row, its source, unit ratio and `-invert`, and
  binds it to that port. As with `DRAM_CLK`, the port carries a clock instead of
  data, so `check_timing` reports exactly one `no_output_delay` endpoint naming
  it; a target with no pin clock accepts none. The checked netlist must show the
  clock pin's buffer taking the complement of the fitted pixel clock net, and each
  control pin's buffer taking the constant the board specification records, so a
  documented value that did not reach its pin fails.

The DAC adds two fitter diagnostics the resistor ladder cannot produce, and both
are classified rather than hidden. `Warning (13024)` with one `Warning (13410)`
line per pin reports the two deliberately constant control pins: exactly that pin
set, each with its documented level, each naming the source file the attempt's own
project file registers for this top. `Warning (15064)` reports the pixel clock
reaching the DAC's clock pin through the fabric rather than a dedicated PLL output
pin: exactly one line, naming the fitted pixel PLL, `clk[0]`, `vga_clk~output` and
one of the attempt's own generated PLL files. Another pin, another level, another
PLL, another file or a second line stays unexplained and fails the build.

`de2-vga-invalid` shares every source and pin and sources the generated DAC clock
from the Cyclone V Altera PLL's output counter, which no Cyclone IV E netlist
contains, so the pin clock has no source and the build fails naming it. A passing
`de2-vga` fit is therefore evidence rather than an absent check. Neither target
programs the board: the pair ends at a checked fit, and no picture has been
observed.

## Source and workspace boundary

- Root `tools/` contains checked-in project automation.
- `workdir/tools/` contains downloaded or provisioned external tools, except
  those a [host cache](#shared-host-tool-cache) holds outside every checkout
  so one provisioning serves every worktree.
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
│           ├── library.hex
│           ├── library.dat
│           └── output/
├── fpga-program/
│   └── <id>/
│       ├── result.json
│       ├── chain.log
│       └── program.log or dry-run.log
├── lint/
│   └── questa/<attempt>/
│       ├── result.json
│       ├── commands.log
│       ├── compile.log
│       └── elaborate-<top>.log
└── sw/
    ├── library/
    │   ├── result.json
    │   └── runs/<attempt>/
    │       ├── library.hex
    │       ├── library.dat
    │       └── catalogue.bin
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

An explicitly selected test writes its authoritative result to:

```text
workdir/builds/<tag>/sim/test/<test-name>/<backend>/
```

A [regression subset](#regression-subsets) member writes to the same
backend-qualified location, and the aggregate to:

```text
workdir/builds/<tag>/sim/regress/summary.json
```

The simulation stage publishes the backend-qualified `result.json` atomically. It records
status, fingerprint, provenance, commands, and hashes of immutable artifacts under
`<backend>/attempts/<id>/` and `compile/<backend>/<test-name>/<id>/`. A new
attempt never modifies an old attempt. Each authoritative record includes
`authoritative_result` naming itself. Each attempt contains `sim.log`,
`result.json`, `waves/`, and `coverage/` (empty until coverage is implemented).

For existing readers, `sim/test/<test-name>/result.json` and `sim.log` are
atomic mirrors of the last completed run on either backend. The mirror carries
the same full result schema and its backend-qualified `authoritative_result`.
It is never a cache input. Backend-specific consumers, including regression and
baseline readers, use the qualified path. Corrupting the generic mirror cannot
invalidate or impersonate a backend cache; the next cache hit repairs it.

A [prepared attempt](#prepared-attempts) is created under the same attempts
directory before the run that adopts it, with its `prepared.json` receipt.
Before execution, the published record becomes `RUNNING`, preventing reuse after
interruption. Completion publishes `PASS` or `FAIL`; a failed forced rebuild
invalidates the earlier success for that backend stage and preserves both attempts.
Discovery or preparation failure also invalidates that backend's prior success.
If discovery fails before an immutable attempt exists, the backend-qualified and
generic `sim.log` mirrors are atomically replaced with the failure transcript;
neither may retain an earlier PASS log beside the new FAIL result. An unsupported
target/backend pair is rejected before the workspace is opened, so it publishes
neither a new result nor a new log.
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
`sim/regress/.lock`, a tag whose `.lock` records a live or unreadable
writer, and a tag with a [preparation in progress](#prepared-attempts); a dead
writer's `.lock` does not hold the tag. Links inside the tag
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
addresses/command IDs, map overlap/gaps, inconsistent ROM/frame sizes,
duplicate or zero profile IDs, an MBC1 bank geometry that does not tile the ROM
range, and a ROM store smaller than a profile image fail.
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

An FPGA target may declare the bounded `pll` definition: input period 20000 ps
and output multiplier/divisor 63/125, with `system_divide: 2` adding a second
instance that divides the same reference by two. These settings implement the
[clock contract](../../src/clocks-resets-cdc.md), which owns the selected rates.
Other ratios are rejected.

Generation and every clocking check are per device family, because the vendor IP,
its instance hierarchy, its fit-report shape and its netlist primitives all
differ. [`fpga_clocking.py`](../../../tools/n2m/fpga_clocking.py) maps the board's
declared `family` to the one module that owns them:
[`fpga_pll.py`](../../../tools/n2m/fpga_pll.py) for MAX 10 ALTPLL,
[`fpga_pll_cycloneive.py`](../../../tools/n2m/fpga_pll_cycloneive.py) for
Cyclone IV E ALTPLL and
[`fpga_pll_cyclonev.py`](../../../tools/n2m/fpga_pll_cyclonev.py) for the
Cyclone V Altera PLL. The map is one explicit entry per family, never a lookup
that falls back to another family's checks; the two ALTPLL families share one
implementation's code through their own modules rather than by matching loosely.
A target that declares generated clocks on a family with no
implementation is refused when its definition resolves, before any tool launches;
there is no path that builds such a target with the clocking checks skipped. Each
implementation also declares the proof tops whose hierarchy its checks recognize,
so a target cannot point a family's checks at a top they do not describe. The
reset chain audit and its report inventory are the family-neutral part, because
the chain register and pin names come from the shared `n2m_reset_control`.

### MAX 10 ALTPLL

The generator owns 50% duty, zero phase, normal operation and CLK0
compensation. `system_divide: 2` generates `n2m_system_pll` divide-by-two with
LOW bandwidth. Each instance has its own generated HDL and command log.
Supported proof tops retain the exact `u_clocking` wrapper hierarchy;
the v0.5 adapter scopes bridge path checks under `u_system`. Other hierarchies
need an explicit checker extension.

`qmegawiz` comes from the explicit Quartus directory. Its executable, ALTPLL
definition/rules/wizard XML and primitive declaration hashes enter the request
fingerprint. The generated HDL, generation command/log and vendor auxiliary
files remain under the immutable attempt. The generated HDL is checked against
the requested parameters and loaded directly; generated QIP Tcl is retained but
not evaluated. Reuse requires this evidence as well as the complete fit/timing
inventory. Generator errors fail the request and remain retained; partial
output is never accepted. One exact failure is retried: under Quartus Prime Lite
25.1std on Windows the generator's `mega_altpllq.exe` faults in
`mega_mwizcq.dll` (access violation, Windows Application log event 1000) on
about one launch in three, and `qmegawiz` then exits 3 with an empty log. The
builder relaunches the same generator command, up to six launches in total,
only for that signature: exit 3, no timeout, empty log. Standalone probes saw
8 of 20 and 3 of 15 launches fail with up to three consecutive failures; a
private `TEMP` and a pause between launches did not change the rate, and
dropping `-silent` opens the wizard GUI so its effect could not be measured.
The bound covers a run of five. Every launch stays in `commands`
with its exit code and `retried: true`, and `generator_retries` lists each
retried attempt. A reported failure, a different exit code, a timeout or a
sixth silent exit fails the request. A later explicit build
request creates a separate attempt.

### DE2-115 system image

[`fpga_de2_system.py`](../../../tools/n2m/fpga_de2_system.py) owns what the
DE2-115's system image adds on top of the checks the composition's own owners
already carry. The image is
[`de2_system_proof.sv`](../../../src/fpga/de2_115/de2_system_proof.sv) binding
`n2m_clocking` and `n2m_v05_system` to that board, so every clocking, memory,
CPU, pixel-path and endpoint check reaches it through the module that owns it, one
hierarchy level down; that level is applied by rewriting the shared checkers'
`u_bridge|` strings, exactly as the DE10-Lite's composed image does.

**Ports.** The placed and virtual port sets are stated, not derived, and a
definition that does not match them is refused before any tool launches. The pin
numbers themselves stay on the
[board page](../../src/de2-115-board.md); this module never restates one. What it
refuses is a dropped readout pin, a picture pin moved to a virtual one, or an
extra virtual output, on an image someone will program.

**Readout pins.** Each of the 56 seven-segment pins and the 29 video pins states
the output settings `OUTPUT_IO_COMPLETION` gives for the standard *that pin's own
board record supplies*, so the image declares a slew rate on its 2.5 V digits and
only a drive strength on its 3.3-V LVTTL ones. The
[seven-segment group is not one voltage](../../src/de2-115-board.md#seven-segment-displays):
the vendor fixes four of the 56 and leaves 52 to two different jumpers, with the
boundaries falling inside digits, so this is per pin and not per group.

**Readout contents.** The image publishes its 128-bit build identity and the
CRC-32 of the carried ROM on its own displays, because this board has no host to
ask. The identity is the same `N2M_V05_BUILD_ID` macro the DE10-Lite's composed
images carry, checked in the generated project and as the compiled constant the
synthesis report states, twice: the wrapper's and the composition's. The CRC is
`N2M_DE2_ROM_CRC32`, taken from the
[packager's own record](#carried-rom-image) of the image it wrote into this
attempt, and checked the same two ways. A constant in a source file is not
evidence that it reached the design, so both ends are read every build, and a
record without a 32-bit CRC refuses.

**Unused pins.** This image drives no bus of its own, so the project reserves
every package pin it does not place as a tri-stated input, and the board's SDRAM,
SRAM, flash and Ethernet devices meet high impedance rather than a driven pin.

**Composed evidence.** The [VGA proof profile](#vga-proof-profile) runs on this
board's eight-bit output profile with the blank-control chains selected, because
this composition's PPU asserts blank and that assertion crosses from the pixel
clock to the system clock; the standalone
[video DAC fixture](#de2-115-video-dac) generates its own pixels and asserts none.
The DAC's own clock, blank and sync pins are read out of the fitted netlist by
that fixture's checker. Each of the twelve asynchronous control inputs carries the
shared checked synchronizer chain, per corner and per check; `KEY[0]` is not among
them because it is the reset and the reset controller owns its chain.

**Pin clocks.** The DAC's inverted pixel clock is expected of any target that
places `vga_clk`, not of one top by name, so both this board's images declare it
and a target that places the port and declares no clock fails the clock inventory
instead of passing with a clock missing.

```bash
python3 tools/build.py fpga build de2-system --quartus-bin <directory>
python3 tools/build.py fpga build de2-system-invalid --quartus-bin <directory>
```

`de2-system` must PASS with the fit, positive slack at each of the board's three
declared corners, the carried image's fitted contents, the readout's identity and
CRC constants, the DAC's pin levels and every control chain's per-corner reports
retained. `de2-system-invalid` must FAIL: it shares every source and pin and
understates the readout's constrained endpoint count by one, so the generated
collection check fails inside the fitter with
`Error (332000): checked endpoint count mismatch: ports_0`, `read_sdc` reports
`Critical Warning (332008)` and `Error (171000): Can't fit design in device`
follows, because the fitter has no constraints to place against. Both errors belong
to the control. A target that instead names a package pin the board record does not
record refuses when its definition resolves, which every registry reader triggers,
so that refusal is covered by a unit test rather than by a registered target.

This image's core also has to start, which no fit shows. The
[`host-free-boot`](../../src/dv/integration/SPEC.md) simulation runs the
composition twice from one reset — once with the carried profile and once without,
every other input identical — and requires the first to release pause, tick, fetch,
retire and select the physical input source while the second stays paused and never
ticks.

### Cyclone IV E ALTPLL

ALTPLL serves this family, so
[`fpga_pll_cycloneive.py`](../../../tools/n2m/fpga_pll_cycloneive.py) reuses the
MAX 10 module's generation and every one of its checks and states only what the
family changes. Four things do:

- the generator's `INTENDED_DEVICE_FAMILY` and the `intended_device_family` the
  generated HDL must state back, which are the family itself; each family's
  checker refuses the other's string;
- the installed simulation atom model whose hash enters the request fingerprint,
  `cycloneive_atoms.v` against `fiftyfivenm_atoms.v`, each compared against
  [its accepted digest](#accepted-vendor-sources); the generator, the ALTPLL
  definition, rules, wizard XML, primitive declaration and register model are
  shared;
- the fitted netlist primitives, named `cycloneive_*` where MAX 10's are
  `fiftyfivenm_*`, with the same types and output ports but for two the set
  leaves out: the ADC block and the internal flash, which this family does not
  have. The M9K atom is present because [`de2-vga`](#de2-115-video-dac) places the
  frame bridge's three banks, and `altsyncram` selects M9K on this family exactly
  as on MAX 10. The lock checker takes the family's set, so an undeclared
  primitive still fails rather than hiding a sink;
- its own proof tops, `de2_clocking_proof` and `de2_vga_proof`, both of which fit
  the DE10-Lite's `n2m_clocking` wrapper in place, so the recognized hierarchy is
  that board's and only the top names are this one's;
- one further fitter caution, below.

Everything else is shared because it was measured identical: the wrapper and
instance hierarchy, the solved `M=104, N=8, C=26` and `M=63, N=5, C=25` counters
with their 650 MHz and 630 MHz VCOs, both PLLs on `Dedicated Pin`, the analysed
three-clock inventory at 20.000 ns, 40.000 ns and 39.682 ns, the 176127 merge
refusal, the reset chain, and the whole parallel lock topology down to the LUT,
clock-enable and register parameter sets. The definition is only the parallel one,
so the single-PLL lock checker, which recognizes MAX 10 primitives only, is
unreachable here. `corner_slacks` stays empty for both ALTPLL families because
ALTPLL publishes no VCO clock to the Timing Analyzer.

The family's EDA netlist carries delays, so it opens with one
`initial $sdf_annotate("<name>.sdo")`. A system task call in an initial block
declares no net and drives no port, so the parser recognizes exactly that
statement and consumes it; a second one, another system task or another file
extension fails. MAX 10 devices get the functional netlist only (Quartus 10905)
and never emit it.

The DE2-115 brings its 50 MHz reference to one dedicated clock input, and this
composition has two PLLs, so the Fitter places one where the pin arrives over the
remote dedicated path and reports
`Critical Warning (176598): ... input clock inclk[0] is not fully compensated
because it is fed by a remote clock pin`. Exactly one such line is explained, it
must name one of the two fitted PLL instances, and the pin it names must be the
one the attempt's own project file assigns to `clk_reference`; another pin, a
third instance, another cause or a second line stays unexplained and fails the
build. Both PLLs still take the pin over a dedicated path, which the fit check
requires, and no timing path in this composition references the reference pin.
Forcing the remote PLL to a location the pin does not reach that way replaces its
dedicated clock path with a routed one instead of removing the fact; the caution
is recorded with that reason rather than hidden.

[`test_fpga_cycloneive.py`](../../../tools/n2m/tests/test_fpga_cycloneive.py)
covers the dispatch, the definition, the generator command, the generated-HDL
family string in both directions, the atom model in the fingerprint, the shared
parallel fit check with its rejections, the lock topology in this family's atoms
with the MAX 10 table still refusing it, the annotation bound and the
compensation caution's bounds. The abstract lock fixture is
[the parallel one](../../../tools/n2m/tests/test_fpga_parallel.py) parameterised
by the family's atom set, so one topology serves both ALTPLL families.

### Cyclone V Altera PLL

ALTPLL does not serve Cyclone V: `qmegawiz` refuses the family and names MAX 10
as the only one it supports. The
[Altera PLL IP](https://www.intel.com/content/www/us/en/docs/programmable/683359/current/pll-intel-fpga-ip-core.html)
takes its place. `ip-generate` from the explicit Quartus installation's
`sopc_builder/bin` produces one wrapper and one QIP per instance, named
`n2m_pixel_pll_cyclonev` and `n2m_system_pll_cyclonev`, for the target's own
device and family. Quartus ships it as a shell script on Linux; the Windows
spelling has never been observed from this repository, so Windows accepts
`ip-generate.exe` or `ip-generate` and the refusal names every candidate it
looked for instead of asserting a filename nobody here can confirm.

The request states the physical counters, not a desired frequency: the 50 MHz
reference, the M, N and C counters, one output clock, `locked` enabled and
`direct` operation. The IP then derives the rest and writes it into the generated
HDL, including the VCO frequency, the VCO post-scale divider K and the loop filter
settings, so the intended oscillator is a recorded design fact instead of a
solver's choice recovered from a report. The system PLL states `M=26, N=2, C=26`
and the pixel PLL `M=63, N=5, C=25`, both with `K=1`, which give the contract's
25 MHz and 25.2 MHz from 650 MHz and 630 MHz oscillators. The checker refuses a
configuration whose oscillator leaves the
[datasheet VCO range](../../src/de10-nano-board.md#pll-vco-range), whose counters
miss the contract frequency, or whose post-scale divider is neither 1 nor 2, before
any tool launches. The oscillator is the stated
figure multiplied by K, so a design that legally uses `K=2` to reach a low output
is accepted while one that states no post-scale divider at all is refused.

The generator's executable, the IP's component/rules/callback
Tcl, the `altera_pll` primitive and the Cyclone V atom and register models enter
the request fingerprint. The generated HDL is checked against every stated
parameter: the counters as the high and low half-periods the hardware programs,
the bypass and odd-duty flags each divide implies, the VCO frequency, the
post-scale divider, the loop filter, and that all seventeen other output clocks
are off and bypassed and the four ports are exactly `refclk`, `rst`, `outclk_0`
and `locked`. The generation log must report an implementable PLL and exactly its
two files. Generated QIP Tcl
is retained but not evaluated, so the compensation mode, the auto-reset setting
and the bandwidth preset are written into the project from the checker's own
constants. Without the compensation mode the fitter warns that the PLL has no
clock to compensate (177007) and compensates every output. There is no generator
retry: the Windows ALTPLL crash signature does not apply.

Stating the counters makes the IP instantiate its Cyclone V PLL directly rather
than the family-generic inference, so every fitted atom sits under `cyclonev_pll`
and that branch leaves its unused LVDS, external-clock and DLL outputs
undriven. Each resulting diagnostic is named exactly and explained against its own
evidence: 10034 for those seven vendor output ports, twice over for the two
instances; 12030 for the vendor's own one-bit connection to a two-bit external
clock port; and 14284, 14285 and 14320 for the six phase-shift tie-off nodes per
instance that synthesis removes. The synthesis connectivity report independently
shows the wrapper leaving those ports unconnected. An unpredicted port, node or
message body fails the build, and so does a missing or repeated message. Each
message's trailing `File:` and `Line:` suffix is matched by shape only, because it
carries the installed Quartus path; 10034 states its vendor file and line in the
message body itself, where both are exact.

The fit report's PLL Usage Summary is bound to the two wrapper instances and
checked value by value: PLL type, feedback clock type, bandwidth, reference
frequency and source, VCO frequency, operation mode, enable, fractional
division, self-reset, reference clock input, and the output counter's own owner,
frequency, duty, phase and counter. The solved `M`, `N` and `C` counters are
checked exactly, so a different solution fails rather than passing quietly; the
fit summary must report both PLLs as physical resources. The analysed clock
inventory is exactly five clocks: the reference, each PLL's VCO clock and each
output counter clock, with their periods, ratios and masters. Both VCO clocks
also need a minimum-pulse-width result at every corner.

Cyclone V has no counterpart to the ALTPLL lock event latch, so `check_timing`
must report no register without a clock at all. The evidence is the lock
qualification itself, read from the checked functional netlist: both PLLs take
the reference through its input buffer and their reset from the one bootstrap
register that runs on that raw reference; one lock gate combines both raw locks
with that reset, and all eight combinations must still propagate the reset and
either lock loss; the gate reaches nothing but the two lock sampling registers'
clears, and those registers run on the generated system clock. Supported LUT,
clock-enable and register parameter sets are exact, every critical net must have
one driver, and the sampling pipeline's constant or buffer feeder LUT is
resolved. An unsupported primitive, an extra consumer or any no-clock row fails.
The netlist's own inversions are resolved before each truth table is evaluated.
The reset register holds the complement of the contract's `pll_areset`, because a
Cyclone V register clears asynchronously to zero and the contract powers that
reset up asserted. The IP's Cyclone V branch drives the fractional PLL's
active-low `nresync` with the complement of its own active-high `rst`, so that
register's released level reaches the PLL directly. The port polarity convention
of the vendor's PLL reset input is the vendor's; the checks bind the structure,
and no hardware claim is made about this board.

### Checked timing assignments

Optional declarative `timing` assignments produce owned SDC with checked exact
asynchronous-reset pins and output clock/port collections. Every collection must
match its declared count. Reset exceptions terminate only at named `clrn` pins;
they do not cut synchronized reset consumers or whole clock domains. Output
delays explicitly include source latency. Arbitrary Tcl bodies and external
constraint loads remain unsupported in source SDC.

### MAX 10 lock event evidence

The MAX 10 ALTPLL lock output contains the vendor's documented event latch when
`areset` is enabled ([PLL control signals, section 2.3.6][lock-guide]). Its raw
`locked` transition clocks a constant-one D input; PLL reset clears the latch,
and output logic still propagates raw lock loss. This is not a periodic datapath
clock. A single-PLL proof has one such `no_clock` row; the parallel system/pixel
wrapper has exactly two. The ADC composition adds its separately checked vendor
row, and an ADC proof that generates no PLL of its own reports that row alone.
The audited count is the sum of the rows each owner names: the family's clocking
module for the instances the target generates, the ADC backend for its own
dedicated PLL, the On-Chip Flash IP for its strobe pair. Each clocking family's
count is the length of the rows it names, so the two cannot state different
things. Because both statements come from the registry and those modules, a host
check compares them for every registered target without a fit, and ties the ADC
top set to the targets that compile the backend. The builder explains these rows
only after checking the generated functional netlist: latch input/reset/initial state, the lock gate
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

### Retained clocking evidence

The raw row and vendor netlist remain evidence. All functional unconstrained-path
counts must stay zero. The reference and both generated clocks require setup, hold, recovery, removal, and
minimum-pulse results at every required corner. Exact adjacent reset-stage
setup/hold reports prove the release chain remains timed. CDC/MTBF reports are
retained; their reset-chain identification is not a hardware reliability claim.
The functional netlist writer's exact diagnostic 10905 explains that MAX 10
supports functional, not timing, simulation netlists; TimeQuest supplies timing.
The exact diagnostic 176127 is explained only for the verified system/pixel
pair and one of its two generated `db/` files: their distinct required ratios
prevent PLL merging. Quartus names the two PLLs in either order and cites
whichever generated file it visits second; the order varies between targets
and builds within one release. The classifier compares the pair and the file
as sets, accepts at most one such line, and rejects any other pair, path or
text. Bandwidth, routing and other timing diagnostics remain failures.

A Cyclone V clocking target explains exactly two diagnostics, each against its
own report. 12241 counts the generated wrapper's unconnected optional Altera PLL
ports; it is accepted only after the synthesis report's two port connectivity
tables are found to name exactly the two PLL instances and exactly those ports
with those severities. 330000 is the cost of the checked endpoint collections:
they name the generated PLL output clocks, which exist in the fitter and Timing
Analyzer netlists but not in the pre-synthesis one, so Analysis & Synthesis
cannot initialize a timing netlist and skips timing-driven synthesis. The fitter
and the Timing Analyzer read the same constraints where those clocks do exist,
and the four-corner slack is retained. Any other identity, count, owner or
severity fails. Synthetic report mutations prove each rejection in
[`test_fpga_cyclonev.py`](../../../tools/n2m/tests/test_fpga_cyclonev.py), which
also covers the family refusal, the generated-HDL and generator-log checks, the
fit and clock-inventory checks, and the netlist topology mutations.

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

`python tools/build.py sw library --tag <tag> --json` builds the packages the
[flash library registry](#flash-library-image) names and writes the flash
image files the FPGA build and the Verilator double read; see that section
for the files, the word convention and the record.

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
peer. These registered peer-driver targets use the
[Verilator peer driver](#verilator-peer-driver) and reject Questa before tool
discovery. No legacy Tcl peer path is registered.
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
identity and independent scoped review. Without `--json` the same record prints
as text: the base and head commits, each fallback reason, one `name: decision
reasons` line per unit, then the selected and review-candidate counts.

A host unit with declared [`inputs`](#host-unit-closure) is judged on its
derived modules, declared files and the tracked files under declared
directories: a changed path in that closure selects it with `changed inputs:
PATHS`; a closure whose bytes all equal the base makes it a review candidate
with `validated declared host closure equal base`; anything else selects it.
A host unit without a declaration is always `selected unknown closure: no
declared inputs in src/dv/builder/catalogue.yaml`.
New, deleted, renamed, unmapped, tool, configuration or catalogue changes force
conservative fallback for every unit, host or simulation. Invalid input closure, dynamic data/import behavior,
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
Without a global fallback it hashes each closure path once against the base.
A simulation with no changed input is validated through
[`load_target`](../../../tools/n2m/simulation.py) before its call-free
qualification; one memo per report keeps the parsed registry and each import
walk of the shared test modules and fixture builders, so the cost does not
depend on the change kind: on this tree when quiet, about 17 s for an RTL
change and 22 s for a data-only change.

### Conservativeness proof

[`mutations.json`](../../../src/dv/builder/mutations.json) records, for a
representative set of inputs, one byte mutation and the units that detect it:
an RTL source, a cocotb testbench module, a Python test source another unit
reads as data, the catalogue, a toolchain module and data files such as the
baseline record, an SDC, the SameBoy scenario and source manifests, a
Springtrail asset and the regression subsets. Each row names the input `path`,
its `kind` (`rtl`, `python`, `catalogue`, `tool` or `data`), the `mutation`
(`append`, which adds the document's marker as a trailing line, or
`{"replace": [old, new]}`, applied once), the `detectors` (catalogue units)
and the `evidence` that they detect it. The kinds must all be present, paths
must be tracked files and detectors catalogue units; a malformed row fails by
name.

[`mutations.py`](../../../tools/n2m/mutations.py) and the catalogued
[`test_affected_mutations.py`](../../../tools/n2m/tests/test_affected_mutations.py)
prove selection is conservative for that set: for each row, the report's own
decision function ([`affected.decide`](../../../tools/n2m/affected.py)) is run
in process on the current tree with exactly that path differing from the base,
deciding only the recorded detectors, and every detector must be `selected`. A
detector left as a review candidate fails as `mutation NAME: unit U not
selected for PATH (reason)`, so dropping an input from a unit's declaration
fails by the unit's name. The in-process harness runs under `check` and costs
about 20 s at load average 4, mostly closure derivation. `tests validate` and `check` also
reject a manifest row that names an unknown unit or an untracked path; the
harness fails when the manifest is absent. `python tools/build.py tests
mutations [--name N] --tag TAG --json` runs the same selection proof as a
command; its record lists `mutations` and `misses`.

`tests mutations --confirm` re-derives the recorded detection instead of
trusting it: for each row it clones `HEAD`, borrows the installed cocotb
environment, runs every detector unmutated (a host unit through the catalogue
runner, a simulation target through `sim test` under its ordinary wall budget),
applies the mutation and runs them again. A detector that does not pass before
or does not fail after leaves the row unconfirmed and the command `FAIL`, so an
environment failure is never mistaken for a detection. The first mutated clone
of the `rtl` kind and the first of the `data` kind also run the full
`tests affected` report against `HEAD`
([`report_equals_decision`](../../../tools/n2m/mutations.py)), which must equal
the in-process decision for every unit: a changed path, fallback or required
checks the mutation did not cause, or a unit decided differently, is a named
problem and the command `FAIL`. The RTL change decides most simulations by
their changed inputs; the data change leaves them undecided and validates each
one, so both report paths run. The row record keeps the real report's
`selected`, `review_candidates` and `elapsed_seconds` under `report`. The
comparison itself is proved under `check` with a substituted report
([`test_affected_mutations.py`](../../../tools/n2m/tests/test_affected_mutations.py));
the real clones run only here, so `check` stays inside its budget. It is
opt-in: all eleven rows take about 160 s, dominated by the two
Verilator builds, the two real reports and the before/after runs of the slower
host units. `--verilator-bin` is passed through to the target runs.

`tests closure-trace [--unit NAME]` is the dynamic proof of the declared host
closures ([`closure_trace.py`](../../../tools/n2m/closure_trace.py), tested on a
fixture tree by
[`test_closure_trace.py`](../../../tools/n2m/tests/test_closure_trace.py)). Each
declared unit runs exactly as the catalogue runner runs it, with a
`sitecustomize` audit hook appended to `PYTHONPATH` that records every
repository path the interpreter and its child interpreters `open`, list,
glob or copy, and the spawned commands. A tracked file whose contents were
read (`open` or `shutil.copy*`) that is neither in
[`host_closure.closure()`](#host-unit-closure), under `tools/`, `cfg/` or
`.github/`, nor the registry or catalogue fails as `unit NAME reads outside
its declared closure: PATH`; a unit that fails or cannot run fails as `unit
NAME not traced: reason`. Directory listings and globs are recorded but are
not misses: only modified contents are judged by the report, and a file
added, removed or renamed in a listed directory already forces its full
fallback. Reads under the global-fallback prefixes are not misses for the
same reason. The full trace of every declared unit takes several minutes,
so it is opt-in and recorded when declarations change; a single unit takes
its own run time plus about five seconds of catalogue validation. Each
trace's log and record are kept under the tag. An unmodified checkout reports no
miss: every declared unit's reads fall inside its closure, so a reported miss
belongs to the change under test. The command's overall status carries no such
guarantee. A unit that overspends its [CPU budget](#what-one-host-unit-may-spend),
or one whose pinned environment a fresh worktree has not installed, fails the run
while nothing in the tree reads outside its closure, so read the per-unit misses
rather than the status. Tracing adds an audit hook to every interpreter the unit
starts, so a traced unit's CPU is its own plus that hook's.

Limits: the proof covers the recorded rows, not every input; a detector is
recorded as failing under that one mutation, not under every defect in the
file; the tracer sees the interpreter's file events, not those of native
tools such as Verilator or Git, whose inputs the registry lists; and none of
this changes which checks are required or lets a review candidate skip them.
