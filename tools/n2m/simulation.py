"""One self-checking simulation stage with immutable attempt artifacts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from .hdl import dependencies
from .simulator import ToolError
from .questa import commands as questa_commands, diagnostic
from .records import atomic_json, atomic_text, cache_matches, digest, file_hash, read_json


def load_target(root, name):
    registry = root / "src/dv/builder/targets.json"
    targets = json.loads(registry.read_text(encoding="utf-8"))
    if name not in targets or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError(f"unknown simulation target: {name}")
    target = targets[name]
    if not isinstance(target.get("signature"), str) or not target["signature"].strip():
        raise ValueError("target signature must be a nonempty string")
    if target["expected_exit"] not in ("zero", "nonzero"):
        raise ValueError("expected_exit must be zero or nonzero")
    for source in target["sources"]:
        path = (root / source).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"missing or out-of-tree source: {source}")
    return target, registry


def simulate(root, build, args, simulator, provenance=None):
    target, registry = load_target(root, args.target)
    inputs = dependencies(root, target["sources"]) + [registry.relative_to(root).as_posix(), "tools/build.py"]
    inputs += [str(p.relative_to(root)).replace("\\", "/") for p in (root / "tools/n2m").glob("*.py")]
    inputs += ["tools/n2m/dependencies.json"]
    hashes = {p: file_hash(root / p) for p in inputs}
    options = {"seed": args.seed, "target": args.target, "definition": target}
    fingerprint = digest({"inputs": hashes, "tools": simulator.info, "options": options})
    stage = build / "sim/test" / args.target
    current = stage / "result.json"
    old = read_json(current)
    if not args.rebuild and cache_matches(old, fingerprint, root, build):
        return {**old, "cache": "CACHED"}
    attempt_id = uuid.uuid4().hex
    attempt = stage / "attempts" / attempt_id
    backend = "questa" if simulator.backend == "questa" else "iverilog"
    compile_dir = build / "compile" / backend / args.target / attempt_id
    for path in (attempt / "waves", attempt / "coverage", compile_dir):
        path.mkdir(parents=True, exist_ok=True)
    record = {"status": "RUNNING", "cache": "BUILT", "fingerprint": fingerprint,
              "inputs": hashes, "tools": simulator.info, "seed": args.seed,
              "options": options, "commands": [], "artifacts": {},
              "started": datetime.now(timezone.utc).isoformat(),
              "provenance": provenance or {}}
    # Invalidate the previous success before execution. A killed process leaves
    # RUNNING and a lock, never a reusable success for its unfinished request.
    atomic_json(current, record)
    log = compile_dir / "prepare.log"
    try:
        if simulator.backend == "questa":
            commands = questa_commands(simulator, root, target, args.seed, compile_dir, attempt)
        else:
            binary = compile_dir / "simulation.vvp"
            compile_argv = [simulator.compiler, "-g2012", "-Wall", "-s", target["top"],
                            "-I", simulator.path(root), "-o", simulator.path(binary),
                            *[simulator.path(root / source) for source in target["sources"]]]
            sim_argv = [simulator.runtime, simulator.path(binary), f"+seed={args.seed}", *target["args"]]
            commands = [(compile_argv, compile_dir, compile_dir / "compile.log", "zero"),
                        (sim_argv, attempt, attempt / "sim.log", target["expected_exit"])]
        for argv, cwd, log, expected in commands:
            command = simulator.command(argv)
            record["commands"].append({"argv": command, "cwd": str(cwd)})
            with (build / "commands.log").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record["commands"][-1]) + "\n")
            result = simulator.run(argv, cwd=cwd)
            log.write_text(result.stdout, encoding="utf-8")
            record["commands"][-1]["exit_code"] = result.returncode
            if (result.returncode == 0) != (expected == "zero"):
                raise RuntimeError(f"unexpected exit {result.returncode}; see {log.relative_to(root)}")
            problem = diagnostic(result.stdout, target["signature"] if expected == "nonzero" else None)
            if problem:
                raise RuntimeError(f"{problem}; see {log.relative_to(root)}")
        if target["signature"] not in result.stdout:
            raise RuntimeError(f"missing expected signature: {target['signature']}")
        record["status"] = "PASS"
    except Exception as error:
        if isinstance(error, ToolError):
            log.write_text(error.output + "\n" + str(error) + "\n", encoding="utf-8")
        record["status"] = "FAIL"
        record["error"] = str(error)
        if not (attempt / "sim.log").exists():
            (attempt / "sim.log").write_text(str(error) + "\n", encoding="utf-8")
    record["finished"] = datetime.now(timezone.utc).isoformat()
    artifacts = [p for base in (compile_dir, attempt) for p in base.rglob("*") if p.is_file()]
    record["artifacts"] = {p.relative_to(root).as_posix(): file_hash(p) for p in artifacts}
    atomic_json(attempt / "result.json", record)
    # result.json is authoritative. Immutable attempt paths keep old readers
    # valid while the publication pointer changes in one atomic replace.
    atomic_text(stage / "sim.log", (attempt / "sim.log").read_text(encoding="utf-8"))
    atomic_json(current, record)
    return record
