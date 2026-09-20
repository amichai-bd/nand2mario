"""Small command dispatcher for tagged verification and build backends."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import shlex
import subprocess
import sys
import time
import uuid

from .records import (atomic_json, atomic_text, cpu_seconds, file_hash, git_state,
                      tag_directory, workspace)
from .simulation import SIMULATORS, load_target, prepare, publish_mirror, simulate, stage_paths
from .simulator import Simulator, ToolError
from . import fpga_jtag
from .doctor import doctor
from .host.command import run as host_command
from .fpga import build_fpga
from . import fpga_hold
from .fpga_program import FLASH_TIMEOUT, device_state_after, program as program_fpga, program_flash
from .flash_library import library_stage
from .lint import lint_questa
from .progress import Progress, powershell_command
from .rgbds import oracle
from .regress import clean, regress
from . import catalogue, host_suite, interface_codec, vendor_sources, verilator_install
from sw.build import assemble_target
from sw.rom_build import build_target
from sw.link_conformance import proof as link_proof
from sw.asset_conformance import proof as asset_proof
from sw.conformance import conformance
from sw.expressions import AssemblyError


def parser():
    result = argparse.ArgumentParser(description="Tagged repository builds (doctor, check, sim test, regress, clean, fpga build).")
    commands = result.add_subparsers(dest="command", required=True)
    leaves = [commands.add_parser("doctor", help="run the checked host-native simulator smoke; no hardware access"),
              commands.add_parser("check", help="run builder tests")]
    leaves[0].add_argument("--profile", choices=("simulation", "environment"), default="simulation")
    leaves[0].add_argument("--verilator-bin", help="directory containing verilator; otherwise discover on PATH")
    leaves[0].add_argument("--questa-bin", help="directory containing native Questa tools; otherwise discover on PATH")
    leaves[0].add_argument("--sim", choices=SIMULATORS)
    for option in ("quartus-bin", "jtag-cable", "openfpgaloader-bin", "probe-firmware",
                   "uart-port", "uart-vid", "uart-pid", "uart-identity"):
        leaves[0].add_argument("--" + option)
    leaves[0].add_argument("--programmer", choices=fpga_jtag.PROGRAMMER_CHOICES, default="auto",
                           help="JTAG backend; auto reads the chain through the first available one that reports a supported board")
    sim = commands.add_parser("sim").add_subparsers(dest="action", required=True)
    test = sim.add_parser("test", help="compile, elaborate, run, and check a named target")
    test.add_argument("target")
    test.add_argument("--seed", type=int, default=1)
    test.add_argument("--rebuild", action="store_true")
    test.add_argument("--verilator-bin", help="directory containing verilator; otherwise discover on PATH")
    test.add_argument("--questa-bin", help="directory containing native Questa tools; otherwise discover on PATH")
    test.add_argument("--intel-sim-lib", help="supported Quartus eda/sim_lib directory for Questa Intel-model targets")
    test.add_argument("--sim", choices=SIMULATORS)
    test.add_argument("--prepared", help="attempt id a prior `sim prepare` of this target produced on this tag; refused if any input changed")
    prepare = sim.add_parser("prepare", help="build a target's fixtures and preload files into an immutable attempt without taking the tag lock or launching a simulator")
    prepare.add_argument("target")
    prepare.add_argument("--seed", type=int, default=1)
    prepare.add_argument("--verilator-bin", help="directory containing verilator; otherwise discover on PATH")
    prepare.add_argument("--questa-bin", help="directory containing native Questa tools; otherwise discover on PATH")
    prepare.add_argument("--intel-sim-lib", help="supported Quartus eda/sim_lib directory for Questa Intel-model targets")
    prepare.add_argument("--sim", choices=SIMULATORS)
    prepare.add_argument("--tag")
    prepare.add_argument("--json", action="store_true", help="emit one JSON result")
    preflight = sim.add_parser("preflight", help="prepare and check Python fixtures without discovering or launching a simulator")
    preflight.add_argument("target")
    preflight.add_argument("--tag")
    preflight.add_argument("--json", action="store_true")
    leaves.append(test)
    for leaf in leaves:
        leaf.add_argument("--tag")
        leaf.add_argument("--json", action="store_true", help="emit one JSON result")
    subset = commands.add_parser("regress", help="run one declared target subset and report one aggregate result")
    subset.add_argument("subset", help="name in src/dv/builder/regressions.json")
    subset.add_argument("--seed", type=int, default=1)
    subset.add_argument("--rebuild", action="store_true")
    subset.add_argument("--broader", action="store_true",
                        help="declare a subset whose budget exceeds the ordinary 300-second pre-merge aggregate")
    subset.add_argument("--verilator-bin")
    subset.add_argument("--questa-bin")
    subset.add_argument("--intel-sim-lib")
    subset.add_argument("--sim", choices=SIMULATORS)
    subset.add_argument("--tag")
    subset.add_argument("--json", action="store_true")
    tests = commands.add_parser("tests", help="one catalogue of every runnable test; select by level and label").add_subparsers(dest="action", required=True)
    validate = tests.add_parser("validate", help="prove the catalogue still covers every test in the tree")
    listing = tests.add_parser("list", help="name the tests one selection would run")
    affected = tests.add_parser("affected", help="explain conservative impact; never replace required checks")
    affected.add_argument("--base", required=True)
    mutations = tests.add_parser("mutations", help="prove recorded mutations select their detecting units; opt-in, never a required check")
    mutations.add_argument("--confirm", action="store_true",
                           help="re-run each detector before and after its mutation in a shared clone")
    mutations.add_argument("--name", action="append", default=[], help="only this recorded mutation; repeatable")
    mutations.add_argument("--verilator-bin")
    trace = tests.add_parser("closure-trace", help="run declared host units under a file tracer and fail any read outside the declared closure")
    trace.add_argument("--unit", action="append", default=[], help="only this declared host unit; repeatable")
    runner = tests.add_parser("run", help="run one selection under one aggregate budget; writes no tracked file")
    recorder = tests.add_parser("record", help="write one retained run's measured walls into the catalogue, with the conditions that produced them")
    recorder.add_argument("--tag", required=True,
                          help="the retained run to record: its tests/summary.json or manifest.json")
    recorder.add_argument("--json", action="store_true")
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
    runner.add_argument("--verilator-bin")
    runner.add_argument("--questa-bin")
    runner.add_argument("--intel-sim-lib")
    runner.add_argument("--sim", choices=SIMULATORS)
    for leaf in (validate, listing, runner, affected, mutations, trace):
        leaf.add_argument("--tag")
        leaf.add_argument("--json", action="store_true")
    tools = commands.add_parser("tools", help="install the host tools this repository pins for itself").add_subparsers(dest="action", required=True)
    pinned_verilator = tools.add_parser("verilator", help="build and install the pinned Verilator into the shared host tool cache (N2M_TOOL_CACHE, else the per-user default); discovery then needs no PATH edit and no worktree rebuilds it")
    pinned_verilator.add_argument("--jobs", type=int, help="parallel build jobs; defaults to the host CPU count")
    pinned_verilator.add_argument("--timeout", type=int, default=verilator_install.STEP_TIMEOUT,
                                  help="per-step timeout in seconds")
    pinned_verilator.add_argument("--offline", action="store_true",
                                  help="build only from an already fetched pinned source; never download")
    pinned_verilator.add_argument("--tag")
    pinned_verilator.add_argument("--json", action="store_true")
    vendor = commands.add_parser("vendor", help="record reviewed installed vendor sources as accepted for an installation").add_subparsers(dest="action", required=True)
    accepted = vendor.add_parser("accept", help="accept the installed digest of named vendor sources; the only way an accepted digest changes")
    accepted.add_argument("--quartus-bin", required=True, help="explicit directory containing Quartus executables")
    accepted.add_argument("--source", action="append", required=True,
                          help="installation-relative path of a vendor source to accept; repeat for several")
    accepted.add_argument("--reason", required=True,
                          help="why the changed vendor bytes are accepted; recorded in the ledger with the digests")
    accepted.add_argument("--json", action="store_true")
    remove = commands.add_parser("clean", help="remove generated output under exactly one build tag")
    remove.add_argument("--tag", required=True)
    remove.add_argument("--json", action="store_true")
    fpga = commands.add_parser("fpga").add_subparsers(dest="action", required=True)
    build = fpga.add_parser("build", help="fit and check an explicit registered board target; no programming")
    build.add_argument("target")
    build.add_argument("--quartus-bin", required=True, help="explicit directory containing Quartus executables")
    build.add_argument("--timeout", type=int, default=600, help="per-tool timeout in seconds, 1..3600")
    build.add_argument("--rebuild", action="store_true")
    build.add_argument("--build-id", help="comparison only: pin the 128-bit identity macro (32 hex digits) instead of the fingerprint prefix; the result cannot be programmed")
    build.add_argument("--tag")
    build.add_argument("--json", action="store_true")
    program_parser = fpga.add_parser("program", help="write a checked .sof (volatile) or .pof (internal flash) to the connected board; the chain must report the image's own board device first")
    image = program_parser.add_mutually_exclusive_group(required=True)
    image.add_argument("--sof", help="path to a design.sof built by 'fpga build'")
    image.add_argument("--pof", help="path to a design.pof built by 'fpga build' of a flash image; program, verify and blank-check the internal flash")
    program_parser.add_argument("--dry-run", action="store_true",
                                help="with --pof: run the record checks and write the exact quartus_pgm command; no JTAG access")
    program_parser.add_argument("--quartus-bin", required=True, help="explicit directory containing Quartus executables")
    program_parser.add_argument("--jtag-cable", help="one cable: a jtagconfig chain index, or an openFPGALoader cable name (usb-blaster, usb-blasterII) which also selects that backend")
    program_parser.add_argument("--programmer", choices=fpga_jtag.PROGRAMMER_CHOICES, default="auto",
                                help="JTAG backend; auto programs through the first available one whose chain reports the image's board")
    program_parser.add_argument("--openfpgaloader-bin", help="explicit directory containing openFPGALoader; otherwise discover on PATH")
    program_parser.add_argument("--probe-firmware", help="FX2 firmware image for a USB-Blaster II; defaults to blaster_6810.hex beside the Quartus Linux executables")
    program_parser.add_argument("--timeout", type=int, help="programmer timeout in seconds; 60 for --sof, 600 for --pof")
    program_parser.add_argument("--tag")
    program_parser.add_argument("--json", action="store_true")
    lint = commands.add_parser("lint", help="front-end gates without a simulation run").add_subparsers(dest="action", required=True)
    gate = lint.add_parser("questa", help="vlog every src/rtl source and vopt every FPGA top under native Questa; no vsim, no runtime license")
    gate.add_argument("--questa-bin", help="directory containing vlib, vmap, vlog and vopt; otherwise discover on PATH")
    gate.add_argument("--inject-fault", action="store_true",
                      help="also compile src/dv/builder/questa_lint_fault.sv; the gate must FAIL naming it")
    gate.add_argument("--tag")
    gate.add_argument("--json", action="store_true")
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
    flash_library = sw.add_parser("library", help="assemble the flash library image (library.hex, library.dat) from src/fpga/de10_lite/library.json; no Quartus")
    flash_library.add_argument("--rebuild", action="store_true")
    flash_library.add_argument("--offline", action="store_true", help="never fetch: refuse by name an external image the shared cache (N2M_EXTERNAL_ROM_CACHE, else the per-user default) does not hold")
    flash_library.add_argument("--tag")
    flash_library.add_argument("--json", action="store_true")
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
    for action in ('status', 'io', 'load', 'reset', 'run', 'halt', 'step', 'run-dots', 'input', 'write', 'snapshot', 'peek',
                   'sdram-write', 'sdram-read', 'sdram-test', 'crc-proof', 'keyboard'):
        description = None
        if action == 'keyboard':
            description = ('Focused Windows classic console only (conhost.exe cmd.exe); Windows Terminal/WSL are unsupported. '
                           'Release keys before starting. Arrows: directions; Z: A; X: B; right Shift: Select; Enter: Start. '
                           'Escape/Ctrl+C or focus loss releases when certain and exits. No load/run/reset; requires UART/neutral input. '
                           '--json and --endpoint-restarted are not accepted.')
        leaf = host.add_parser(action, description=description)
        host_session_options(leaf)
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
        if action in ('sdram-write', 'sdram-read'):
            leaf.add_argument('--address', type=lambda value: int(value, 0), required=True,
                              help='line-aligned SDRAM device byte address')
        if action == 'sdram-write':
            leaf.add_argument('--data', required=True, help='1..15 whole 16-byte lines as hex digits, byte 0 first')
        if action == 'sdram-read':
            leaf.add_argument('--lines', type=int, default=1, help='1..15 consecutive lines')
        if action == 'sdram-test':
            leaf.add_argument('--start', type=lambda value: int(value, 0), default=0, help='line-aligned start address')
            leaf.add_argument('--length', type=lambda value: int(value, 0), default=0x8000,
                              help='bytes to test, a line multiple; default one 32 KiB slot')
            leaf.add_argument('--full', action='store_true', help='test the whole 64 MiB device instead of --start/--length')
            leaf.add_argument('--boundary', action='store_true',
                              help="the storage contract's boundary lines (slot, catalogue, row and bank edges) instead of a range")
            leaf.add_argument('--seed', type=int, default=1, help='pattern seed')
    library = host.add_parser('library', help='the sixteen-slot SDRAM game library and its catalogue').add_subparsers(dest='verb', required=True)
    library_load = library.add_parser('load', description='Write our own built images to SDRAM slots 0..N-1, the menu image at index 16 and the '
                                      'catalogue, then read everything back and verify each slot by CRC32.')
    library_load.add_argument('package', nargs='+',
                              help='immutable sw/build/<target>/runs/<attempt>/result.json per slot, slot 0 first, at most 16')
    library_load.add_argument('--menu', help='immutable sw/build result.json for the menu image at index 16')
    host_session_options(library_load)
    host_session_options(library.add_parser('status', description='Read the catalogue as stored and print the library table.'))
    library_return = library.add_parser('return', description='Return to the menu from the host: the whitelisted LIBRARY_CONTROL '
                                        'write that behaves exactly like the KEY1 hold; accepted while PAUSED or RUNNING, '
                                        'refused by name while LOADING. Reports LIBRARY_STATUS and the endpoint state after the write.')
    library_return.add_argument('--wait', action='store_true',
                                help='read LIBRARY_STATUS until copy_busy and key1_pending clear, within a bounded number of reads')
    host_session_options(library_return)
    return result


def host_session_options(leaf):
    for option in ('uart-port', 'uart-vid', 'uart-pid', 'uart-identity'):
        leaf.add_argument('--' + option)
    leaf.add_argument('--endpoint-restarted', action='store_true',
                      help='declare a separately completed endpoint global reset after uncertain completion; sends no reset')
    leaf.add_argument('--tag')
    leaf.add_argument('--json', action='store_true')


def measured_notices(root, target, report):
    """Say what this run cost and against what the catalogue records for it.

    An unasked-for measurement belongs in the run's own retained record, beside
    the run that produced it, and in the author's eyes. It does not belong in a
    tracked file nobody asked to change."""
    walls = catalogue.measured_walls(report)
    if target not in walls:
        return []
    wall, cpu = walls[target]["wall"], walls[target].get("cpu")
    ratio = catalogue.wall_cpu_ratio(wall, cpu)
    try:
        recorded = (catalogue.load(root)[0]["units"].get(target) or {}).get("duration_seconds")
    except (OSError, ValueError) as error:
        return [f"Measured {target} {wall:.2f}s; {catalogue.CATALOGUE} could not be read: {error}"]
    against = (f"{recorded:.2f}s recorded" if isinstance(recorded, (int, float))
               else "no recorded wall")
    load = "wall/CPU unknown on this host" if ratio is None else f"wall/CPU {ratio:.2f}"
    lines = [f"Measured {target} {wall:.2f}s against {against} ({load}); no tracked file changed."]
    if catalogue.drifted(catalogue.measured_duration(wall), recorded):
        lines.append("Record this sitting if the host was quiet: "
                     f"python tools/build.py tests record --tag {report.get('tag')}")
    return lines


def recorded_lines(report):
    """Say what each recorded wall replaced, so no multiple lands silently.

    A recording that writes 195 seconds over 26 without a word is the same
    silence this command exists to end, so the gap is named at the moment of
    writing and marked when it is more than the reporting threshold."""
    lines = []
    for name, entry in (report.get("recorded") or {}).items():
        was, ratio = entry.get("was"), entry.get("wall_cpu")
        if isinstance(was, (int, float)) and was > 0:
            # Named in whichever direction is the multiple, so a wall that
            # shrank by 268 times does not print as 0.0x.
            times = (f"{entry['seconds'] / was:.1f}x higher" if entry["seconds"] >= was
                     else f"{was / entry['seconds']:.1f}x lower")
            gap = f"against {was:.2f}s recorded, {times}"
        else:
            gap = "against no recorded wall"
        load = "" if ratio is None else f", wall/CPU {ratio:.2f}"
        build = "" if entry.get("build") is None else f", {entry['build']:.2f}s of it compile"
        mark = " DRIFT" if name in (report.get("drift") or []) else ""
        lines.append(f"Recorded{mark} {name} {entry['seconds']:.2f}s {gap}{load}{build}")
    return lines


def drift_lines(report):
    """Name every unit whose measured wall no longer matches the recorded one."""
    lines = []
    for name in report.get("drift", []):
        wall = report["measured_walls"][name]
        recorded = report["units"][name].get("recorded_seconds")
        against = (f"{recorded:.2f}s recorded" if isinstance(recorded, (int, float))
                   else "no recorded wall")
        ratio = catalogue.wall_cpu_ratio(wall["wall"], wall.get("cpu"))
        load = "" if ratio is None else f", wall/CPU {ratio:.2f}"
        lines.append(f"{name}: measured {wall['wall']:.2f}s against {against}{load}")
    if lines:
        lines.append(f"{catalogue.CATALOGUE} is unchanged. Record this sitting if the host was "
                     f"quiet: python tools/build.py tests record --tag {report.get('tag')}")
    return lines


def tagged(root, args, header, publish, progress=None):
    """Run one command inside its exclusive tagged workspace."""
    progress = progress or Progress(False)
    reclaimed = []
    operation_folder = None
    with workspace(root, args.tag, reclaimed) as build:
        locked_at = time.monotonic()
        cpu_at = cpu_seconds()
        report = header(build.name)
        if reclaimed:
            report["stale_lock_reclaimed"] = reclaimed[0].relative_to(root).as_posix()
        atomic_json(build / "status.json", {"status": "RUNNING"})
        try:
            if args.command == "check":
                suite, problems = host_suite.run(root, build / "check.log")
                (build / "commands.log").write_text("".join(json.dumps(c) + "\n" for c in suite["commands"]),
                                                    encoding="utf-8")
                # A test in the tree but not in the catalogue fails this check.
                model, _ = catalogue.load(root)
                coverage = catalogue.coverage(root, model) + catalogue.unmeasured(model)
                problems += coverage
                report.update(status="PASS" if not problems else "FAIL", **suite,
                              catalogue_units=len(model["units"]), catalogue_problems=coverage,
                              artifacts=[str((build / "check.log").relative_to(root))])
                if problems:
                    report["error"] = problems[0]
            elif args.command == "doctor":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                report.update(doctor(root, build, args, provenance))
            elif args.command == "fpga":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                if args.action == "build":
                    progress.line(f"FPGA build: target {args.target}")
                    report.update(build_fpga(root, build, args, provenance, progress=progress))
                else:
                    folder = build / "fpga-program" / uuid.uuid4().hex[:12]
                    folder.mkdir(parents=True)
                    operation_folder = folder
                    if args.pof:
                        # The flash image is not a backend choice: only quartus_pgm
                        # has the documented operation letters and timing for it.
                        if args.programmer != "auto" and args.programmer != fpga_jtag.QUARTUS:
                            raise ValueError(f"--programmer {args.programmer} does not apply to --pof; "
                                             "the flash image is written by quartus_pgm")
                        progress.line(f"FPGA flash program{' (dry run)' if args.dry_run else ''}: {args.pof}")
                        result = program_flash(root, folder, Path(args.pof), quartus_bin=args.quartus_bin,
                                               cable=args.jtag_cable, timeout=args.timeout or FLASH_TIMEOUT,
                                               dry_run=args.dry_run, progress=progress)
                    else:
                        if args.dry_run:
                            raise ValueError("--dry-run applies only to --pof")
                        progress.line(f"FPGA program: {args.sof}")
                        result = program_fpga(root, folder, Path(args.sof), quartus_bin=args.quartus_bin,
                                              cable=args.jtag_cable, timeout=args.timeout or 60, progress=progress,
                                              programmer=args.programmer,
                                              openfpgaloader_bin=args.openfpgaloader_bin,
                                              probe_firmware=args.probe_firmware)
                    # The operation directory keeps its own record beside its logs,
                    # so the retained evidence outlives later commands on the tag.
                    atomic_json(folder / "result.json", {"status": "PASS", "provenance": provenance, **result})
                    report.update(status="PASS", provenance=provenance, **result,
                                 artifacts={p.relative_to(root).as_posix(): file_hash(p) for p in folder.rglob("*") if p.is_file()})
            elif args.command == 'host':
                provenance = {k: report[k] for k in ('commit', 'dirty_tree_fingerprint', 'host', 'python') if k in report}
                report.update(host_command(root, build, args, provenance))
            elif args.command == "lint":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python", "os") if k in report}
                progress.line("Questa compile gate: src/rtl and every registered FPGA top; no simulation")
                report.update(lint_questa(root, build, args, provenance, progress=progress))
            elif args.command == "sw":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
                report.update(oracle(root, build, args, provenance) if args.action == "oracle"
                              else conformance(root, build, args, provenance) if args.action == "conformance"
                              else asset_proof(root, build, args, provenance) if args.action == "asset-conformance"
                              else link_proof(root, build, args, provenance) if args.action == "link-conformance"
                              else build_target(root, build, args, provenance) if args.action == "build"
                              else library_stage(root, build, args, provenance) if args.action == "library"
                              else assemble_target(root, build, args, provenance))
            elif args.command == "tools":
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python", "os") if k in report}
                progress.line("Install the pinned Verilator into the shared host tool cache; no simulation")
                report.update(verilator_install.command(root, build, args, provenance))
            elif args.command == "sim" and args.action == "preflight":
                from .fixture_preflight import run
                report.update(run(root, build, args.target))
            else:
                if not 0 <= args.seed <= 2147483647:
                    raise ValueError("seed must be between 0 and 2147483647")
                provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python", "os") if k in report}
                # Capability validation precedes discovery, so an unsupported
                # pair never probes or falls back to another simulator.
                load_target(root, args.target, args.sim)
                progress.line(f"Simulation: target {args.target}; backend {args.sim}")
                with progress.stage(f"Discover {args.sim.capitalize()} tools"):
                    simulator = Simulator(args.sim, verilator_bin=args.verilator_bin,
                                          questa_bin=args.questa_bin, root=root)
                report.update(simulate(root, build, args, simulator, provenance, progress=progress,
                                       locked_at=locked_at, cpu_at=cpu_at))
                # The measured wall stays in this run's retained record and is
                # reported here, so an author reads what its run cost without a
                # tracked file changing under it. Writing it into the catalogue
                # is `tests record`, which names this tag.
                report.setdefault("notices", []).extend(measured_notices(root, args.target, report))
        except Exception as error:
            report.update(status="FAIL", error=str(error))
            if isinstance(error, AssemblyError):
                report['diagnostics'] = [error.diagnostic]
                diagnostic = build / 'sw' / ('diagnostics-' + uuid.uuid4().hex[:12] + '.json')
                atomic_json(diagnostic, report['diagnostics'])
                report['artifacts'] = {diagnostic.relative_to(root).as_posix(): file_hash(diagnostic)}
            failure_artifacts = {}
            failure_text = str(error) + "\n"
            if isinstance(error, ToolError):
                folder = build / "discovery" / uuid.uuid4().hex
                folder.mkdir(parents=True)
                log = folder / "failure.log"
                failure_text = error.output + "\n" + str(error) + "\n"
                log.write_text(failure_text, encoding="utf-8")
                failure_artifacts[log.relative_to(root).as_posix()] = file_hash(log)
                report["artifacts"] = failure_artifacts
                # A probe that refused carries its own record. Keep it beside the
                # failure so the argv and exit behind the refusal stay auditable,
                # exactly as a passing discovery records them.
                if error.record is not None:
                    report["discovery"] = [error.record]
                atomic_json(folder / "result.json", report)
            if operation_folder is not None:
                # The retained program.log decides what the failure means for the
                # board: nothing ran, quartus_pgm succeeded before the host record
                # failed, or quartus_pgm ran unconfirmed. No replay either way.
                report["device_state"] = device_state_after(operation_folder)
                failure_artifacts.update({p.relative_to(root).as_posix(): file_hash(p)
                                          for p in operation_folder.rglob("*") if p.is_file()})
                report["artifacts"] = failure_artifacts
            if args.command == "sim" and args.action == "test" and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", args.target):
                stage, mirror, authoritative = stage_paths(root, build, args.target, args.sim)
                failure = {"status": "FAIL", "error": str(error), "artifacts": failure_artifacts,
                           "simulator": args.sim, "os": platform.system(),
                           "authoritative_result": authoritative}
                atomic_text(stage / "sim.log", failure_text)
                atomic_json(stage / "result.json", failure)
                publish_mirror(root, mirror, failure, stage / "sim.log")
        publish(build, report)
    return report


def prepare_command(root, args, header, progress):
    """`sim prepare`: host preparation into an immutable attempt, no tag lock.

    The tag's stage records, manifest, status and latest pointer belong to
    the tag lock's holder and are not written here.
    """
    load_target(root, args.target, args.sim)
    build = tag_directory(root, args.tag)
    report = header(build.name)
    provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python", "os") if k in report}
    progress.line(f"Preparation: target {args.target}; backend {args.sim}; tag lock not taken")
    with progress.stage(f"Discover {args.sim.capitalize()} tools"):
        # Preparation launches no vsim, so it consults no license: the run that
        # adopts the attempt is what needs the checkout.
        simulator = Simulator(args.sim, verilator_bin=args.verilator_bin, questa_bin=args.questa_bin,
                              root=root, require_license=False)
    with progress.stage("Prepare attempt"):
        record = prepare(root, build, args, simulator, provenance)
    # The receipt keeps PREPARED so adoption can tell it from a run result;
    # the command reports PASS or FAIL like every other command.
    report.update(record, status="PASS" if record["status"] == "PREPARED" else "FAIL")
    return report


def _artifacts(report, *, suffix=None, contains=None):
    paths = report.get("artifacts", {})
    if isinstance(paths, dict):
        paths = paths.keys()
    elif not isinstance(paths, list):
        paths = []
    return sorted(path for path in paths
                  if (suffix is None or path.endswith(suffix))
                  and (contains is None or contains in path))


def _diagnostic(report):
    for suffix in ("failure.log", "program.log", "sim.log", "compile.log", "chain.log"):
        paths = _artifacts(report, suffix=suffix)
        if paths:
            return paths[-1]
    return None


def affected_lines(report):
    """Text rows for the advisory affected record: every unit, then the summary."""
    lines = [f"Base: {report['base']}  head: {report['head']}  {len(report.get('changes', []))} changed paths"]
    lines += [f"Fallback: {reason}" for reason in report.get("fallback", [])]
    for name, row in report["units"].items():
        lines.append(f"{name}: {row['decision']} {'; '.join(row.get('reasons', []))}".rstrip())
    lines.append(f"{report['selected']} selected, {report['review_candidates']} review candidates "
                 f"of {len(report['units'])} units")
    lines.append(f"Scope: {report['scope']}; required checks {report['required_checks']}")
    lines.append(f"Elapsed: {report.get('elapsed_seconds', 0):.1f}s")
    return lines


def current_host_command(argv):
    """Render a follow-up command for the host that just ran this one.

    The interpreter is the repository's portable spelling, and the arguments are
    quoted for the shell that host uses.
    """
    windows = platform.system() == "Windows"
    argv = ["python" if windows else "python3", *argv]
    return powershell_command(argv) if windows else shlex.join(argv)


def _human_result(args, report, progress):
    """Render the compact handoff after live stages have finished."""
    status = report.get("status", "FAIL")
    cache = report.get("cache")
    progress.line(f"Result: {status}" + (f" ({cache})" if cache else ""))
    if "error" in report:
        progress.line(f"Error: {report['error']}")
    diagnostic = _diagnostic(report)
    if status != "PASS" and diagnostic:
        progress.line(f"Diagnostic: {diagnostic}")

    if args.command == "sim" and args.action == "test":
        for path in _artifacts(report, suffix=".log", contains="/compile/"):
            progress.line(f"Compile log: {path}")
        sim_logs = _artifacts(report, suffix="sim.log", contains="/attempts/")
        if sim_logs:
            progress.line(f"Simulation log: {sim_logs[-1]}")
        if report.get("authoritative_result"):
            progress.line(f"Result record: {report['authoritative_result']}")
        waves = report.get("waves")
        if isinstance(waves, dict) and waves.get("path"):
            progress.line(f"Waveform ({waves.get('format', 'unknown').upper()}): {waves['path']}")
        if status == "PASS":
            progress.line("Next: " + current_host_command([
                "tools/build.py", "fpga", "build", "v05-board",
                "--quartus-bin", "<Quartus-bin>", "--tag", "fpga-v05"]))
        return

    if args.command == "fpga" and args.action == "build":
        if report.get("attempt_result"):
            progress.line(f"Result record: {report['attempt_result']}")
        bitstreams = _artifacts(report, suffix="/output/design.sof")
        if bitstreams:
            label = "Checked bitstream" if status == "PASS" else "Unverified bitstream artifact"
            progress.line(f"{label}: {bitstreams[-1]}")
        if status == "PASS":
            for line in fpga_hold.summary_lines(report.get("evidence", {}).get("hold_paths")):
                progress.line(line)
        # Quartus writes a .pof for every image; only a flash image records
        # onchip_flash evidence, so the record decides whether the lines print.
        flash_images = _artifacts(report, suffix="/output/design.pof")
        onchip_flash = report.get("evidence", {}).get("onchip_flash")
        if flash_images and onchip_flash and status == "PASS":
            pof = onchip_flash.get("pof", {})
            progress.line(f"Flash image (.pof, library in the user range): {flash_images[-1]}")
            progress.line(f"CFM0 used {pof.get('cfm0_used_bytes')} of {pof.get('cfm0_bytes')} bytes; spare {pof.get('cfm0_spare_bytes')}")
        if status == "PASS" and bitstreams and not report.get("build_id_override"):
            # Programming is a tool-availability decision now, so the fitting
            # host can offer its own Quartus directory and its own shell.
            progress.line("Next: " + current_host_command([
                "tools/build.py", "fpga", "program", "--sof", bitstreams[-1],
                "--quartus-bin", args.quartus_bin]))
        return

    if args.command == "fpga" and args.action == "program":
        if report.get("cable") and report.get("devices"):
            progress.line(f"JTAG: backend {report.get('backend', 'unknown')}; cable {report['cable']}; "
                          f"device {', '.join(report['devices'])}")
        if report.get("volatile_image"):
            progress.line(f"Raw volatile image: {report['volatile_image']}")
        if report.get("program_log"):
            progress.line(f"Program log: {report['program_log']}")
        if status != "PASS" and report.get("device_state"):
            progress.line(f"Device state: {report['device_state']}; no automatic replay")
        if report.get("pof"):
            if report.get("dry_run"):
                progress.line(f"Dry run: flash unchanged; command in {report.get('dry_run_log')}")
            elif status == "PASS":
                progress.line(f"Flash programmed, verified and blank-checked in {report.get('isp_seconds')} s; "
                              f".pof sha256 {report.get('pof_sha256')}")
                progress.line(f"Next: {report.get('next_step')}")
            return
        if report.get("wire_build_id"):
            progress.line(f"On-wire build ID: {report['wire_build_id']}")
            if status == "PASS" and report.get("fpga_target") == "v05-board":
                progress.line("Next (Windows PowerShell): " + powershell_command([
                    "python", "tools/gb_launcher.py", "--expected-build-id",
                    report["wire_build_id"], "--uart-port", "<UART-port>"]))
        return

    if args.command == "lint":
        if report.get("attempt_result"):
            progress.line(f"Result record: {report['attempt_result']}")
        failure = report.get("failure")
        if isinstance(failure, dict):
            for line in failure.get("errors", []):
                progress.line(line.strip())
        return

    progress.line(f"{report.get('cache', status)}: {args.command} tag={report.get('tag', '-')}")


# One build tool, one refused backend and one verified-access boundary. No
# command launches the other operating system or translates one backend into
# another. Only a source build is a host fact; `fpga build`, `fpga program`,
# `lint questa` and `--sim questa` decide by tool discovery inside their stages,
# so a missing tool or license names itself.
# The pinned Verilator is an autoconf, make and g++ source build, so there is no
# supported Windows Verilator for discovery to find; that refusal is a fact about
# the tool, not a policy.
VERILATOR_HOST = "Verilator simulation runs on Linux"
# `fpga program` used to refuse every non-Windows host because Linux JTAG access
# was unverified. It is verified for reading: `openFPGALoader` enumerates the
# attached cables on a host whose Quartus daemon cannot. So the refusal is now a
# tool-availability decision inside the stage, which names the missing programmer
# rather than the operating system. Writing to a board still needs the owner's
# authorization for that run; nothing here programs a board by itself.
# The pinned Verilator is an autoconf/make/g++ source build, so its
# installation belongs to the same host that runs it.
TOOLS_HOST = "Pinned host tool installation runs on Linux"


def simulator_command(args):
    return (args.command == "doctor" or args.command == "regress"
            or (args.command == "sim" and args.action in ("test", "prepare"))
            or (args.command == "tests" and args.action == "run"))


def resolve_simulator(args, system=None):
    """Resolve omission to the native backend and reject ignored tool options."""
    if not simulator_command(args):
        return
    if args.sim is None:
        args.sim = "questa" if (system or platform.system()) == "Windows" else "verilator"
    if args.sim == "verilator" and getattr(args, "questa_bin", None) is not None:
        raise ValueError("--questa-bin applies only to --sim questa")
    if args.sim == "verilator" and getattr(args, "intel_sim_lib", None) is not None:
        raise ValueError("--intel-sim-lib applies only to --sim questa")
    if args.sim == "questa" and getattr(args, "verilator_bin", None) is not None:
        raise ValueError("--verilator-bin applies only to --sim verilator")


def foreign_host(args):
    """The refusal message when this OS does not own the requested command.

    `fpga build`, `fpga program`, `lint questa` and `--sim questa` are absent:
    an installed Quartus, Questa or openFPGALoader runs them on any host, and
    their own discovery names the missing tool, the missing programmer or the
    missing Questa runtime license.
    """
    system = platform.system()
    if simulator_command(args) and args.sim == "verilator" and system == "Windows":
        return VERILATOR_HOST
    if args.command == "tools" and system == "Windows":
        return TOOLS_HOST
    return None


def main(argv=None, root=None):
    args = parser().parse_args(argv)
    root = Path(root or Path(__file__).resolve().parents[2]).resolve()
    report = {"status": "FAIL"}
    progress = Progress(not args.json)

    def header(tag):
        return {"tag": tag, "created": datetime.now(timezone.utc).isoformat(),
                "host": platform.platform(), "os": platform.system(), "python": platform.python_version(),
                "requested": vars(args), **git_state(root)}

    def publish(build, result):
        atomic_json(build / "manifest.json", result)
        atomic_json(build / "status.json", {"status": result["status"], "cache": result.get("cache")})
        if result["status"] == "PASS":
            atomic_text(root / "workdir/latest.txt", build.name + "\n")

    try:
        resolve_simulator(args)
        refusal = foreign_host(args)
        if refusal:
            report = {"tag": args.tag or "-", "os": platform.system(), "status": "FAIL", "error": refusal,
                      "requested": vars(args)}
        elif args.command == "regress":
            report = regress(root, args, header, publish)
        elif args.command == "tests":
            report = catalogue.command(root, args, header, publish)
        elif args.command == "vendor":
            # No build tag and no workspace: the command's output is a tracked
            # source change, reviewed like any other.
            report = header("-")
            report.update(status="PASS", **vendor_sources.accept(args.quartus_bin, args.source, args.reason))
        elif args.command == "clean":
            # No workspace: the tag directory itself is what clean removes.
            report = header(args.tag)
            report.update(clean(root, args.tag))
        elif args.command == "sim" and args.action == "test":
            # The single-target capability contract is checked before the tag
            # workspace is created. The stage repeats this check defensively.
            load_target(root, args.target, args.sim)
            report = tagged(root, args, header, publish, progress)
        elif args.command == "sim" and args.action == "prepare":
            report = prepare_command(root, args, header, progress)
        else:
            report = tagged(root, args, header, publish, progress)
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        guided = (args.command in ("fpga", "lint")
                  or (args.command == "sim" and args.action == "test"))
        if guided:
            _human_result(args, report, progress)
        else:
            print(f"{report.get('cache', report['status'])}: {args.command} tag={report.get('tag', '-')}")
            if "error" in report:
                print(report["error"])
        for line in report.get("notices", []):
            print(line)
        if args.command == "tests" and args.action == "affected" and "units" in report:
            for line in affected_lines(report):
                print(line)
        if args.command == "tests" and args.action == "run" and isinstance(report.get("units"), dict):
            # Preparation happens before the aggregate clock, so its cost is
            # named here rather than left to the JSON record alone.
            for name, step in (report.get("preparation") or {}).items():
                wall = f" in {step['elapsed_seconds']:.1f}s" if "elapsed_seconds" in step else ""
                print(f"Prepared {name}: {step['status']}{wall} {step.get('error', '')}".rstrip())
            for name, outcome in report["units"].items():
                if outcome["status"] != "PASS":
                    print(f"{name}: {outcome['status']} {outcome.get('reason', outcome.get('error', ''))}".rstrip())
            print(f"{report['selector']}: {report['selected']} selected, "
                  f"{len(report.get('failed', []))} failed, {len(report.get('skipped', []))} skipped")
            print(f"Elapsed: {report.get('elapsed_seconds', 0):.1f}s of {report.get('budget_seconds')}s budget")
            for line in drift_lines(report):
                print(line)
        if args.command == "tests" and args.action == "record":
            for line in recorded_lines(report):
                print(line)
            for name, reason in (report.get("not_recorded") or {}).items():
                print(f"Not recorded {name}: {reason}")
            if "measured" in report:
                sitting = report["measured"]
                print(f"{report['durations_written']} written in {catalogue.CATALOGUE}, measured "
                      f"{sitting['at']} at commit {sitting['commit']} on {sitting['host']}")
        if args.command == "tests" and "tests" in report:
            for name in report["tests"]:
                print(name)
            print(f"{report['selector']}: {report['selected']} selected, "
                  f"{report['measured']} measured, {report['measured_seconds']:.1f}s last measured total")
        if args.command == "tests" and "problems" in report:
            for problem in report["problems"]:
                print(problem)
            # Each tests action shapes its own record: only validate counts the
            # catalogue, while closure-trace reports the units it traced.
            if args.action == "validate":
                print(f"{report['units']} units, {len(report['not_runnable'])} not runnable, "
                      f"{len(report.get('retired', []))} retired")
            elif args.action == "closure-trace":
                print(f"{report.get('traced', 0)} of {len(report.get('units', {}))} units traced, "
                      f"{len(report['problems'])} problems")
        if args.command == "sim" and args.action == "prepare" and report.get("prepared_record"):
            print(f"Prepared attempt: {report['prepared']} ({report.get('prepare_seconds', 0):.1f}s); receipt {report['prepared_record']}")
            print("Next: " + powershell_command(["python", "tools/build.py", "sim", "test", args.target,
                                                 "--tag", report["tag"], "--prepared", report["prepared"]]))
        if args.command == "sim" and report.get("status") == "SKIPPED":
            print(f"{args.target}: SKIPPED {report['reason']}")
        if args.command == "regress" and "targets" in report:
            for name, outcome in report["targets"].items():
                detail = [outcome.get("cache"), outcome.get("reason", outcome.get("error"))]
                print(" ".join([f"{name}: {outcome['status']}", *[part for part in detail if part]]))
            print(f"Elapsed: {report.get('elapsed_seconds', 0):.1f}s of {report.get('budget_seconds')}s budget")
        if args.command == "doctor" and "checks" in report:
            print(report["scope"])
            for name, check in report["checks"].items():
                print(f"{name}: {check['status']} {check.get('error', check.get('detail', ''))}")
                if "notice" in check:
                    print(check["notice"])
            # Named before readiness: a reader who stops at the status line must
            # still see what the run could not read.
            for item in report.get("unreadable", []):
                print(f"Not read: {item}")
            print(f"Readiness: {report['readiness']}; untested: {', '.join(report['untested'])}")
    # SKIPPED shares WARNING's exit: the requested evidence is incomplete, not wrong.
    return {"PASS": 0, "FAIL": 1, "WARNING": 2, "SKIPPED": 2}[report["status"]]
