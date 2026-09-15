"""Run the isolated tile-pixel contract under Verilator; this is not the planned n2m build tool."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from n2m.hdl import dependencies
from n2m.simulator import Simulator, ToolError
from n2m.verilator import commands as verilator_commands, diagnostic
SOURCES = [
    ROOT / "src/rtl/display/dmg_tile_pixel.sv",
    ROOT / "src/dv/display/tb_dmg_tile_pixel.sv",
]
TOP = "tb_dmg_tile_pixel"
# The testbench is deterministic and reports seed=none; this seed feeds only
# Verilator's randomized initial values, so the record names it.
RANDOMIZATION_SEED = 1
CASES = {
    "normal": ([], "zero", "PASS pixel_cases=524288 palette_cases=8192 cycles=532521 seed=none"),
    "corrupt": (["+corrupt"], "nonzero",
                "MISMATCH cycle=5 phase=after-edge expected=10110 actual=10111 "
                "low=00 high=01 x=7 palette=e4 seed=none"),
}
# The shared runner's command construction and transcript checks are the
# contract; only the fresh-tag, two-case manifest is this runner's own.
HELPERS = ["tools/n2m/hdl.py", "tools/n2m/simulator.py", "tools/n2m/verilator.py"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", choices=["verilator"], default="verilator")
    parser.add_argument("--verilator-bin", help="directory containing verilator; otherwise discover on PATH")
    parser.add_argument("--tag", default=datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%Sz"))
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,47}", args.tag):
        parser.error("tag must be 1-48 lowercase filesystem-safe characters")
    build = ROOT / "workdir/builds" / args.tag
    # Fresh directories prevent stale binaries and concurrent writers without caching.
    try:
        build.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("tag already exists; select a fresh tag")
    record = {
        "simulator": args.sim, "tag": args.tag, "seed": None,
        "randomization_seed": RANDOMIZATION_SEED,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {}, "tools": {},
        "commands": [], "status": "FAIL",
    }

    def run(command, directory, log_name, *, expected_exit, marker=None):
        log = directory / log_name
        try:
            result = subprocess.run(command, cwd=directory, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180)
        except subprocess.TimeoutExpired as error:
            partial = error.stdout or ""
            if isinstance(partial, bytes):
                partial = partial.decode(errors="replace")
            log.write_text(partial, encoding="utf-8")
            record["commands"].append({"argv": command, "cwd": str(directory.relative_to(build)),
                                       "timeout": True, "log": str(log.relative_to(build))})
            raise
        log.write_text(result.stdout, encoding="utf-8")
        record["commands"].append({"argv": command, "cwd": str(directory.relative_to(build)),
                                   "exit_code": result.returncode, "log": str(log.relative_to(build))})
        # Any warning fails; an error line must carry the expected failure text.
        problem = diagnostic(result.stdout, marker if expected_exit == "nonzero" else None)
        if problem:
            raise RuntimeError(f"{problem}: {log}")
        if (result.returncode != 0) != (expected_exit == "nonzero") or (marker and marker not in result.stdout):
            raise RuntimeError(f"unexpected result: {log}")
        return result.stdout

    try:
        relative = [p.relative_to(ROOT).as_posix() for p in SOURCES]
        inputs = [*[ROOT / name for name in dependencies(ROOT, relative)], Path(__file__),
                  *[ROOT / name for name in HELPERS]]
        record["inputs"] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        record["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        record["dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
        simulator = Simulator("verilator", verilator_bin=args.verilator_bin)
        record["tools"] = simulator.info
        compiler = build / "compile" / args.sim
        compiler.mkdir(parents=True)
        # One build serves both cases; each case runs from its own directory
        # so its waves and log land beside its result.
        for index, (case, (plusargs, expected_exit, marker)) in enumerate(CASES.items()):
            sim_dir = build / "sim/test/tile-pixel" / case
            (sim_dir / "waves").mkdir(parents=True)
            target = {"top": TOP, "sources": relative, "args": plusargs, "expected_exit": expected_exit}
            plan = verilator_commands(simulator, ROOT, target, RANDOMIZATION_SEED, compiler, sim_dir)
            if index == 0:
                argv, cwd, log, exit_class = plan[0]
                run(argv, cwd, log.name, expected_exit=exit_class)
            argv, cwd, log, exit_class = plan[1]
            run(argv, cwd, log.name, expected_exit=exit_class, marker=marker)
            (sim_dir / "result.json").write_text(json.dumps({
                "status": "EXPECTED_FAILURE" if expected_exit == "nonzero" else "PASS", "marker": marker,
                "seed": None, "wave": "waves/simulation.fst"}, indent=2) + "\n", encoding="utf-8")
        record["status"] = "PASS"
        print(f"PASS {args.sim}: normal and deliberate corruption; {build}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        record["error"] = str(error)
        if isinstance(error, ToolError) and error.output:
            record["error_output"] = error.output
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        (build / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
