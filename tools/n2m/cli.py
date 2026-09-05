"""Small command dispatcher; future SW/FPGA backends belong beside simulation."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

from .records import atomic_json, atomic_text, git_state, workspace
from .simulation import simulate
from .simulator import Simulator


def parser():
    result = argparse.ArgumentParser(description="Tagged repository builds (doctor, check, sim test).")
    commands = result.add_subparsers(dest="command", required=True)
    leaves = [commands.add_parser("doctor", help="discover portable simulator; no hardware access"),
              commands.add_parser("check", help="run builder tests")]
    sim = commands.add_parser("sim").add_subparsers(dest="action", required=True)
    test = sim.add_parser("test", help="compile, elaborate, run, and check a named target")
    test.add_argument("target")
    test.add_argument("--seed", type=int, default=1)
    test.add_argument("--rebuild", action="store_true")
    leaves.append(test)
    for leaf in leaves:
        leaf.add_argument("--tag")
        leaf.add_argument("--json", action="store_true", help="emit one JSON result")
        if leaf is not leaves[1]:
            leaf.add_argument("--sim", choices=("auto", "icarus", "wsl-icarus"), default="auto")
            leaf.add_argument("--iverilog", help="compiler executable name or path in selected backend")
            leaf.add_argument("--vvp", help="runtime executable name or path in selected backend")
            leaf.add_argument("--wsl-distro", help="WSL distribution; omitted uses WSL default")
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
                else:
                    simulator = Simulator(args.sim, args.iverilog, args.vvp, args.wsl_distro)
                    if args.command == "doctor":
                        report.update(status="PASS", tools=simulator.info,
                                      scope="Icarus compiler/runtime discovery only; run sim test builder-smoke to prove execution",
                                      untested=["Questa license/runtime", "Quartus", "JTAG", "UART"])
                    else:
                        if not 0 <= args.seed <= 2147483647:
                            raise ValueError("seed must be between 0 and 2147483647")
                        provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                        report.update(simulate(root, build, args, simulator, provenance))
            except Exception as error:
                report.update(status="FAIL", error=str(error))
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
        if args.command == "doctor" and report["status"] == "PASS":
            print(report["scope"])
            print(json.dumps(report["tools"], indent=2))
    return 0 if report["status"] == "PASS" else 1
