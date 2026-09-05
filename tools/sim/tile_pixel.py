"""Run the isolated tile-pixel contract; this is not the planned n2m build tool."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
SOURCES = [
    ROOT / "src/rtl/display/dmg_tile_pixel.sv",
    ROOT / "src/dv/display/tb_dmg_tile_pixel.sv",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sim", choices=["icarus", "questa"], required=True)
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
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in [*SOURCES, Path(__file__)]},
        "commands": [], "status": "FAIL",
    }

    def run(command, directory, log_name, *, failure=False, marker=None):
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
        if re.search(r"(?:\*\* Warning:|\bwarning:)", result.stdout, re.IGNORECASE):
            raise RuntimeError(f"unexplained warning: {log}")
        diagnostics = re.findall(r"(?im)^.*\b(?:error|fatal)(?: \([^)]*\))?:.*$", result.stdout)
        if any(not (failure and marker and marker in line) for line in diagnostics):
            raise RuntimeError(f"unexpected diagnostic: {log}")
        if any(int(count) != (1 if failure else 0)
               for count in re.findall(r"\bErrors:\s*(\d+)", result.stdout)):
            raise RuntimeError(f"unexpected error count: {log}")
        if (result.returncode != 0) != failure or (marker and marker not in result.stdout):
            raise RuntimeError(f"unexpected result: {log}")
        return result.stdout

    try:
        record["commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        record["dirty"] = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True))
        names = ["iverilog", "vvp"] if args.sim == "icarus" else ["vlib", "vmap", "vlog", "vsim"]
        binaries = {name: shutil.which(name) for name in names}
        if not all(binaries.values()):
            raise RuntimeError("missing tools on PATH: " + ", ".join(n for n, p in binaries.items() if not p))
        compiler = build / "compile" / args.sim
        compiler.mkdir(parents=True)
        if args.sim == "icarus":
            run([binaries["vvp"], "-V"], compiler, "runtime-version.log")
            # -V can emit installation helper diagnostics on some distributions.
            # Capture the public compiler banner with -v during the real compile.
            run([binaries["iverilog"], "-g2012", "-Wall", "-v", "-s", "tb_dmg_tile_pixel",
                 "-o", str(compiler / "tile.vvp"), *map(str, SOURCES)], compiler, "compile.log")
        else:
            run([binaries["vlog"], "-version"], compiler, "version.log")
            run([binaries["vlib"], "work"], compiler, "library.log")
            run([binaries["vlog"], "-sv", "-work", "work", *map(str, SOURCES)], compiler, "compile.log")
        for corrupt in [False, True]:
            case = "corrupt" if corrupt else "normal"
            sim_dir = build / "sim/test/tile-pixel" / case
            sim_dir.mkdir(parents=True)
            plusargs = ["+corrupt"] if corrupt else []
            if args.sim == "icarus":
                command = [binaries["vvp"], str(compiler / "tile.vvp"), *plusargs]
            else:
                run([binaries["vmap"], "-c"], sim_dir, "ini.log")
                run([binaries["vmap"], "work", (compiler / "work").as_posix()], sim_dir, "map.log")
                # Questa's handlers require a macro, not inline -do commands.
                (sim_dir / "run.do").write_text(
                    "onbreak {if {[lindex [runStatus -full] 2] eq {$finish}} "
                    "{quit -code 0} else {quit -code 1}}\n"
                    "onerror {quit -code 1}\nrun -all\nquit -code 1\n",
                    encoding="utf-8")
                # stop preserves the finish reason; exit turns $fatal into 0.
                command = [binaries["vsim"], "-c", "-onfinish", "stop", "-wlf", "waves.wlf",
                           "work.tb_dmg_tile_pixel", *plusargs,
                           "-do", "do run.do"]
            marker = ("MISMATCH cycle=5 phase=after-edge expected=10110 actual=10111 "
                      "low=00 high=01 x=7 palette=e4 seed=none" if corrupt else
                      "PASS pixel_cases=524288 palette_cases=8192 cycles=532521 seed=none")
            run(command, sim_dir, "sim.log", failure=corrupt, marker=marker)
            (sim_dir / "result.json").write_text(json.dumps({
                "status": "EXPECTED_FAILURE" if corrupt else "PASS", "marker": marker,
                "seed": None, "wave": "waves.vcd"}, indent=2) + "\n", encoding="utf-8")
        record["status"] = "PASS"
        print(f"PASS {args.sim}: normal and deliberate corruption; {build}")
        return 0
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        record["error"] = str(error)
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    finally:
        (build / "manifest.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
