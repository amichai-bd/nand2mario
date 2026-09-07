"""Stage a manifest-verified historical DUT with the current Python diagnostic.

This is a temporary build input tree, never a maintained source mirror. It does
not execute the historical Tcl driver, peer or SV testbench.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage(root, snapshot, destination):
    root, snapshot, destination = root.resolve(), snapshot.resolve(), destination.resolve()
    if not destination.is_relative_to(root / "workdir/builds") or destination.exists():
        raise ValueError("destination must be a new directory under this worktree's workdir/builds")
    manifest = json.loads((snapshot / "snapshot.json").read_text())
    for name, digest in manifest["files"].items():
        path = (snapshot / name).resolve()
        if not path.is_relative_to(snapshot) or not path.is_file() or sha(path) != digest:
            raise ValueError(f"historical snapshot identity mismatch: {name}")
    # Include uncommitted new diagnostic files during development; never copy
    # ignored output, .git, credentials, or unrelated user files.
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    names += [p.relative_to(root).as_posix() for p in (root / "src/dv/python/integration").glob("*") if p.is_file()]
    for name in sorted(set(names) - {""}):
        source = root / name
        if source.is_file():
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    overrides = {}
    for name in manifest["files"]:
        if name.startswith("src/rtl/") or name == "src/dv/integration/n2m_smoke_system.sv":
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snapshot / name, target)
            overrides[name] = sha(target)
    record = {"kind": "historical-dut-independent-python-tb", "snapshot_sha256": sha(snapshot / "snapshot.json"),
              "snapshot_base": manifest["base_commit"], "snapshot_preload": manifest["preload_commit"],
              "python_author_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
              "historical_inputs": overrides,
              "note": "Only RTL and composition are historical. Builder, Python stimulus/checker and HDL observation wrapper are current."}
    identity = "src/dv/python/integration/historical-identity.json"
    (destination / identity).write_text(json.dumps(record, indent=2) + "\n")
    registry = destination / "src/dv/builder/targets.json"
    targets = json.loads(registry.read_text())
    for name in ("python-integration", "python-integration-fault"):
        targets[name]["python"]["inputs"].append(identity)
    registry.write_text(json.dumps(targets, indent=2) + "\n")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    result = stage(Path(__file__).resolve().parents[4], args.snapshot, args.destination)
    print(json.dumps(result, indent=2))
