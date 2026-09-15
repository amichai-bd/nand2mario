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
from .verilator import commands as verilator_commands, diagnostic as verilator_diagnostic, WAVES as VERILATOR_WAVES
from .questa import commands as questa_commands, diagnostic as questa_diagnostic
from .records import atomic_json, atomic_text, cache_matches, digest, file_hash, read_json
from .progress import Progress, display_path
from . import intel_adc, intel_memory, python_tb
from .simulation_peer import Peer

# Every registry target names each backend whose observable checks it preserves.
SIMULATORS = ("verilator", "questa")
VENDOR_MODELS = ("intel-memory", "intel-adc", "intel-controls")


def simulator_problem(name, target):
    """The validation message for a target's simulator capability list, or None."""
    simulators = target.get("simulators") if isinstance(target, dict) else None
    if (not isinstance(simulators, list) or not simulators
            or any(simulator not in SIMULATORS for simulator in simulators)
            or len(set(simulators)) != len(simulators)):
        return (f"target {name} must declare simulators as a nonempty unique list "
                f"drawn from {', '.join(SIMULATORS)}")
    return None


def require_backend(name, target, backend):
    """Refuse an unsupported pair before tool discovery or launch."""
    if backend not in SIMULATORS:
        raise ValueError(f"unsupported simulator: {backend}; expected verilator or questa")
    if backend not in target["simulators"]:
        raise ValueError(f"target {name} does not support simulator {backend}; supported: "
                         + ", ".join(target["simulators"]))


