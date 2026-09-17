"""The repository's own pinned Verilator: source build under workdir/tools, and its discovery.

`tools verilator` builds the pinned tag into `workdir/tools/verilator/v<version>`
and records its provenance. Discovery then finds it without a PATH edit, so a
host needs no operator-installed simulator. An operator-supplied Verilator on
PATH still wins: the pinned tree is the fallback, never a silent override.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

from .records import atomic_json, atomic_text, file_hash

# Relative to the repository root, outside workdir/builds so `clean --tag`
# never removes an installed tool and no tag rebuilds one.
RELATIVE_PREFIX = "workdir/tools/verilator"
INSTALLATION = "installation.json"
# The official git-build prerequisites this installation needs on PATH.
BUILD_TOOLS = ("git", "autoconf", "make", "g++", "flex", "bison", "perl", "help2man")
# Verilator's own root must come from the built tree, never from the caller.
REMOVED_VARIABLES = ("VERILATOR_ROOT", "VERILATOR_BIN")
STEP_TIMEOUT = 3600


def repository_root():
    return Path(__file__).resolve().parents[2]


def pin(root):
    """The dependencies.json Verilator pin: version, tag, commit, url and license."""
    text = (Path(root) / "tools/n2m/dependencies.json").read_text(encoding="utf-8")
    return json.loads(text)["verilator"]


def prefix(root, version):
    return Path(root) / RELATIVE_PREFIX / ("v" + version)


def source_root(root, version):
    return Path(root) / RELATIVE_PREFIX / ("v" + version + ".source")


def installed(root=None, *, version=None):
    """The pinned installation's bin directory, or None when it is not installed.

    An installation counts only with its provenance record beside it, so a
    partially removed or half-written tree is never discovered.
    """
    root = Path(root or repository_root())
    try:
        version = version or pin(root)["version"]
    except (OSError, ValueError, KeyError):
        return None
    base = prefix(root, version)
    if (base / "bin/verilator").is_file() and (base / INSTALLATION).is_file():
        return base / "bin"
    return None


def discovery_note(root=None):
    """The hint a missing-Verilator failure carries; never a fallback of its own."""
    del root
    return ("install the repository-pinned Verilator with "
            "`python tools/build.py tools verilator` or select its tool directory explicitly")


def build_environment(environ=None):
    """The child environment: the caller's, without Verilator's own root variables."""
    return {k: v for k, v in (environ or os.environ).items() if k not in REMOVED_VARIABLES}


def _run(argv, cwd, log_path, timeout, env):
    """Run one argv without a shell and retain its whole transcript."""
    try:
        result = subprocess.run([str(part) for part in argv], cwd=str(cwd), env=env, text=True,
                                encoding="utf-8", errors="replace", stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=timeout)
        output = result.stdout
        code = result.returncode
    except (OSError, subprocess.TimeoutExpired) as error:
        output = getattr(error, "stdout", "") or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        atomic_text(Path(log_path), output + "\n" + str(error) + "\n")
        raise ValueError(f"{Path(log_path).stem} failed: {error}") from error
    atomic_text(Path(log_path), output)
    if code:
        raise ValueError(f"{Path(log_path).stem} exited {code}; see {Path(log_path).name}")
    return output


def prerequisites(which=None):
    """Return the resolved build prerequisites; a missing one is named, not guessed."""
    which = which or shutil.which
    found = {}
    for name in BUILD_TOOLS:
        path = which(name)
        if not path:
            raise ValueError(f"missing Verilator build prerequisite: {name}; "
                             "install the upstream git-build prerequisites and retry")
        found[name] = str(Path(path).resolve())
    return found


def banner_version(text):
    """The release from a `Verilator <release> <date> rev <tag>` banner."""
    match = re.match(r"Verilator (\d+\.\d+)\b", text.strip())
    return match[1] if match else None


def install(root, folder, item, *, jobs=None, timeout=STEP_TIMEOUT, offline=False,
            run=_run, which=None, environ=None):
    """Build and install the pinned Verilator tag into workdir/tools; return the record.

    Every step keeps its transcript under `folder`. An existing installation
    whose banner matches the pin is reused; nothing is rebuilt or overwritten.
    """
    version, tag, commit = item["version"], item["tag"], item["commit"]
    base, source = prefix(root, version), source_root(root, version)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    env = build_environment(environ)
    record = {"pin": item, "prefix": str(base), "source": str(source),
              "reused": False, "commands": []}

    def step(name, argv, cwd, step_timeout=None):
        record["commands"].append([str(part) for part in argv])
        return run(argv, cwd, folder / (name + ".log"), step_timeout or timeout, env)

    tool = base / "bin/verilator"
    if tool.is_file() and (base / INSTALLATION).is_file():
        banner = step("reused-version", [tool, "--version"], folder, 60).strip()
        if banner_version(banner) != version:
            raise ValueError(f"installed Verilator is {banner!r}, expected {version}: {base}")
        record.update(reused=True, version=banner,
                      installation=json.loads((base / INSTALLATION).read_text(encoding="utf-8")))
        return record

    tools = prerequisites(which)
    record["build_tools"] = tools
    if not (source / ".git").is_dir():
        if offline:
            raise ValueError(f"offline: the pinned Verilator source is not present at {source}")
        source.parent.mkdir(parents=True, exist_ok=True)
        step("clone", [tools["git"], "clone", "--depth", "1", "--branch", tag, item["url"], source],
             source.parent)
    resolved = step("commit", [tools["git"], "-C", source, "rev-parse", "HEAD"], folder, 60).strip()
    if resolved != commit:
        raise ValueError(f"pinned Verilator commit mismatch: {resolved} != {commit}")
    record["commit"] = resolved
    jobs = jobs or os.cpu_count() or 1
    if jobs < 1:
        raise ValueError("--jobs must be at least 1")
    record["jobs"] = jobs
    started = time.monotonic()
    step("autoconf", [tools["autoconf"]], source)
    step("configure", [source / "configure", "--prefix", base], source)
    step("make", [tools["make"], "-j", str(jobs)], source)
    step("install", [tools["make"], "install"], source)
    record["elapsed_seconds"] = round(time.monotonic() - started, 3)
    banner = step("version", [tool, "--version"], folder, 60).strip()
    if banner_version(banner) != version:
        raise ValueError(f"installed Verilator is {banner!r}, expected {version}")
    record["version"] = banner
    provenance = {"kind": "unmodified upstream source build", "pin": item, "commit": resolved,
                  "version": banner, "prefix": str(base),
                  "tools": {name: file_hash(base / "bin" / name)
                            for name in ("verilator", "verilator_bin")
                            if (base / "bin" / name).is_file()},
                  "build_tools": {name: _tool_identity(path) for name, path in tools.items()},
                  "host": platform.platform(), "python": platform.python_version(),
                  "jobs": jobs, "elapsed_seconds": record["elapsed_seconds"],
                  "local_changes": "none",
                  "redistribution": "No Verilator source or binary is committed; the build stays "
                                    "under the ignored workdir/tools prefix"}
    atomic_json(base / INSTALLATION, provenance)
    record["installation"] = provenance
    return record


def _tool_identity(path):
    try:
        return {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    except OSError:
        return {"path": path}


def command(root, build, args, provenance):
    """`tools verilator`: install the pin, then report where discovery will find it."""
    folder = build / "tools/verilator"
    folder.mkdir(parents=True, exist_ok=True)
    item = pin(root)
    report = {"status": "FAIL", **provenance,
              "scope": "pinned Verilator installation only; no simulation was run"}
    try:
        record = install(root, folder, item, jobs=args.jobs,
                         timeout=args.timeout or STEP_TIMEOUT, offline=args.offline)
        report.update(status="PASS", **record)
        report["discovered"] = str(installed(root, version=item["version"]) or "")
    except Exception as error:
        report["error"] = str(error)
    report["artifacts"] = {path.relative_to(root).as_posix(): file_hash(path)
                           for path in sorted(folder.rglob("*"))
                           if path.is_file() and path.name != "result.json"}
    atomic_json(folder / "result.json", report)
    return report
