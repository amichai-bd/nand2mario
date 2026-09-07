"""One self-checking simulation stage with immutable attempt artifacts."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import uuid

from .hdl import dependencies
from .simulator import ToolError
from .questa import commands as questa_commands, diagnostic
from .records import atomic_json, atomic_text, cache_matches, digest, file_hash, read_json
from . import intel_memory, intel_adc
from .simulation_peer import Peer


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
    timeout = target.get("timeout_seconds", 60)
    maximum_timeout = 1500 if "driver" in target else 600
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
    return target, registry


def simulate(root, build, args, simulator, provenance=None):
    target, registry = load_target(root, args.target)
    hdl_inputs = dependencies(root, target["sources"])
    vendor_model = intel_memory.resolve(root, simulator, target, getattr(args, "intel_sim_lib", None))
    if vendor_model is not None:
        if vendor_model["selection"] == "intel-adc":
            intel_adc.reject_shadow_models(root, hdl_inputs)
        else:
            intel_memory.reject_shadow_models(root, hdl_inputs)
    inputs = hdl_inputs + [registry.relative_to(root).as_posix(), "tools/build.py"]
    inputs += [str(p.relative_to(root)).replace("\\", "/") for p in (root / "tools/n2m").glob("*.py")]
    inputs += ["tools/n2m/dependencies.json"]
    if "driver" in target:
        inputs += [target["driver"]["script"], target["driver"]["peer"], *target["driver"]["inputs"]]
    hashes = {p: file_hash(root / p) for p in inputs}
    options = {"seed": args.seed, "target": args.target, "definition": target, "vendor_model": vendor_model}
    if "driver" in target:
        options["peer_python"] = {"path": sys.executable, "sha256": file_hash(Path(sys.executable)), "version": sys.version}
    fingerprint = digest({"inputs": hashes, "tools": simulator.info, "options": options})
    stage = build / "sim/test" / args.target
    current = stage / "result.json"
    old = read_json(current)
    if not args.rebuild and cache_matches(old, fingerprint, root, build):
        return {**old, "cache": "CACHED"}
    attempt_id = uuid.uuid4().hex
    attempt = stage / "attempts" / attempt_id
    backend = "questa"
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
        commands = questa_commands(simulator, root, target, args.seed, compile_dir, attempt, vendor_model=vendor_model)
        for argv, cwd, log, expected in commands:
            command = simulator.command(argv)
            record["commands"].append({"argv": command, "cwd": str(cwd)})
            with (build / "commands.log").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record["commands"][-1]) + "\n")
            call_options = {"timeout": target["timeout_seconds"]} if log.name == "sim.log" and "timeout_seconds" in target else {}
            record["commands"][-1]["timeout_seconds"] = call_options.get("timeout", 60)
            peer = None
            result = None
            try:
                if log.name == "sim.log" and "driver" in target:
                    peer = Peer(root, attempt, target["driver"]["peer"])
                    port = peer.start()
                    if target["driver"].get("preload", False):
                        from .preload import verify
                        verify(attempt)
                    def tcl_path(path):
                        return "{" + path.as_posix().replace("{", "\\{").replace("}", "\\}") + "}"
                    macro = (attempt / "run.do").read_text(encoding="utf-8")
                    macro = macro.replace("run -all", f"set smoke_root {tcl_path(root)}\nset smoke_peer_port {port}\nsource {tcl_path(root / target['driver']['script'])}")
                    (attempt / "run.do").write_text(macro, encoding="utf-8")
                result = simulator.run(argv, cwd=cwd, **call_options)
                log.write_text(result.stdout, encoding="utf-8")
                record["commands"][-1]["exit_code"] = result.returncode
            finally:
                if peer is not None:
                    peer.close(result is not None and result.returncode == 0)
            if (result.returncode == 0) != (expected == "zero"):
                raise RuntimeError(f"unexpected exit {result.returncode}; see {log.relative_to(root)}")
            if log.name == "adc-pll-generate.log":
                record["generated_adc_pll"] = intel_adc.verify_generated(cwd)
            checked_output = result.stdout
            if log.name == "intel-adc-control-compile.log":
                checked_output, record["explained_compile_diagnostics"] = intel_adc.classify_compile_diagnostics(result.stdout, vendor_model, log.name)
            if log.name == "sim.log":
                if vendor_model and vendor_model["selection"] == "intel-adc":
                    checked_output, record["explained_diagnostics"] = intel_adc.classify_sim_diagnostics(result.stdout, vendor_model)
                else:
                    checked_output, record["explained_diagnostics"] = intel_memory.classify_diagnostics(result.stdout, vendor_model)
            problem = diagnostic(checked_output, target["signature"] if expected == "nonzero" else None)
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
