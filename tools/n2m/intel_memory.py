"""Resolve the pinned installed Intel memory model; never synthesize a substitute."""
import json
from pathlib import Path
import re

from .records import file_hash


LIBRARY = "n2m_altera_mf"
MIXED_MODE_MODEL_HASH = "2ae09f97f9606626da216e9eb91007beec3ebbe023c5b9415be472417fe49d5e"


def resolve(root, simulator, target, directory=None):
    selection = target.get("vendor_model")
    if selection is None:
        return None
    if selection != "intel-memory":
        raise ValueError("unsupported vendor model; expected intel-memory")
    pin = json.loads((root / "tools/n2m/dependencies.json").read_text(encoding="utf-8"))["intel_memory"]
    if directory is None:
        # The supported Quartus distribution installs Questa alongside Quartus.
        installation = Path(simulator.tools["vsim"]).resolve().parents[2]
        folder = installation / "quartus/eda/sim_lib"
    else:
        folder = Path(directory).resolve()
    if not folder.is_dir():
        raise ValueError("missing Intel simulation library; select --intel-sim-lib from the supported Quartus installation")
    sources = []
    for name, expected in pin["sources"].items():
        path = folder / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"missing Intel memory model source: {name}")
        actual = file_hash(path)
        if actual != expected:
            raise ValueError(f"unsupported Intel memory model hash: {name}; install the pinned release")
        sources.append({"name": name, "path": str(path), "sha256": actual})
    instances = target.get("intel_mixed_mode_instances", [])
    if (not isinstance(instances, list) or
            any(not isinstance(item, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.$\[\]]*", item) for item in instances) or
            len(set(instances)) != len(instances)):
        raise ValueError("invalid Intel mixed-mode diagnostic instance inventory")
    if instances and not any(source["name"] == "altera_mf.v" and source["sha256"] == MIXED_MODE_MODEL_HASH for source in sources):
        raise ValueError("Intel mixed-mode diagnostic requires the reviewed model source hash")
    return {"selection": selection, "library": LIBRARY, "version": pin["version"],
            "sources": sources, "compile_options": ["-work", LIBRARY],
            "binding_options": ["-L", LIBRARY], "mixed_mode_instances": instances}


def classify_diagnostics(output, descriptor):
    """Record only the pinned model's time-zero mixed-mode coercion pairs."""
    instances = descriptor.get("mixed_mode_instances", []) if descriptor else []
    if not instances:
        return output, []
    if not any(source["name"] == "altera_mf.v" and source["sha256"] == MIXED_MODE_MODEL_HASH
               for source in descriptor["sources"]):
        raise ValueError("Intel mixed-mode diagnostic requires the reviewed model source hash")
    pattern = re.compile(r"^# Warning: read_during_write_mode_mixed_ports is assumed as +OLD_DATA\r?\n"
                         r"# Time: 0 +Instance: ([A-Za-z_][A-Za-z0-9_.$\[\]]*)\r?$", re.MULTILINE)
    matches = list(pattern.finditer(output))
    if sorted(match[1] for match in matches) != sorted(instances):
        raise ValueError("Intel mixed-mode diagnostic count or instance differs")
    evidence = [{"id": "intel-max10-mixed-mode-coercion", "time": 0,
                 "instance": match[1], "raw": match[0], "model_sha256": MIXED_MODE_MODEL_HASH,
                 "reason": "Different-clock mixed-port collisions are forbidden by the memory MAS."}
                for match in matches]
    return pattern.sub("", output), evidence


def reject_shadow_models(root, inputs):
    for name in inputs:
        text = (root / name).read_text(encoding="utf-8")
        text = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", " ", text)
        if re.search(r"\bmodule\s+(?:automatic\s+)?altsyncram(?:_body)?\b", text):
            raise ValueError(f"repository model shadows the installed Intel memory model: {name}")


def commands(simulator, compiler, attempt, descriptor):
    if descriptor is None:
        return [], [], []
    library = descriptor["library"]
    path = (compiler / library).as_posix()
    tools = simulator.tools
    compile_commands = [
        ([tools["vlib"], library], compiler, compiler / "intel-library.log", "zero"),
        ([tools["vmap"], library, path], compiler, compiler / "intel-map.log", "zero"),
        ([tools["vlog"], *descriptor["compile_options"],
          *[source["path"] for source in descriptor["sources"]]],
         compiler, compiler / "intel-compile.log", "zero"),
    ]
    map_commands = [([tools["vmap"], library, path], attempt, attempt / "intel-map.log", "zero")]
    return compile_commands, map_commands, descriptor["binding_options"]
