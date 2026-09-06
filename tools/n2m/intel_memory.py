"""Resolve the pinned installed Intel memory model; never synthesize a substitute."""
import json
from pathlib import Path
import re

from .records import file_hash


LIBRARY = "n2m_altera_mf"


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
    return {"selection": selection, "library": LIBRARY, "version": pin["version"],
            "sources": sources, "compile_options": ["-work", LIBRARY],
            "binding_options": ["-L", LIBRARY]}


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
