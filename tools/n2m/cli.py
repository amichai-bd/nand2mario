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
from .host.command import run as host_command
from .fpga import build_fpga
from .fpga_program import program as program_fpga
from .rgbds import oracle
from .regress import clean, regress
from . import catalogue, interface_codec
from sw.build import assemble_target
from sw.rom_build import build_target
from sw.link_conformance import proof as link_proof
from sw.asset_conformance import proof as asset_proof
from sw.conformance import conformance
from sw.expressions import AssemblyError


def parser():
    result = argparse.ArgumentParser(description="Tagged repository builds (doctor, check, sim test, regress, clean, fpga build).")
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
    test.add_argument("--intel-sim-lib", help="supported Quartus eda/sim_lib directory for Intel memory targets")
    leaves.append(test)
    for leaf in leaves:
        leaf.add_argument("--tag")
        leaf.add_argument("--json", action="store_true", help="emit one JSON result")
        if leaf is not leaves[1]:
            leaf.add_argument("--sim", choices=("questa",), default="questa")
    subset = commands.add_parser("regress", help="run one declared target subset and report one aggregate result")
    subset.add_argument("subset", help="name in src/dv/builder/regressions.json")
    subset.add_argument("--seed", type=int, default=1)
    subset.add_argument("--rebuild", action="store_true")
    subset.add_argument("--broader", action="store_true",
                        help="declare a subset whose budget exceeds the ordinary 300-second pre-merge aggregate")
    subset.add_argument("--questa-bin")
    subset.add_argument("--intel-sim-lib")
    subset.add_argument("--sim", choices=("questa",), default="questa")
    subset.add_argument("--tag")
    subset.add_argument("--json", action="store_true")
    tests = commands.add_parser("tests", help="one catalogue of every runnable test; select by level and label").add_subparsers(dest="action", required=True)
    validate = tests.add_parser("validate", help="prove the catalogue still covers every test in the tree")
    listing = tests.add_parser("list", help="name the tests one selection would run")
    runner = tests.add_parser("run", help="run one selection and write each measured wall back")
    for leaf in (listing, runner):
        leaf.add_argument("--level", type=int, choices=catalogue.LEVELS,
                          help="run this level and every level below it")
        leaf.add_argument("--label", action="append", default=[],
                          help="require this declared label; repeat to require several")
    runner.add_argument("--seed", type=int, default=1)
    runner.add_argument("--rebuild", action="store_true")
    runner.add_argument("--budget", type=int, help="aggregate wall budget in seconds")
    runner.add_argument("--broader", action="store_true",
                        help="declare a budget above the ordinary 300-second pre-merge aggregate")
    runner.add_argument("--questa-bin")
    runner.add_argument("--intel-sim-lib")
    for leaf in (validate, listing, runner):
        leaf.add_argument("--tag")
        leaf.add_argument("--json", action="store_true")
    remove = commands.add_parser("clean", help="remove generated output under exactly one build tag")
    remove.add_argument("--tag", required=True)
    remove.add_argument("--json", action="store_true")
    fpga = commands.add_parser("fpga").add_subparsers(dest="action", required=True)
    build = fpga.add_parser("build", help="fit and check an explicit MAX 10 target; no programming")
    build.add_argument("target")
    build.add_argument("--quartus-bin", required=True, help="explicit directory containing Quartus executables")
    build.add_argument("--timeout", type=int, default=600, help="per-tool timeout in seconds, 1..3600")
    build.add_argument("--rebuild", action="store_true")
    build.add_argument("--tag")
    build.add_argument("--json", action="store_true")
    program_parser = fpga.add_parser("program", help="write a checked .sof to the connected board; USB-Blaster/10M50DA identity checked first")
    program_parser.add_argument("--sof", required=True, help="path to a design.sof built by 'fpga build'")
    program_parser.add_argument("--quartus-bin", required=True, help="explicit directory containing Quartus executables")
    program_parser.add_argument("--jtag-cable", help="required JTAG chain index if more than one is ever present")
    program_parser.add_argument("--timeout", type=int, default=60)
    program_parser.add_argument("--tag")
    program_parser.add_argument("--json", action="store_true")
    sw = commands.add_parser("sw").add_subparsers(dest="action", required=True)
    rgbds = sw.add_parser("oracle", help="check original fixtures with pinned upstream RGBDS")
    rgbds.add_argument("--offline", action="store_true", help="require verified cached downloads")
    rgbds.add_argument("--expected", help="explicit expected fixture JSON, including deliberate negative checks")
    rgbds.add_argument("--tag")
    rgbds.add_argument("--json", action="store_true")
    assembly = sw.add_parser("assemble", help="emit validated relocatable objects for an explicit target")
    assembly.add_argument("target")
    assembly.add_argument("--rebuild", action="store_true")
    assembly.add_argument("--tag")
    assembly.add_argument("--json", action="store_true")
    cartridge = sw.add_parser("build", help="link and package an explicit direct-profile target")
    cartridge.add_argument("target")
    cartridge.add_argument("--rebuild", action="store_true")
    cartridge.add_argument("--tag")
    cartridge.add_argument("--json", action="store_true")
    proof = sw.add_parser("conformance", help="compare complete original instruction matrix against RGBDS")
    proof.add_argument("--offline", action="store_true")
    proof.add_argument("--mutate", action="store_true", help="deliberately corrupt one encoded byte; must fail")
    proof.add_argument("--tag")
    proof.add_argument("--json", action="store_true")
    linked_proof = sw.add_parser("link-conformance", help="compare linked bytes/symbols and independent packaging")
    linked_proof.add_argument("--offline", action="store_true")
    linked_proof.add_argument("--mutate", choices=("relocation", "checksum"))
    linked_proof.add_argument("--tag")
    linked_proof.add_argument("--json", action="store_true")
    asset_check = sw.add_parser("asset-conformance", help="decode original assets and verify ASSET build integration")
    asset_check.add_argument("--mutate", choices=("planes", "bitorder", "columns", "rows", "tiles"))
    asset_check.add_argument("--tag")
    asset_check.add_argument("--json", action="store_true")
    host = commands.add_parser('host', help='explicit UART load/control; follows verified hardware workflow').add_subparsers(dest='action', required=True)
    for action in ('status', 'io', 'load', 'reset', 'run', 'halt', 'step', 'run-dots', 'input', 'write', 'snapshot', 'peek', 'crc-proof', 'keyboard'):
        description = None
        if action == 'keyboard':
            description = ('Focused Windows classic console only (conhost.exe cmd.exe); Windows Terminal/WSL are unsupported. '
                           'Release keys before starting. Arrows: directions; Z: A; X: B; right Shift: Select; Enter: Start. '
                           'Escape/Ctrl+C or focus loss releases when certain and exits. No load/run/reset; requires UART/neutral input. '
                           '--json and --endpoint-restarted are not accepted.')
        leaf = host.add_parser(action, description=description)
        for option in ('uart-port', 'uart-vid', 'uart-pid', 'uart-identity'):
            leaf.add_argument('--' + option)
        leaf.add_argument('--endpoint-restarted', action='store_true',
                          help='declare a separately completed endpoint global reset after uncertain completion; sends no reset')
        leaf.add_argument('--tag')
        leaf.add_argument('--json', action='store_true')
        if action in ('crc-proof', 'keyboard'):
            leaf.add_argument('--expected-build-id', required=True, help='reviewed 32-hex wire build identity')
        if action == 'load':
            source = leaf.add_mutually_exclusive_group(required=True)
            source.add_argument('--package', help='immutable sw/build/<target>/runs/<attempt>/result.json')
            source.add_argument('--external', help='pinned external image name from tools/n2m/dependencies.json')
        if action in ('step', 'run-dots'):
            leaf.add_argument('--dots', type=int, required=True)
        if action == 'input':
            leaf.add_argument('--mask', type=lambda value: int(value, 0), required=True)
        if action == 'peek':
            leaf.add_argument('--store', required=True, choices=sorted(interface_codec.PEEK_STORES),
                              help='one non-ROM store to read; the core must be paused')
        if action == 'io':
            leaf.add_argument('--samples', type=int, default=200,
                              help='live LCD samples to take; reads never pause the endpoint')
        if action == 'write':
            leaf.add_argument('--address', type=lambda value: int(value, 0), required=True)
            leaf.add_argument('--value', type=lambda value: int(value, 0), required=True)
    return result


