"""Temporary Quartus installations and accepted-source ledgers for host tests.

A host test never reads a real Quartus installation, so it builds one: the
layout directory [`vendor_sources`](../vendor_sources.py) reads the platform
from, an optional `version.txt`, and its own ledger file. Pointing the ledger at
a temporary path is what keeps a test from reading or writing the tracked one.
"""
import json
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import vendor_sources


def installation(root, platform="linux", release="0.0 host-test"):
    """A Quartus installation tree this platform's layout identifies."""
    root = Path(root)
    for folder in (vendor_sources.LAYOUTS[platform], vendor_sources.EXECUTABLES[platform]):
        (root / folder).mkdir(parents=True, exist_ok=True)
    if release:
        (root / "quartus/version.txt").write_text(f"Version=ignored\n[ACDS]\nVersion={release}\n", encoding="utf-8")
    return root


def ledger(case, path, sources=None, platform="linux", history=()):
    """Point the ledger at `path` for this test, holding `sources` for `platform`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {"schema_version": 1, "purpose": "Host test ledger.", "acceptance": "Host test ledger.",
               "installations": {platform: {"quartus": None, "sources": dict(sources or {}),
                                            "history": list(history)}}}
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    # Tests reach the module as both `n2m.vendor_sources` and
    # `tools.n2m.vendor_sources`, which are separate objects. Every loaded copy is
    # redirected, so no test can read or write the tracked ledger.
    modules = [module for name, module in list(sys.modules.items())
               if name.endswith("n2m.vendor_sources") and module is not None]
    assert modules, "vendor_sources is not imported"
    for module in modules:
        patcher = patch.object(module, "ledger_path", lambda: path)
        patcher.start()
        case.addCleanup(patcher.stop)
    return path


def accepted(path, sha256, source, platform="linux", status=vendor_sources.UNCHANGED):
    """One entry shaped like the record `vendor_sources.check` returns."""
    return {"path": str(path), "sha256": sha256, "source": source,
            "installation": platform, "accepted": status}
