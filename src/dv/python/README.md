# Python hardware tests

Python targets run through the same Questa builder as SystemVerilog targets.
The first target is the [independent joypad test](joypad/README.md).
The [Python DV skill](../../../.agents/skills/dv-python/SKILL.md) owns the method.

Create an isolated environment using a Python 3.12.14 executable:

```powershell
python3.12 -m venv workdir/builds/python-dv-env/.venv
workdir/builds/python-dv-env/.venv/Scripts/python.exe -m pip install -r src/dv/python/requirements.txt
workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-joypad --tag python-joypad --json
```

Use the installed Python 3.12.14 executable's actual name/path for the first
command. On Linux the environment's executable is `.venv/bin/python`.
No package installation or interpreter fallback occurs during a test command.
The ordinary builder environment still runs all existing SV targets.

The intentional negative target uses the same Python checker:

```powershell
workdir/builds/python-dv-env/.venv/Scripts/python.exe tools/build.py sim test python-joypad-fault --tag python-joypad-fault --json
```

This command must exit 1 and publish FAIL with
`JOYP_MISMATCH cycle=3 phase=post signal=io_rdata expected=238 actual=239`.
The raw Questa exit is retained separately and can be zero. The negative target
is not a reusable successful stage.

Inspect `sim/test/<target>/result.json` under the selected build tag for immutable
attempt paths. Each attempt retains commands, simulator logs, Python result XML,
`transactions.jsonl`, WLF and VCD waves. The JSONL observations record cycle,
phase, seed, applied public inputs and expected/actual outputs. Python reference
state is represented in this trace; HDL waves record the simulated signals.
Use `--seed` for repeatable random cases and `--rebuild` to bypass valid cache.
Licensed simulation remains serialized; no hardware is accessed.
