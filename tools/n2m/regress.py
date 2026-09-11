"""Declared regression subsets under one tag, and cleanup of one tag."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
import time

from .records import atomic_json, atomic_text, file_hash, valid_tag, workspace
from .simulation import load_target
from .test_budget import supervise, target_selection

# Verification tiers of wiki/src/dv/integration/SPEC.md#verification-tiers.
TIERS = ("ordinary", "transport", "milestone")
# AGENTS.md: the ordinary pre-merge aggregate guidance. A subset above it is a
# broader declared aggregate and needs --broader on the command line.
ORDINARY_BUDGET = 300
# A child needs its 12 reserved cleanup seconds plus at least one to run.
MINIMUM_CHILD_SECONDS = 13
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")


def load_subsets(root):
    """Return (subsets, registry path); every declared subset is validated."""
    registry = root / "src/dv/builder/regressions.json"
    plan = json.loads(registry.read_text(encoding="utf-8"))
    if (not isinstance(plan, dict) or set(plan) != {"version", "subsets"} or plan["version"] != 1
            or not isinstance(plan["subsets"], dict) or not plan["subsets"]):
        raise ValueError("regression subsets require version 1 and a nonempty subsets object")
    targets = json.loads((root / "src/dv/builder/targets.json").read_text(encoding="utf-8"))
    for name, subset in plan["subsets"].items():
        if not NAME.fullmatch(name):
            raise ValueError(f"invalid regression subset name: {name}")
        if not isinstance(subset, dict) or set(subset) != {"tier", "purpose", "budget_seconds", "targets"}:
            raise ValueError(f"subset {name} requires exactly tier, purpose, budget_seconds and targets")
        if subset["tier"] not in TIERS:
            raise ValueError(f"subset {name} tier must be one of {', '.join(TIERS)}")
        if not isinstance(subset["purpose"], str) or not subset["purpose"].strip():
            raise ValueError(f"subset {name} requires a purpose")
        members = subset["targets"]
        if (not isinstance(members, list) or not members or len(set(members)) != len(members)
                or any(not isinstance(member, str) or member not in targets for member in members)):
            raise ValueError(f"subset {name} targets must be distinct registered target names")
        # The most any member may consume; a budget above it declares nothing.
        ceiling = sum(target_selection(member, targets[member])[0] for member in members)
        budget = subset["budget_seconds"]
        if type(budget) is not int or not 1 <= budget <= ceiling:
            raise ValueError(f"subset {name} budget_seconds must be an integer in 1..{ceiling}")
        if subset["tier"] == "ordinary" and budget > ORDINARY_BUDGET:
            raise ValueError(f"subset {name} is ordinary and cannot exceed {ORDINARY_BUDGET} seconds")
    return plan["subsets"], registry


def child_command(root, tag, target, args):
    # The worker entry, as test_budget.main launches it: the regression's own
    # supervise call is the one wall budget, not a second nested supervisor.
    command = [sys.executable, str(root / "tools/n2m/test_budget.py"), "sim", "test", target,
               "--tag", tag, "--seed", str(args.seed), "--json"]
    if args.rebuild:
        command.append("--rebuild")
    for option in ("questa_bin", "intel_sim_lib"):
        if getattr(args, option, None):
            command += ["--" + option.replace("_", "-"), getattr(args, option)]
    return command


def run_target(root, tag, target, args, remaining):
    """Run one member as the sim-test worker under its own wall budget,
    capped by the aggregate seconds that remain."""
    command = child_command(root, tag, target, args)
    started = time.monotonic()
    code, text = supervise(command, root, tag, target=target, ceiling=math.floor(remaining))
    outcome = {"command": command, "exit_code": code, "elapsed_seconds": time.monotonic() - started}
    lines = [line for line in text.splitlines() if line.strip()]
    try:
        child = json.loads(lines[-1]) if lines else {}
        if not isinstance(child, dict):
            raise ValueError
    except ValueError:
        child = {"status": "FAIL", "error": "child result is not a JSON object"}
    for key in ("cache", "error"):
        if key in child:
            outcome[key] = child[key]
    outcome["status"] = "PASS" if code == 0 and child.get("status") == "PASS" else "FAIL"
    if outcome["status"] == "FAIL" and "error" not in outcome:
        outcome["error"] = f"child exit {code} with status {child.get('status')}"
    # Only the supervisor's own wall-budget result carries cleanup_complete.
    # A killed child never ran its finally, so the tag lock it held is a
    # leftover of a dead process tree: remove it so later members and the
    # aggregate publish can take the tag. An incomplete cleanup leaves it.
    if child.get("cleanup_complete") is True:
        lock = root / "workdir/builds" / tag / ".lock"
        if lock.is_file():
            lock.unlink()
            outcome["stale_lock_removed"] = True
    result = root / "workdir/builds" / tag / "sim/test" / target / "result.json"
    if result.is_file():
        outcome["result"] = result.relative_to(root).as_posix()
    return outcome


def run_subset(root, build, args, provenance):
    subsets, registry = load_subsets(root)
    if args.subset not in subsets:
        raise ValueError(f"unknown regression subset: {args.subset}")
    subset = subsets[args.subset]
    budget = subset["budget_seconds"]
    if budget > ORDINARY_BUDGET and not args.broader:
        raise ValueError(f"subset {args.subset} declares {budget} seconds, above the ordinary "
                         f"{ORDINARY_BUDGET}-second pre-merge aggregate; pass --broader to run it as a declared broader aggregate")
    # Fail before any simulator time is spent when one member cannot run.
    for member in subset["targets"]:
        load_target(root, member)
    record = {"subset": args.subset, "tier": subset["tier"], "purpose": subset["purpose"],
              "budget_seconds": budget, "broader": bool(args.broader),
              "subsets": {"path": registry.relative_to(root).as_posix(), "sha256": file_hash(registry)},
              "seed": args.seed, "targets": {}, "failed": [], "provenance": provenance or {},
              "started": datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    for member in subset["targets"]:
        remaining = budget - (time.monotonic() - started)
        if remaining < MINIMUM_CHILD_SECONDS:
            record["targets"][member] = {"status": "SKIPPED", "error": "aggregate budget exhausted before start"}
        else:
            record["targets"][member] = run_target(root, build.name, member, args, remaining)
        if record["targets"][member]["status"] != "PASS":
            record["failed"].append(member)
    record["elapsed_seconds"] = time.monotonic() - started
    record["finished"] = datetime.now(timezone.utc).isoformat()
    if record["failed"]:
        named = ", ".join(f"{member} {record['targets'][member]['status']}" for member in record["failed"])
        record.update(status="FAIL", error=f"regression {args.subset} failed: {named}")
    elif record["elapsed_seconds"] > budget:
        record.update(status="FAIL", error=f"regression {args.subset} exceeded its {budget}-second aggregate budget")
    else:
        record["status"] = "PASS"
    return record


def regress(root, args, header, publish):
    """Run a declared subset. Members run as ordinary tagged sim tests, so the
    tag lock is held per child; a regress guard keeps one regression per tag."""
    with workspace(root, args.tag) as build:
        report = {**header(build.name), "status": "RUNNING"}
        atomic_json(build / "status.json", {"status": "RUNNING"})
        atomic_json(build / "manifest.json", report)
    guard = build / "sim/regress/.lock"
    guard.parent.mkdir(parents=True, exist_ok=True)
    # A passing child moves latest.txt as any sim test does; only an aggregate
    # PASS may leave it on this tag.
    latest = root / "workdir/latest.txt"
    previous = latest.read_text(encoding="utf-8") if latest.is_file() else None
    try:
        try:
            os.close(os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise ValueError(f"regression on tag {build.name} is locked; confirm its runner stopped before removing {guard}")
        try:
            provenance = {k: report[k] for k in ("commit", "dirty_tree_fingerprint", "host", "python") if k in report}
            report.update(run_subset(root, build, args, provenance))
            summary = build / "sim/regress/summary.json"
            atomic_json(summary, report)
            report["summary"] = summary.relative_to(root).as_posix()
        finally:
            guard.unlink()
            if report.get("status") != "PASS":
                if previous is None:
                    latest.unlink(missing_ok=True)
                else:
                    atomic_text(latest, previous)
    except Exception as error:
        report.update(status="FAIL", error=str(error))
    try:
        with workspace(root, build.name) as build:
            publish(build, report)
    except ValueError as error:
        # A child whose cleanup did not complete may still hold the tag, so
        # nothing is published; the aggregate itself is still reported.
        report.update(status="FAIL", error=f"{report.get('error', 'aggregate not published')}; {error}")
    return report


def clean(root, tag):
    """Remove exactly workdir/builds/<tag>; anything else is refused."""
    if not isinstance(tag, str) or not valid_tag(tag):
        raise ValueError("clean requires one valid build tag")
    builds = root / "workdir/builds"
    build = builds / tag
    if build.is_symlink() or build.is_junction():
        raise ValueError(f"tag {tag} is a link; refusing to clean through it")
    if not build.is_dir():
        raise ValueError(f"no build tag {tag}")
    if build.resolve().parent != builds.resolve():
        raise ValueError("tag path escapes workdir/builds")
    if (build / ".lock").exists() or (build / "sim/regress/.lock").exists():
        raise ValueError(f"tag {tag} is locked; confirm its writer stopped before cleaning")
    files, size = own_files(build)
    # rmtree removes links and junctions themselves, never their targets.
    shutil.rmtree(build)
    latest = root / "workdir/latest.txt"
    cleared = latest.is_file() and latest.read_text(encoding="utf-8").strip() == tag
    if cleared:
        latest.unlink()
    return {"status": "PASS", "removed": build.relative_to(root).as_posix(),
            "files": files, "bytes": size, "latest_cleared": cleared}


def own_files(build):
    """Count and size the files rmtree will delete: links and junctions are
    removed as entries, never entered, so nothing behind them is counted."""
    count, size = 0, 0
    pending = [build]
    while pending:
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if entry.is_symlink() or Path(entry.path).is_junction():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    count += 1
                    size += entry.stat(follow_symlinks=False).st_size
    return count, size
