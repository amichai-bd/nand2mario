"""Small command dispatcher for tagged verification and build backends."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid

from .records import atomic_json, atomic_text, file_hash, git_state, workspace
from .simulation import simulate
from .simulator import Simulator, ToolError
from .doctor import doctor
from .fpga import build_fpga
from .rgbds import oracle


def parser():
    result = argparse.ArgumentParser(description="Tagged repository builds (doctor, check, sim test, fpga build).")
    commands = result.add_subparsers(dest="command", required=True)
    leaves = [commands.add_parser("doctor", help="run checked Questa smoke; no hardware access"),
              commands.add_parser("check", help="run builder tests")]
    leaves[0].add_argument("--profile", choices=("simulation", "environment"), default="simulation")
    for option in ("questa-bin", "quartus-bin", "jtag-cable", "uart-port", "uart-vid", "uart-pid", "uart-identity"):
        leaves[0].add_argument("--" + option)
    sim = commands.add_parser("sim").add_subparsers(dest="action", required=True)
    test = sim.add_parser("test", help="compile, elaborate, run, and check a named target")
    test.add_argument("target")
    test.add_argument("--seed", type=int, default=1)
    test.add_argument("--rebuild", action="store_true")
    test.add_argument("--questa-bin", help="Questa tool directory; otherwise discover on PATH")
    leaves.append(test)
    for leaf in leaves:
        leaf.add_argument("--tag")
        leaf.add_argument("--json", action="store_true", help="emit one JSON result")
        if leaf is not leaves[1]:
            leaf.add_argument("--sim", choices=("questa",), default="questa")
    fpga = commands.add_parser("fpga").add_subparsers(dest="action", required=True)
    build = fpga.add_parser("build", help="fit and check an explicit MAX 10 target; no programming")
    build.add_argument("target")
    build.add_argument("--quartus-bin", required=True, help="explicit directory containing Quartus executables")
    build.add_argument("--timeout", type=int, default=600, help="per-tool timeout in seconds, 1..3600")
    build.add_argument("--rebuild", action="store_true")
    build.add_argument("--tag")
    build.add_argument("--json", action="store_true")
    sw = commands.add_parser("sw").add_subparsers(dest="action", required=True)
    rgbds = sw.add_parser("oracle", help="check original fixtures with pinned upstream RGBDS")
    rgbds.add_argument("--offline", action="store_true", help="require verified cached downloads")
    rgbds.add_argument("--expected", help="explicit expected fixture JSON, including deliberate negative checks")
    rgbds.add_argument("--tag")
    rgbds.add_argument("--json", action="store_true")
    return result


def main(argv=None, root=None):
    args = parser().parse_args(argv)
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    report = {"status": "FAIL"}
    try:
        with workspace(root, args.tag) as build:
            report = {"tag": build.name, "created": datetime.now(timezone.utc).isoformat(),
                      "host": platform.platform(), "python": platform.python_version(),
                      "requested": vars(args), **git_state(root)}
            atomic_json(build / "status.json", {"status": "RUNNING"})
            try:
                if args.command == "check":
                    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s",
                               str(root / "tools/n2m/tests"), "-v"]
                    result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, timeout=180)
                    (build / "check.log").write_text(result.stdout, encoding="utf-8")
                    (build / "commands.log").write_text(json.dumps(command) + "\n", encoding="utf-8")
                    report.update(status="PASS" if result.returncode == 0 else "FAIL",
                                  commands=[command], artifacts=[str((build / "check.log").relative_to(root))])
                elif args.command == "doctor":
                    provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                    report.update(doctor(root, build, args, provenance))
                elif args.command == "fpga":
                    provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                    report.update(build_fpga(root, build, args, provenance))
                elif args.command == "sw":
                    provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                    report.update(oracle(root, build, args, provenance))
                else:
                    simulator = Simulator(args.sim, questa_bin=args.questa_bin)
                    if not 0 <= args.seed <= 2147483647:
                        raise ValueError("seed must be between 0 and 2147483647")
                    provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                    report.update(simulate(root, build, args, simulator, provenance))
            except Exception as error:
                report.update(status="FAIL", error=str(error))
                failure_artifacts = {}
                if isinstance(error, ToolError):
                    folder = build / "discovery" / uuid.uuid4().hex
                    folder.mkdir(parents=True)
                    log = folder / "failure.log"
                    log.write_text(error.output + "\n" + str(error) + "\n", encoding="utf-8")
                    failure_artifacts[log.relative_to(root).as_posix()] = file_hash(log)
                    report["artifacts"] = failure_artifacts
                    atomic_json(folder / "result.json", report)
                if args.command == "sim" and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.target):
                    atomic_json(build / "sim/test" / args.target / "result.json",
                                {"status": "FAIL", "error": str(error), "artifacts": failure_artifacts})
            atomic_json(build / "manifest.json", report)
            atomic_json(build / "status.json", {"status": report["status"], "cache": report.get("cache")})
            if report["status"] == "PASS":
                atomic_text(root / "workdir/latest.txt", build.name + "\n")
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"{report.get('cache', report['status'])}: {args.command} tag={report.get('tag', '-')}")
        if "error" in report:
            print(report["error"])
        if args.command == "doctor" and "checks" in report:
            print(report["scope"])
            for name, check in report["checks"].items():
                print(f"{name}: {check['status']} {check.get('error', check.get('detail', ''))}")
            print(f"Readiness: {report['readiness']}; untested: {', '.join(report['untested'])}")
    return {"PASS": 0, "FAIL": 1, "WARNING": 2}[report["status"]]
