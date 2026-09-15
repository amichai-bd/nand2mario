"""One self-checking simulation stage with immutable attempt artifacts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import re
import sys
import time
import uuid

from .hdl import dependencies
from .simulator import ToolError
from .verilator import commands as verilator_commands, diagnostic, WAVES
from .records import atomic_json, atomic_text, cache_matches, digest, file_hash, read_json
from . import python_tb
from .simulation_peer import Peer

# Every registry target names the simulator it runs on. A questa target is
# retired: it is reported SKIPPED by name and never launched.
SIMULATORS = ("verilator", "questa")
RETIRED = "questa"
RETIRED_REASON = "questa-retired"


def simulator_problem(name, target):
    """The validation message for a target's simulator field, or None."""
    if not isinstance(target, dict) or target.get("simulator") not in SIMULATORS:
        return f"target {name} must declare simulator as one of {', '.join(SIMULATORS)}"
    return None


def retired(target):
    return target["simulator"] == RETIRED


def load_target(root, name):
    registry = root / "src/dv/builder/targets.json"
    targets = json.loads(registry.read_text(encoding="utf-8"))
    if name not in targets or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError(f"unknown simulation target: {name}")
    target = targets[name]
    problem = simulator_problem(name, target)
    if problem:
        raise ValueError(problem)
    if not isinstance(target.get("signature"), str) or not target["signature"].strip():
        raise ValueError("target signature must be a nonempty string")
    if target["expected_exit"] not in ("zero", "nonzero"):
        raise ValueError("expected_exit must be zero or nonzero")
    timeout = target.get("timeout_seconds", 60)
    from .test_budget import target_selection
    # The validator and the supervisor read the same row, so a declared
    # allowance bounds the nested command exactly as it bounds the wall.
    maximum_timeout = target_selection(name, target)[0]
    if type(timeout) is not int or not 1 <= timeout <= maximum_timeout:
        raise ValueError(f"simulation target timeout_seconds must be an integer in 1..{maximum_timeout}")
    for source in target["sources"]:
        path = (root / source).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"missing or out-of-tree source: {source}")
    if "driver" in target:
        driver = target["driver"]
        if not isinstance(driver, dict) or set(driver) - {"script", "peer", "inputs", "access", "preload"} or not {"script", "peer", "inputs"} <= set(driver) or not isinstance(driver["inputs"], list):
            raise ValueError("simulation driver requires script, peer and inputs")
        if type(driver.get("preload", False)) is not bool:
            raise ValueError("simulation driver preload must be a boolean")
        if not isinstance(driver.get("access", []), list) or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in driver.get("access", [])):
            raise ValueError("driver access must name top-level DV objects")
        for source in [driver["script"], driver["peer"], *driver["inputs"]]:
            if not isinstance(source, str):
                raise ValueError("simulation driver inputs must be paths")
            path = (root / source).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file():
                raise ValueError(f"missing or out-of-tree driver input: {source}")
    if not retired(target):
        # The Intel models were a Questa binding; a target that still needs
        # one stays questa until its area migrates. A verilator driver's
        # script is the cocotb peer module; the retired Tcl script is refused.
        if target.get("vendor_model") is not None:
            raise ValueError(f"target {name}: vendor_model is not supported under verilator")
        if "driver" in target:
            if not target["driver"]["script"].endswith(".py"):
                raise ValueError(f"target {name}: driver script must be the Verilator peer module (.py)")
            if not target["driver"].get("access"):
                raise ValueError(f"target {name}: a Verilator driver needs a nonempty access list")
    python_tb.validate(root, target, name)
    return target, registry


def skipped_record(root, build, args, provenance=None):
    """Publish and return the SKIPPED record of a retired target; nothing runs."""
    record = {"status": "SKIPPED", "reason": RETIRED_REASON, "target": args.target,
              "simulator": RETIRED, "os": platform.system(), "seed": args.seed,
              "provenance": provenance or {}, "finished": datetime.now(timezone.utc).isoformat()}
    atomic_json(build / "sim/test" / args.target / "result.json", record)
    return record