def tagged(root, args, header, publish):
    """Run one command inside its exclusive tagged workspace."""
    with workspace(root, args.tag) as build:
        report = header(build.name)
        atomic_json(build / "status.json", {"status": "RUNNING"})
        try:
            if args.command == "check":
                command = [sys.executable, "-B", "-m", "unittest", "discover", "-s",
                           str(root / "tools/n2m/tests"), "-v"]
                result = subprocess.run(command, cwd=root, text=True, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=180)
                (build / "check.log").write_text(result.stdout, encoding="utf-8")
                (build / "commands.log").write_text(json.dumps(command) + "\n", encoding="utf-8")
                # A test in the tree but not in the catalogue fails this check.
                model, _ = catalogue.load(root)
                problems = catalogue.coverage(root, model)
                report.update(status="PASS" if result.returncode == 0 and not problems else "FAIL",
                              commands=[command], catalogue_units=len(model["units"]),
                              catalogue_problems=problems,
                              artifacts=[str((build / "check.log").relative_to(root))])
                if problems:
                    report["error"] = problems[0]
            elif args.command == "doctor":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                report.update(doctor(root, build, args, provenance))
            elif args.command == "fpga":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                if args.action == "build":
                    report.update(build_fpga(root, build, args, provenance))
                else:
                    folder = build / "fpga-program" / uuid.uuid4().hex[:12]
                    folder.mkdir(parents=True)
                    result = program_fpga(root, folder, Path(args.sof), quartus_bin=args.quartus_bin,
                                          cable=args.jtag_cable, timeout=args.timeout)
                    report.update(status="PASS", provenance=provenance, **result,
                                 artifacts={p.relative_to(root).as_posix(): file_hash(p) for p in folder.rglob("*") if p.is_file()})
            elif args.command == 'host':
                provenance = {k: report[k] for k in ('commit', 'dirty_tree_fingerprint', 'host', 'python') if k in report}
                report.update(host_command(root, build, args, provenance))
            elif args.command == "sw":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                report.update(oracle(root, build, args, provenance) if args.action == "oracle"
                              else conformance(root, build, args, provenance) if args.action == "conformance"
                              else asset_proof(root, build, args, provenance) if args.action == "asset-conformance"
                              else link_proof(root, build, args, provenance) if args.action == "link-conformance"
                              else build_target(root, build, args, provenance) if args.action == "build"
                              else assemble_target(root, build, args, provenance))
            else:
                simulator = Simulator(args.sim, questa_bin=args.questa_bin)
                if not 0 <= args.seed <= 2147483647:
                    raise ValueError("seed must be between 0 and 2147483647")
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                report.update(simulate(root, build, args, simulator, provenance))
        except Exception as error:
            report.update(status="FAIL", error=str(error))
            if isinstance(error, AssemblyError):
                report['diagnostics'] = [error.diagnostic]
                diagnostic = build / 'sw' / ('diagnostics-' + uuid.uuid4().hex[:12] + '.json')
                atomic_json(diagnostic, report['diagnostics'])
                report['artifacts'] = {diagnostic.relative_to(root).as_posix(): file_hash(diagnostic)}
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
        publish(build, report)
    return report


