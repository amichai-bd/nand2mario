# Python hardware tests

Python targets run through the same [builder](../../../wiki/tools/n2m/SPEC.md#testbench-types)
as SystemVerilog targets. Each target declares Verilator, Questa, or both; a
backend follows its own tools, not an operating system.
The first target is the [independent joypad test](joypad/README.md).
The [integration diagnostic](integration/README.md) independently reproduces
the retained preloaded UART execution sequence with the real composed subsystem.
Every Python target declares `simulators: ["verilator"]` and runs under
Verilator 5.052 on Linux with cocotb 2.1.0, including the three
[Mooneye targets](../mooneye/README.md) under the owner's bounded wall
allowance: 127 Python rows, all `["verilator"]`, no Questa-only Python row.
The 600-frame `python-v05-continuous` row is retired in the catalogue; the
[continuity schedule](v05/README.md#continuity-schedule) covers its input
transitions under a declared 900-second wall allowance. Questa remains available
to the targets that declare it, wherever its executables and a
[runtime license](../../../wiki/tools/n2m/SPEC.md#questa-runtime-license) are
present; no Python target claims a Questa capability this host cannot prove.
Composed wrappers build with only their top module public and `-O2`; the
builder generates that access configuration, and the wrappers keep their own
clocks under `--timing`. A background monitor cancelled at the end of a test
must be allowed to finish before the test returns: cocotb 2.1 cancels a task
waiting in `First()` through its child waiters, and the regression's own
end-of-test cancel fails a task it still finds running.
The [Python DV skill](../../../.agents/skills/dv-python/SKILL.md) owns the method.

Create an isolated environment using a Python 3.12.14 executable:

```bash
python3.12 -m venv workdir/builds/python-dv-env/.venv
workdir/builds/python-dv-env/.venv/bin/python -m pip install -r src/dv/python/requirements.txt
workdir/builds/python-dv-env/.venv/bin/python tools/build.py sim test python-joypad --tag python-joypad --json
```

Use the installed Python 3.12.14 executable's actual name/path for the first
command. No package installation or interpreter fallback occurs during a test
command. The ordinary builder interpreter (`python3`) still runs all SV targets.

The intentional negative target uses the same Python checker against a
wrapper with one broken read line:

```bash
workdir/builds/python-dv-env/.venv/bin/python tools/build.py sim test python-joypad-fault --tag python-joypad-fault --json
```

It is registered `expected_exit: "nonzero"` with the signature
`JOYP_MISMATCH cycle=3 phase=post signal=io_rdata expected=238 actual=239`, so
the command exits 0 and publishes PASS only when the named Python test fails
with that message; `results.xml` retains the failure and `python_results`
reports `FAIL` for the test itself. The simulator process exits zero in both
targets. A passing checker, a different mismatch or missing results fails the
target, as the [builder contract](../../../wiki/tools/n2m/SPEC.md#python-testbenches-under-verilator)
defines, and `tests run --label joypad` counts it like any other `fault` unit.

Inspect `sim/test/<target>/<backend>/result.json` under the selected build tag
for the authoritative result and immutable attempt paths. The generic
`sim/test/<target>/result.json` is a last-completed-run compatibility mirror.
Each attempt retains commands, build logs, `sim.log`, Python result XML,
`transactions.jsonl` and backend waves (`simulation.fst` for Verilator;
`simulation.vcd` and `simulation.wlf` for Questa). The JSONL
observations record cycle, phase, seed, applied public inputs and expected/actual
outputs. Python reference state is represented in this trace; the FST records the
simulated signals. Use `--seed` for repeatable random cases and `--rebuild` to
bypass valid cache. No hardware is accessed.

The optional `python.waves` selection described in the
[builder contract](../../../wiki/tools/n2m/SPEC.md#testbench-types) is still
validated; under Verilator the FST holds the whole top regardless.
