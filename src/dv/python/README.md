# Python hardware tests

Python targets run through the same [Verilator builder](../../../wiki/tools/n2m/SPEC.md#python-testbenches-under-verilator)
as SystemVerilog targets, on WSL Linux.
The first target is the [independent joypad test](joypad/README.md).
The [integration diagnostic](integration/README.md) independently reproduces
the retained preloaded UART execution sequence with the real composed subsystem;
it and the other Python preloaded targets are still registered
`simulator: "questa"` and report `SKIPPED questa-retired` until the Python
migration ([#612](https://github.com/amichai-bd/nand2mario/issues/612)); the
SystemVerilog `integration-smoke` and `integration-preloaded` targets already
run under the Verilator peer.
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

Inspect `sim/test/<target>/result.json` under the selected build tag for immutable
attempt paths. Each attempt retains commands, the Verilator build log, `sim.log`,
Python result XML, `transactions.jsonl` and `waves/simulation.fst`. The JSONL
observations record cycle, phase, seed, applied public inputs and expected/actual
outputs. Python reference state is represented in this trace; the FST records the
simulated signals. Use `--seed` for repeatable random cases and `--rebuild` to
bypass valid cache. No hardware is accessed.

The optional `python.waves` selection described in the
[builder contract](../../../wiki/tools/n2m/SPEC.md#testbench-types) is still
validated; under Verilator the FST holds the whole top regardless.
