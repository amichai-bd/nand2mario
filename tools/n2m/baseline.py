"""Run the fixture regression and compare retained transactions across simulators."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from n2m.records import atomic_json, file_hash, valid_tag, workspace

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "src/dv/baseline/regression.json"
FIELDS = ["seed", "cycle", "reset", "enable", "operand", "expected", "actual"]


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    if (set(plan) != {"version", "levels", "targets"} or type(plan["version"]) is not int
            or plan["version"] != 1 or set(plan["levels"]) != {"smoke", "regression"}
            or plan["targets"] != ["baseline-good", "baseline-broken"]):
        raise ValueError("invalid baseline manifest")
    for level in plan["levels"].values():
        if (set(level) != {"seeds", "budget_seconds"} or type(level["budget_seconds"]) is not int
                or level["budget_seconds"] <= 0 or not isinstance(level["seeds"], list)
                or not level["seeds"] or any(type(seed) is not int or not 0 <= seed <= 2147483647
                                            for seed in level["seeds"])
                or len(set(level["seeds"])) != len(level["seeds"])):
            raise ValueError("invalid baseline regression level")
    return plan


def trace_rows(path, seed, broken):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError("invalid baseline trace header")
        rows = [{key: int(value) for key, value in row.items()} for row in reader]
    count = 6 if broken else 75
    if len(rows) != count:
        raise ValueError(f"trace length expected={count} actual={len(rows)}")
    for index, row in enumerate(rows, 1):
        if row["seed"] != seed or row["cycle"] != index:
            raise ValueError(f"trace ordering/seed at cycle {index}: {row}")
        if (any(not 0 <= row[key] <= 255 for key in ("operand", "expected", "actual"))
                or row["reset"] not in (0, 1) or row["enable"] not in (0, 1)):
            raise ValueError(f"invalid transaction at cycle {index}: {row}")
        if broken and index == count:
            if (row["expected"], row["actual"]) != (0, 128):
                raise ValueError(f"wrong deliberate defect: {row}")
        elif row["expected"] != row["actual"]:
            raise ValueError(f"unexpected mismatch: {row}")
    return rows


def compare_traces(expected, actual):
    if len(expected) != len(actual):
        raise ValueError(f"backend trace length expected={len(expected)} actual={len(actual)}")
    for index, (left, right) in enumerate(zip(expected, actual), 1):
        if left != right:
            raise ValueError(f"backend trace cycle={index} expected={left} actual={right}")


def evidence(root, tag, seed, broken):
    folder = root / "workdir/builds" / tag
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "PASS" or manifest["seed"] != seed:
        raise ValueError("simulation did not meet its registered expectation")
    found = {}
    for name, digest in manifest["artifacts"].items():
        path = root / name
        if not path.resolve().is_relative_to(folder.resolve()) or file_hash(path) != digest:
            raise ValueError("out-of-build or changed simulation artifact")
        found[path.name] = path
    for name in ("transactions.csv", "baseline.vcd", "sim.log"):
        if name not in found or not found[name].stat().st_size:
            raise ValueError("missing nonempty artifact: " + name)
    runtime_exit = manifest["commands"][-1]["exit_code"]
    if (runtime_exit != 0) != broken:
        raise ValueError("raw simulator exit does not match good/broken case")
    if not broken and "bins=ff" not in found["bins.txt"].read_text(encoding="utf-8"):
        raise ValueError("fixture coverage incomplete")
    return trace_rows(found["transactions.csv"], seed, broken)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("smoke", "regression"), default="smoke")
    parser.add_argument("--sim", choices=("portable", "questa", "both"), default="both")
    parser.add_argument("--questa-bin")
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    if not valid_tag(args.tag) or len(args.tag) > 24:
        parser.error("regression tag must be a valid build tag of at most 24 characters")
    if args.questa_bin and args.sim == "portable":
        parser.error("--questa-bin requires Questa")
    plan = load_plan(MANIFEST)
    level = plan["levels"][args.level]
    backends = ["auto", "questa"] if args.sim == "both" else ["auto" if args.sim == "portable" else "questa"]
    report = {"status": "RUNNING", "level": args.level, "simulators": backends,
              "manifest_sha256": file_hash(MANIFEST), "runs": [], "trace_comparison": "not applicable"}
    start = time.monotonic()
    with workspace(ROOT, args.tag) as build:
        destination = build / "regression.json"
        atomic_json(destination, report)
        try:
            for index, seed in enumerate(level["seeds"]):
                for target in plan["targets"]:
                    traces = []
                    for backend in backends:
                        if time.monotonic() - start >= level["budget_seconds"]:
                            raise ValueError("regression wall-clock budget exhausted")
                        tag = f"{args.tag}-{backend[0]}-{index}-{target.removeprefix('baseline-')}"
                        command = [sys.executable, str(ROOT / "tools/build.py"), "sim", "test", target,
                                   "--sim", backend, "--seed", str(seed), "--tag", tag, "--rebuild"]
                        if backend == "questa" and args.questa_bin:
                            command += ["--questa-bin", args.questa_bin]
                        # Builder bounds every subprocess to 60 seconds and owns its cleanup.
                        result = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", capture_output=True)
                        log = build / (tag + ".log")
                        log.write_text(result.stdout + result.stderr, encoding="utf-8")
                        report["runs"].append({"tag": tag, "seed": seed, "command": command,
                                               "exit_code": result.returncode, "log": log.relative_to(ROOT).as_posix()})
                        if result.returncode:
                            raise ValueError(f"regression target failed: {tag}; see {log.relative_to(ROOT)}")
                        traces.append(evidence(ROOT, tag, seed, target == "baseline-broken"))
                    if len(traces) == 2:
                        compare_traces(*traces)
                        report["trace_comparison"] = "PASS"
            if time.monotonic() - start > level["budget_seconds"]:
                raise ValueError("regression wall-clock budget exhausted")
            report["status"] = "PASS"
        except Exception as error:
            report.update(status="FAIL", error=str(error))
        report["elapsed_seconds"] = time.monotonic() - start
        atomic_json(destination, report)
        print(report["status"] + " baseline regression: " + str(destination))
        if "error" in report:
            print(report["error"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