def main(argv=None, root=None):
    args = parser().parse_args(argv)
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    report = {"status": "FAIL"}

    def header(tag):
        return {"tag": tag, "created": datetime.now(timezone.utc).isoformat(),
                "host": platform.platform(), "python": platform.python_version(),
                "requested": vars(args), **git_state(root)}

    def publish(build, result):
        atomic_json(build / "manifest.json", result)
        atomic_json(build / "status.json", {"status": result["status"], "cache": result.get("cache")})
        if result["status"] == "PASS":
            atomic_text(root / "workdir/latest.txt", build.name + "\n")

    try:
        if args.command == "regress":
            report = regress(root, args, header, publish)
        elif args.command == "tests":
            report = catalogue.command(root, args, header, publish)
        elif args.command == "clean":
            # No workspace: the tag directory itself is what clean removes.
            report = header(args.tag)
            report.update(clean(root, args.tag))
        else:
            report = tagged(root, args, header, publish)
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"{report.get('cache', report['status'])}: {args.command} tag={report.get('tag', '-')}")
        if "error" in report:
            print(report["error"])
        if args.command == "tests" and "units" in report and isinstance(report["units"], dict):
            for name, outcome in report["units"].items():
                if outcome["status"] != "PASS":
                    print(f"{name}: {outcome['status']} {outcome.get('reason', outcome.get('error', ''))}".rstrip())
            print(f"{report['selector']}: {report['selected']} selected, "
                  f"{len(report.get('failed', []))} failed, {len(report.get('skipped', []))} skipped")
            print(f"Elapsed: {report.get('elapsed_seconds', 0):.1f}s of {report.get('budget_seconds')}s budget")
        if args.command == "tests" and "tests" in report:
            for name in report["tests"]:
                print(name)
            print(f"{report['selector']}: {report['selected']} selected, "
                  f"{report['measured']} measured, {report['measured_seconds']:.1f}s last measured total")
        if args.command == "tests" and "problems" in report:
            for problem in report["problems"]:
                print(problem)
            print(f"{report['units']} units, {len(report['not_runnable'])} not runnable")
        if args.command == "regress" and "targets" in report:
            for name, outcome in report["targets"].items():
                print(f"{name}: {outcome['status']} {outcome.get('cache', '')} {outcome.get('error', '')}".rstrip())
            print(f"Elapsed: {report.get('elapsed_seconds', 0):.1f}s of {report.get('budget_seconds')}s budget")
        if args.command == "doctor" and "checks" in report:
            print(report["scope"])
            for name, check in report["checks"].items():
                print(f"{name}: {check['status']} {check.get('error', check.get('detail', ''))}")
            print(f"Readiness: {report['readiness']}; untested: {', '.join(report['untested'])}")
    return {"PASS": 0, "FAIL": 1, "WARNING": 2}[report["status"]]