def load_target(root, name, backend=None):
    registry = root / "src/dv/builder/targets.json"
    targets = json.loads(registry.read_text(encoding="utf-8"))
    if name not in targets or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError(f"unknown simulation target: {name}")
    target = targets[name]
    problem = simulator_problem(name, target)
    if problem:
        raise ValueError(problem)
    if backend is not None:
        require_backend(name, target, backend)
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
    if target.get("vendor_model") not in (None, *VENDOR_MODELS):
        raise ValueError(f"target {name}: vendor_model must be one of {', '.join(VENDOR_MODELS)}")
    if "intel_mixed_mode_instances" in target and "questa" not in target["simulators"]:
        raise ValueError(f"target {name}: intel_mixed_mode_instances requires Questa support")
    # Elaboration-time selection is a build option, not a runtime plusarg.
    defines = target.get("defines", [])
    if not isinstance(defines, list) or any(not isinstance(d, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(=[A-Za-z0-9_]+)?", d) for d in defines):
        raise ValueError(f"target {name}: defines must list NAME or NAME=VALUE identifiers")
    if "driver" in target:
        if target["simulators"] != ["verilator"] or not target["driver"]["script"].endswith(".py"):
            raise ValueError(f"target {name}: the Python peer driver supports only Verilator")
        if not target["driver"].get("access"):
            raise ValueError(f"target {name}: a Verilator driver needs a nonempty access list")
    python_tb.validate(root, target, name)
    return target, registry


def stage_paths(root, build, target, backend):
    """Return the backend authority and legacy last-completed-run mirror."""
    mirror = build / "sim/test" / target
    stage = mirror / backend
    return stage, mirror, (stage / "result.json").relative_to(root).as_posix()


def publish_mirror(root, mirror, record, log=None):
    """Atomically update the compatibility mirror; it is never a cache input."""
    mirrored = {**record, "authoritative_result": record["authoritative_result"]}
    if log is not None and log.is_file():
        atomic_text(mirror / "sim.log", log.read_text(encoding="utf-8"))
    atomic_json(mirror / "result.json", mirrored)


def simulate(root, build, args, simulator, provenance=None, progress=None):
    progress = progress or Progress(False)
    backend = simulator.backend
    target, registry = load_target(root, args.target, backend)
    driver = target.get("driver")
    # A driver target runs its SystemVerilog testbench under the cocotb peer,
    # so it needs the pinned Python runtime like a Python testbench.
    python_runtime = python_tb.discover(backend) if target.get("testbench") == "python" or driver else None
    peer_config = python_tb.peer_config(target) if driver else None
    hdl_inputs = dependencies(root, target["sources"])
    vendor_model = None
    if backend == "questa":
        vendor_model = intel_memory.resolve(root, simulator, target, getattr(args, "intel_sim_lib", None))
        if vendor_model is not None:
            if vendor_model["selection"] in ("intel-adc", "intel-controls"):
                intel_adc.reject_shadow_models(root, hdl_inputs)
            intel_memory.reject_shadow_models(root, hdl_inputs)
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
               "simulator": backend, "os": platform.system()}
    if target.get("vendor_model") is not None:
        options["vendor_model"] = (vendor_model if backend == "questa" else
                                   {"synthesis_binding": target["vendor_model"],
                                    "simulation": "repository double under VERILATOR"})
    if python_runtime:
        options["python_runtime"] = python_runtime
    if driver:
        options["peer_python"] = {"path": sys.executable, "sha256": file_hash(Path(sys.executable)), "version": sys.version}
    fixture_tools = None
    if target.get("preload") == "mooneye-reg-f":
        # The locked fixture is built by the host compiler and CMake; their
        # identity shapes the image, so it enters the fingerprint.
        from .mooneye import tool_identity
        installation = Path(simulator.tools["vlog"]).resolve().parents[2] if backend == "questa" else None
        fixture_tools = tool_identity(root, installation)
        options["fixture_tools"] = fixture_tools
    fingerprint = digest({"inputs": hashes, "tools": simulator.info, "options": options})
    stage, mirror, authoritative = stage_paths(root, build, args.target, backend)
    current = stage / "result.json"
    old = read_json(current)
    if not args.rebuild and cache_matches(old, fingerprint, root, build) and (not python_runtime or (driver and target["expected_exit"] != "zero") or python_tb.evidence(root, old, target, driver=bool(driver))):
        cached = {**old, "cache": "CACHED", "authoritative_result": authoritative}
        publish_mirror(root, mirror, cached, stage / "sim.log")
        progress.cached("Compile and elaborate")
        progress.cached("Run simulation")
        progress.cached("Check simulation result")
        return cached
    attempt_id = uuid.uuid4().hex
    attempt = stage / "attempts" / attempt_id
    compile_dir = build / "compile" / backend / args.target / attempt_id
    for path in (attempt / "waves", attempt / "coverage", compile_dir):
        path.mkdir(parents=True, exist_ok=True)
    from .test_budget import target_selection
    record = {"status": "RUNNING", "cache": "BUILT", "fingerprint": fingerprint,
              "inputs": hashes, "tools": simulator.info, "seed": args.seed,
              "simulator": backend, "os": platform.system(),
              "waves": {"format": "fst" if backend == "verilator" else "wlf",
                        "path": (attempt / (VERILATOR_WAVES if backend == "verilator"
                                             else "waves/simulation.wlf")).relative_to(root).as_posix()},
              "timing": {"build_seconds": 0.0, "run_seconds": 0.0},
              "options": options, "commands": [], "artifacts": {},
              "authoritative_result": authoritative,
              "started": datetime.now(timezone.utc).isoformat(),
              "provenance": provenance or {}}
    # Invalidate the previous success before execution. A killed process leaves
    # RUNNING and a lock, never a reusable success for its unfinished request.
    atomic_json(current, record)
    log = compile_dir / "prepare.log"
    active_stage = None
    try:
        commands = (verilator_commands(simulator, root, target, args.seed, compile_dir, attempt,
                                       python_runtime=python_runtime, fixture_tools=fixture_tools)
                    if backend == "verilator" else
                    questa_commands(simulator, root, target, args.seed, compile_dir, attempt,
                                    vendor_model=vendor_model, python_runtime=python_runtime,
                                    fixture_tools=fixture_tools))
        for argv, cwd, log, expected in commands:
            running = log.name == "sim.log"
            label = "Run simulation" if running else "Compile and elaborate"
            if not running and log.name not in ("build.log", "compile.log"):
                label += ": " + log.stem.replace("-", " ")
            detail = f"log: {display_path(root, log)}"
            active_stage = (label, progress.begin(label, detail), detail)
            command = simulator.command(argv)
            record["commands"].append({"argv": command, "cwd": str(cwd)})
            with (build / "commands.log").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record["commands"][-1]) + "\n")
            # Verilator's C++ build and Questa's vendor compilation share the
            # target wall; the run keeps the registry's runtime bound.
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
                if result is not None:
                    # Retain the transcript before the peer is judged: a peer
                    # that exits nonzero after a passing run must not lose it.
                    log.write_text(result.stdout, encoding="utf-8")
                    record["commands"][-1]["exit_code"] = result.returncode
                if peer is not None:
                    # The Python peer completed only when the run exited zero
                    # and the cocotb peer reported PASS; any other outcome
                    # reaps it and keeps its transcript and exit for the record.
                    if result is not None:
                        record["python_results"] = python_tb.results(attempt / "results.xml", peer_config)
                    peer.close(result is not None and result.returncode == 0
                               and record.get("python_results", {}).get("status") == "PASS")
            if running and python_runtime and not driver:
                record["python_results"] = python_tb.results(attempt / "results.xml", target["python"])
            # cocotb ends a failed Python testbench through $finish, so its
            # named XML verdict remains separate from the raw process exit.
            peer_failure = (running and python_runtime and driver and expected == "nonzero"
                            and result.returncode == 0 and python_tb.accepted(record["python_results"], target))
            if ((result.returncode == 0)
                    != (expected == "zero" or (python_runtime is not None and not driver))
                    and not peer_failure):
                raise RuntimeError(f"unexpected exit {result.returncode}; see {log.relative_to(root)}")
            if running and python_runtime and driver:
                if expected == "zero" and record["python_results"]["status"] != "PASS":
                    raise RuntimeError(f"{backend.capitalize()} peer failed: {python_tb.failure_name(record['python_results'])}")
            elif running and python_runtime and not python_tb.accepted(record["python_results"], target):
                raise RuntimeError(f"Python test verdict does not match expected_exit {target['expected_exit']}: {record['python_results']}")
            checked_output = result.stdout
            if backend == "questa":
                if log.name == "adc-pll-generate.log":
                    record["generated_adc_pll"] = intel_adc.verify_generated(cwd)
                if log.name == "intel-adc-control-compile.log":
                    checked_output, record["explained_compile_diagnostics"] = \
                        intel_adc.classify_compile_diagnostics(checked_output, vendor_model, log.name)
                if running:
                    if vendor_model and vendor_model["selection"] in ("intel-adc", "intel-controls"):
                        memory_explained = []
                        if vendor_model["selection"] == "intel-controls":
                            checked_output, memory_explained = intel_memory.classify_diagnostics(
                                checked_output, vendor_model["memory_diagnostics"])
                        checked_output, adc_explained = intel_adc.classify_sim_diagnostics(
                            checked_output, vendor_model,
                            python_access=bool(python_runtime) and vendor_model["selection"] == "intel-controls")
                        record["explained_diagnostics"] = memory_explained + adc_explained
                    else:
                        checked_output, record["explained_diagnostics"] = \
                            intel_memory.classify_diagnostics(checked_output, vendor_model)
                    if python_runtime:
                        checked_output, explained_python = python_tb.classify_questa(checked_output)
                        if explained_python:
                            record["explained_python_diagnostics"] = explained_python
                problem = questa_diagnostic(
                    checked_output,
                    target["signature"] if (running and not python_runtime
                                             and target["expected_exit"] == "nonzero") else None)
            else:
                explained = python_tb.explained_warnings(target) if running and python_runtime and (not driver or peer_failure) else ()
                problem = verilator_diagnostic(
                    checked_output, target["signature"] if expected == "nonzero" else None,
                    explained=explained, peer=peer_config["module"] if driver else None)
            if problem:
                raise RuntimeError(f"{problem}; see {log.relative_to(root)}")
            progress.finish(active_stage[0], active_stage[1], detail=active_stage[2])
            active_stage = None
        active_stage = ("Check simulation result",
                        progress.begin("Check simulation result"), None)
        if target["signature"] not in result.stdout:
            raise RuntimeError(f"missing expected signature: {target['signature']}")
        waves = VERILATOR_WAVES if backend == "verilator" else "waves/simulation.wlf"
        if not (attempt / waves).is_file():
            raise RuntimeError(f"missing retained waves: {waves}")
        progress.finish(active_stage[0], active_stage[1], status="PASS", detail=active_stage[2])
        active_stage = None
        record["status"] = "PASS"
    except Exception as error:
        if active_stage is not None:
            progress.finish(active_stage[0], active_stage[1], status="FAIL", detail=active_stage[2])
        if isinstance(error, ToolError):
            log.write_text(error.output + "\n" + str(error) + "\n", encoding="utf-8")
        record["status"] = "FAIL"
        record["error"] = str(error)
        if not (attempt / "sim.log").exists():
            (attempt / "sim.log").write_text(str(error) + "\n", encoding="utf-8")
    record["finished"] = datetime.now(timezone.utc).isoformat()
    artifacts = [p for base in (compile_dir, attempt) for p in base.rglob("*") if p.is_file()]
    record["artifacts"] = {p.relative_to(root).as_posix(): file_hash(p) for p in artifacts}
    if python_runtime and record["status"] == "PASS" and not (driver and target["expected_exit"] != "zero") and not python_tb.evidence(root, record, target, driver=bool(driver)):
        record.update(status="FAIL", error="incomplete Python test evidence")
    atomic_json(attempt / "result.json", record)
    # The backend-qualified record is authoritative. The generic files are
    # compatibility mirrors of the last completed run and are never reused.
    atomic_text(stage / "sim.log", (attempt / "sim.log").read_text(encoding="utf-8"))
    atomic_json(current, record)
    publish_mirror(root, mirror, record, attempt / "sim.log")
    return record