def simulate(root, build, args, simulator, provenance=None):
    target, registry = load_target(root, args.target)
    if retired(target):
        return skipped_record(root, build, args, provenance)
    driver = target.get("driver")
    # A driver target runs its SystemVerilog testbench under the cocotb peer,
    # so it needs the pinned Python runtime like a Python testbench.
    python_runtime = python_tb.discover() if target.get("testbench") == "python" or driver else None
    peer_config = python_tb.peer_config(target) if driver else None
    hdl_inputs = dependencies(root, target["sources"])
    inputs = hdl_inputs + [registry.relative_to(root).as_posix(), "tools/build.py"]
    inputs += [str(p.relative_to(root)).replace("\\", "/") for p in (root / "tools/n2m").glob("*.py")]
    inputs += ["tools/n2m/dependencies.json"]
    if driver:
        inputs += [driver["script"], driver["peer"], *driver["inputs"]]
        inputs += ["src/dv/python/requirements.txt", "src/dv/python/THIRD_PARTY.md"]
    if target.get("testbench") == "python":
        inputs += target["python"]["inputs"] + ["src/dv/python/requirements.txt", "src/dv/python/THIRD_PARTY.md"]
    elif target.get("preload") is not None:
        # A Python target's inputs already carry its fixture; a SystemVerilog
        # target declares them, so a changed fixture input rebuilds either.
        inputs += target["preload_inputs"]
    hashes = {p: file_hash(root / p) for p in inputs}
    options = {"seed": args.seed, "target": args.target, "definition": target,
               "simulator": "verilator", "os": platform.system()}
    if python_runtime:
        options["python_runtime"] = python_runtime
    if driver:
        options["peer_python"] = {"path": sys.executable, "sha256": file_hash(Path(sys.executable)), "version": sys.version}
    fixture_tools = None
    if target.get("preload") == "mooneye-reg-f":
        # The locked fixture is built by the host compiler and CMake; their
        # identity shapes the image, so it enters the fingerprint.
        from .mooneye import tool_identity
        fixture_tools = tool_identity(root)
        options["fixture_tools"] = fixture_tools
    fingerprint = digest({"inputs": hashes, "tools": simulator.info, "options": options})
    stage = build / "sim/test" / args.target
    current = stage / "result.json"
    old = read_json(current)
    if not args.rebuild and cache_matches(old, fingerprint, root, build) and (not python_runtime or target["expected_exit"] != "zero" or python_tb.evidence(root, old, peer_config or target["python"], driver=bool(driver))):
        return {**old, "cache": "CACHED"}
    attempt_id = uuid.uuid4().hex
    attempt = stage / "attempts" / attempt_id
    compile_dir = build / "compile/verilator" / args.target / attempt_id
    for path in (attempt / "waves", attempt / "coverage", compile_dir):
        path.mkdir(parents=True, exist_ok=True)
    from .test_budget import target_selection
    record = {"status": "RUNNING", "cache": "BUILT", "fingerprint": fingerprint,
              "inputs": hashes, "tools": simulator.info, "seed": args.seed,
              "simulator": "verilator", "os": platform.system(),
              "waves": {"format": "fst", "path": (attempt / WAVES).relative_to(root).as_posix()},
              "timing": {"build_seconds": 0.0, "run_seconds": 0.0},
              "options": options, "commands": [], "artifacts": {},
              "started": datetime.now(timezone.utc).isoformat(),
              "provenance": provenance or {}}
    # Invalidate the previous success before execution. A killed process leaves
    # RUNNING and a lock, never a reusable success for its unfinished request.
    atomic_json(current, record)
    log = compile_dir / "prepare.log"
    try:
        commands = verilator_commands(simulator, root, target, args.seed, compile_dir, attempt,
                                      python_runtime=python_runtime, fixture_tools=fixture_tools)
        for argv, cwd, log, expected in commands:
            command = simulator.command(argv)
            record["commands"].append({"argv": command, "cwd": str(cwd)})
            with (build / "commands.log").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record["commands"][-1]) + "\n")
            running = log.name == "sim.log"
            # The C++ build of a large design is bounded by the target's own
            # selected wall; the run keeps the registry's runtime bound.
            if running:
                call_options = {"timeout": target["timeout_seconds"]} if "timeout_seconds" in target else {}
            else:
                call_options = {"timeout": target_selection(args.target, target)[0]}
            record["commands"][-1]["timeout_seconds"] = call_options.get("timeout", 60)
            if running and python_runtime:
                call_options["env"] = python_tb.environment(root, target, attempt, args.seed, python_runtime)
                record["python_results_file"] = (attempt / "results.xml").relative_to(root).as_posix()
            if running and target.get("preload") is not None:
                # Recheck the prepared image and files immediately before
                # launch; the run reads them from the attempt directory.
                from .preload import verify
                record["preload"] = verify(attempt)
            peer = None
            result = None
            started = time.monotonic()
            try:
                if running and driver:
                    # The builder owns the Python peer; the cocotb peer inside
                    # the run connects to its listener and touches only the
                    # declared access list.
                    peer = Peer(root, attempt, driver["peer"])
                    port = peer.start()
                    if driver.get("preload", False):
                        from .preload import verify
                        record["preload"] = verify(attempt)
                    call_options["env"].update(N2M_PEER_PORT=str(port), N2M_DRIVER_ACCESS=",".join(driver["access"]))
                    record["peer"] = {"port": port, "access": list(driver["access"]), "module": peer_config["module"]}
                result = simulator.run(argv, cwd=cwd, **call_options)
            finally:
                elapsed = time.monotonic() - started
                record["commands"][-1]["elapsed_seconds"] = elapsed
                record["timing"]["run_seconds" if running else "build_seconds"] += elapsed
                if peer is not None:
                    # The Python peer completed only when the run exited zero
                    # and the cocotb peer reported PASS; any other outcome
                    # reaps it and keeps its transcript and exit for the record.
                    if result is not None:
                        record["python_results"] = python_tb.results(attempt / "results.xml", peer_config)
                    peer.close(result is not None and result.returncode == 0
                               and record.get("python_results", {}).get("status") == "PASS")
            log.write_text(result.stdout, encoding="utf-8")
            record["commands"][-1]["exit_code"] = result.returncode
            if running and python_runtime and not driver:
                record["python_results"] = python_tb.results(attempt / "results.xml", target["python"])
            if (result.returncode == 0) != (expected == "zero"):
                raise RuntimeError(f"unexpected exit {result.returncode}; see {log.relative_to(root)}")
            if running and python_runtime and expected == "zero" and record["python_results"]["status"] != "PASS":
                if driver:
                    raise RuntimeError(f"Verilator peer failed: {python_tb.failure_name(record['python_results'])}")
                raise RuntimeError(f"Python test failed: {record['python_results']}")
            problem = diagnostic(result.stdout, target["signature"] if expected == "nonzero" else None,
                                 peer=peer_config["module"] if driver else None)
            if problem:
                raise RuntimeError(f"{problem}; see {log.relative_to(root)}")
        if target["signature"] not in result.stdout:
            raise RuntimeError(f"missing expected signature: {target['signature']}")
        if not (attempt / WAVES).is_file():
            raise RuntimeError(f"missing retained waves: {WAVES}")
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
    if python_runtime and record["status"] == "PASS" and target["expected_exit"] == "zero" and not python_tb.evidence(root, record, peer_config or target["python"], driver=bool(driver)):
        record.update(status="FAIL", error="incomplete Python test evidence")
    atomic_json(attempt / "result.json", record)
    # result.json is authoritative. Immutable attempt paths keep old readers
    # valid while the publication pointer changes in one atomic replace.
    atomic_text(stage / "sim.log", (attempt / "sim.log").read_text(encoding="utf-8"))
    atomic_json(current, record)
    return record
