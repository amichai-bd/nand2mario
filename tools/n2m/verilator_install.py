"""The repository's own pinned Verilator: one source build per host, and its discovery.

`tools verilator` builds the pinned tag into the shared host tool cache and
records its provenance. Discovery then finds it without a PATH edit, so a host
needs no operator-installed simulator and no worktree pays the build twice. An
operator-supplied Verilator on PATH still wins: the pinned tree is the fallback,
never a silent override.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import time

from .records import (atomic_json, atomic_text, file_hash, lock_owner, pid_alive,
                      reclaim_stale_lock, release_held_lock, take_lock)

# Relative to the repository root: the per-checkout prefix earlier runs filled.
# It is still discovered and adopted, but nothing new installs there, because a
# worktree's removal after delivery would take the tool with it.
RELATIVE_PREFIX = "workdir/tools/verilator"
# The shared installation lives outside every checkout, so one build serves every
# worktree on the host and post-merge cleanup cannot reach it.
CACHE_VARIABLE = "N2M_TOOL_CACHE"
CACHE_FOLDER = ("nand2mario", "tools")
TOOL_FOLDER = "verilator"
WINDOWS = os.name == "nt"
INSTALLATION = "installation.json"
# One installation at a time per host, because the cache is shared.
INSTALL_LOCK = "install.lock"
# The only installed files a run never reaches. Nothing in this repository passes
# `--debug`, so these two are never executed, and they are 236 MB of the 259 MB
# installed: covering them would add about four seconds to every discovery for a
# tree no simulation touches. Everything else, including the `share/verilator`
# headers compiled into every simulation binary, is covered.
UNCOVERED = ("verilator_bin_dbg", "verilator_coverage_bin_dbg")
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


def cache_root(root, environment=None):
    """Where this host keeps its installed pinned tools, outside every checkout.

    ``N2M_TOOL_CACHE`` wins when it names a path; otherwise the per-user default
    under the platform cache folder. A relative variable is resolved against the
    checkout so a caller cannot land the cache on an unknown path. The location
    is deliberately not inside a checkout: a worktree is removed after delivery
    and would take a 26-minute build with it.
    """
    environment = os.environ if environment is None else environment
    override = (environment.get(CACHE_VARIABLE) or "").strip()
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else Path(root).resolve() / path
    base = (environment.get("XDG_CACHE_HOME") or "").strip()
    if not base and WINDOWS:
        base = (environment.get("LOCALAPPDATA") or "").strip()
    base = (Path(base).expanduser() if base
            else Path(environment.get("HOME") or Path.home()).expanduser() / ".cache")
    return base.joinpath(*CACHE_FOLDER)


def prefix(root, version):
    return cache_root(root) / TOOL_FOLDER / ("v" + version)


def source_root(root, version):
    return cache_root(root) / TOOL_FOLDER / ("v" + version + ".source")


def legacy_prefix(root, version):
    return Path(root) / RELATIVE_PREFIX / ("v" + version)


def legacy_source_root(root, version):
    return Path(root) / RELATIVE_PREFIX / ("v" + version + ".source")


def pinned_release(root=None):
    """The release this repository pins, or None when the pin cannot be read."""
    try:
        return pin(Path(root or repository_root()))["version"]
    except (OSError, TypeError, ValueError, KeyError):
        return None


def covered_files(base):
    """Every installed file a simulation can execute or compile against, in order."""
    base = Path(base)
    return [path for path in sorted(base.rglob("*"))
            if path.is_file() and path.name != INSTALLATION and path.name not in UNCOVERED]


def tree_digests(base):
    """The covered installation as {path relative to the prefix: sha256}."""
    base = Path(base)
    return {path.relative_to(base).as_posix(): file_hash(path) for path in covered_files(base)}


def verify_installation(base, item):
    """Prove a tree is this pin's build and return its record; a path is never trust.

    A shared cache, an operator-set `N2M_TOOL_CACHE` and an adopted per-checkout
    tree all arrive as a directory that claims to hold the pin. The record beside
    it must name this pin's version, tag and commit, and every covered installed
    file must still hash to what it recorded, so a stale, foreign or damaged tree
    is refused by name rather than silently simulated with.

    The check covers the whole installation apart from `UNCOVERED`, not only the
    executables: `share/verilator/include` is compiled into every simulation
    binary, so a tampered header there changes what runs exactly as a tampered
    compiler would. A covered file that is missing, changed or not in the record
    at all is refused; `tools` is checked as well, so a record whose two views of
    the same executables disagree is refused rather than half-believed.
    """
    base = Path(base)
    record_path = base / INSTALLATION
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"unreadable Verilator provenance record: {record_path}: {error}") from error
    recorded = record.get("pin") if isinstance(record, dict) else None
    recorded = recorded if isinstance(recorded, dict) else {}
    for field in ("version", "tag", "commit"):
        if recorded.get(field) != item[field]:
            raise ValueError(f"installed Verilator was built from a different pin: {base}: "
                             f"{field} {recorded.get(field)!r} is not {item[field]!r}")
    tools = record.get("tools")
    tools = tools if isinstance(tools, dict) else {}
    if "verilator" not in tools:
        raise ValueError(f"Verilator provenance record names no installed tool hash: {record_path}")
    for name, digest in sorted(tools.items()):
        tool = base / "bin" / name
        if not tool.is_file():
            raise ValueError(f"installed Verilator is missing {name}: {base}")
        if file_hash(tool) != digest:
            raise ValueError(f"installed Verilator {name} does not match its provenance record: {base}")
    tree = record.get("tree")
    if not isinstance(tree, dict) or not tree:
        raise ValueError(f"Verilator provenance record covers no installed tree: {record_path}; "
                         "reinstall with `python3 tools/build.py tools verilator`")
    found = tree_digests(base)
    for path in sorted(set(tree) | set(found)):
        if path not in found:
            raise ValueError(f"installed Verilator is missing {path}: {base}")
        if path not in tree:
            raise ValueError(f"installed Verilator carries the unrecorded file {path}: {base}")
        if found[path] != tree[path]:
            raise ValueError(f"installed Verilator {path} does not match its provenance record: {base}")
    return record


def adoptable_prefix(root, item, base):
    """True while a per-checkout installation could still be published."""
    legacy = legacy_prefix(root, item["version"])
    base = Path(base)
    return (not base.exists() and legacy.resolve() != base.resolve()
            and (legacy / "bin/verilator").is_file())


def adoptable_source(root, item):
    """True while a per-checkout clone could still be published."""
    source, legacy = source_root(root, item["version"]), legacy_source_root(root, item["version"])
    return (not source.exists() and legacy.resolve() != source.resolve()
            and (legacy / ".git").is_dir())


def adopt_prefix(root, item, base):
    """Publish a verified per-checkout installation into the shared host cache.

    An earlier run that installed into a checkout keeps its value: the tree is
    verified against the pin before it moves and again where it lands. The
    installed `bin/verilator` resolves its own root relative to its directory, so
    the prefix relocates without a rebuild; only the record's own `prefix` is
    restated. A tree that fails the check is left alone for the caller to
    inspect, never overwritten or silently rebuilt over.
    """
    if not adoptable_prefix(root, item, base):
        return False
    legacy, base = legacy_prefix(root, item["version"]), Path(base)
    verify_installation(legacy, item)
    base.parent.mkdir(parents=True, exist_ok=True)
    staged = base.with_name(base.name + ".adopting")
    if staged.exists():
        shutil.rmtree(staged)
    shutil.move(str(legacy), str(staged))
    record = json.loads((staged / INSTALLATION).read_text(encoding="utf-8"))
    record.update(prefix=str(base), adopted_from=str(legacy))
    atomic_json(staged / INSTALLATION, record)
    os.replace(staged, base)
    verify_installation(base, item)
    return True


def adopt_source(root, item):
    """Publish a per-checkout clone into the shared cache, independently of the prefix.

    The clone is what `--offline` rebuilds from, so it must outlive the worktree
    that fetched it. It is adopted even when the cache already holds the
    installation, which is the ordinary case: the two are separate directories
    with separate lifetimes, and tying the clone's rescue to the prefix's would
    lose it exactly when the prefix is already safe.

    A clone is never a trusted build input: `install` holds its `HEAD` against the
    pinned commit and refuses by name before `autoconf` runs, wherever the clone
    came from. That one gate covers an adopted clone as it covers a fetched one,
    so adoption does not re-run it here.
    """
    if not adoptable_source(root, item):
        return False
    source, legacy = source_root(root, item["version"]), legacy_source_root(root, item["version"])
    source.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy), str(source))
    return True


def adopt(root, item, base):
    """Publish whichever per-checkout trees the cache does not already hold."""
    return {"prefix": adopt_prefix(root, item, base), "source": adopt_source(root, item)}


@contextlib.contextmanager
def cache_lock(base):
    """Hold the cache's install lock so two worktrees never build into one prefix.

    The cache is shared, so a second `tools verilator` would otherwise clone and
    `make` into the same source tree as a running one. Reuse never takes the lock,
    so a discovery is never blocked by another worktree's build.

    A held lock follows the tag lock's rule exactly: a lock whose recorded writer
    is dead is the leftover of a killed process, reclaimed once out loud; a live
    or unreadable owner keeps the cache and nothing steals by age. Unreadable
    counts as live, so the failure never advises removing the lock of a running
    26-minute build, and the empty window between the exclusive create and the pid
    write cannot be mistaken for an abandoned one.
    """
    lock = Path(base).parent / INSTALL_LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = take_lock(lock)
    except FileExistsError:
        owner = lock_owner(lock)
        if owner is None or pid_alive(owner):
            raise ValueError(f"the pinned Verilator cache {lock.parent} is being installed into"
                             + (f" by live pid {owner}" if owner else "")
                             + f"; confirm its writer stopped before removing {lock}") from None
        reclaim_stale_lock(lock, owner)
        try:
            fd = take_lock(lock)
        except FileExistsError:
            raise ValueError(f"the pinned Verilator cache {lock.parent} was taken by another "
                             f"installer while its stale lock {lock} was reclaimed") from None
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode())
        yield
    finally:
        release_held_lock(fd, lock)


def installed(root=None, *, version=None):
    """The pinned installation's bin directory, or None when it is not installed.

    The shared host cache is searched first, then the per-checkout prefix an
    earlier run may have filled, so a worktree that already holds a build keeps
    working. An installation counts only with its provenance record beside it, so
    a partially removed or half-written tree is never discovered, and the record
    must still match the pin, so a tree from another version is reported rather
    than used.
    """
    root = Path(root or repository_root())
    try:
        item = pin(root)
        version = version or item["version"]
    except (OSError, ValueError, KeyError):
        return None
    for base in (prefix(root, version), legacy_prefix(root, version)):
        if (base / "bin/verilator").is_file() and (base / INSTALLATION).is_file():
            verify_installation(base, item)
            return base / "bin"
    return None


def discovery_note(root=None):
    """The hint a missing-Verilator failure carries; never a fallback of its own.

    It states the whole remedy once, so a caller prefixes it rather than
    repeating either half. The build is kept per host, so the remedy is paid once
    on this machine rather than once per worktree.
    """
    del root
    return ("install the repository-pinned Verilator with "
            "`python3 tools/build.py tools verilator` or select its tool directory explicitly")


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
    # Validate before folding in a default: `--jobs 0` and `--timeout 0` are
    # refused by name rather than silently becoming the host CPU count and
    # STEP_TIMEOUT, which is what a guard placed after the fold would allow.
    if jobs is not None and jobs < 1:
        raise ValueError(f"--jobs must be at least 1, not {jobs}")
    if timeout is not None and timeout < 1:
        raise ValueError(f"--timeout must be at least 1 second, not {timeout}")
    version, tag, commit = item["version"], item["tag"], item["commit"]
    # `environ` is the build child's environment, not this host's: the cache is
    # resolved from the process environment so a stripped child environment can
    # never redirect the installation.
    base, source = prefix(root, version), source_root(root, version)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    env = build_environment(environ)
    record = {"pin": item, "prefix": str(base), "source": str(source),
              "cache_root": str(cache_root(root)),
              "adopted": {"prefix": False, "source": False},
              "reused": False, "commands": []}

    def step(name, argv, cwd, step_timeout=None):
        record["commands"].append([str(part) for part in argv])
        return run(argv, cwd, folder / (name + ".log"), step_timeout or timeout, env)

    tool = base / "bin/verilator"

    def reuse():
        """The installed prefix's record and banner, or None when it is absent."""
        if not (tool.is_file() and (base / INSTALLATION).is_file()):
            return None
        installation = verify_installation(base, item)
        banner = step("reused-version", [tool, "--version"], folder, 60).strip()
        if banner_version(banner) != version:
            raise ValueError(f"installed Verilator is {banner!r}, expected {version}: {base}")
        record.update(reused=True, version=banner, installation=installation)
        return record

    def adopt_or_build():
        """Everything that writes the shared cache; the caller holds its lock."""
        record["adopted"].update(adopt(root, item, base))
        # A concurrent installation may have finished between the unlocked reuse
        # check and this lock, so the check runs once more before any build.
        if reuse() is not None:
            return record
        tools = prerequisites(which)
        record["build_tools"] = tools
        if not (source / ".git").is_dir():
            if offline:
                raise ValueError(f"offline: the pinned Verilator source is not present at {source}")
            source.parent.mkdir(parents=True, exist_ok=True)
            # The pinned tag is annotated, so a shallow clone reports
            # "warning: refs/tags/<tag> <sha> is not a commit!": the tag object is
            # fetched, its target commit is not a ref. It is upstream git describing
            # the tag object, not a defect. The `rev-parse HEAD` below is what the
            # pin is checked against, so a wrong tree still fails here.
            step("clone", [tools["git"], "clone", "--depth", "1", "--branch", tag, item["url"], source],
                 source.parent)
        resolved = step("commit", [tools["git"], "-C", source, "rev-parse", "HEAD"], folder, 60).strip()
        if resolved != commit:
            raise ValueError(f"pinned Verilator commit mismatch: {resolved} != {commit}")
        record["commit"] = resolved
        parallel = jobs or os.cpu_count() or 1
        record["jobs"] = parallel
        started = time.monotonic()
        step("autoconf", [tools["autoconf"]], source)
        step("configure", [source / "configure", "--prefix", base], source)
        step("make", [tools["make"], "-j", str(parallel)], source)
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
                      "tree": tree_digests(base), "uncovered": list(UNCOVERED),
                      "build_tools": {name: _tool_identity(path) for name, path in tools.items()},
                      "host": platform.platform(), "python": platform.python_version(),
                      "jobs": parallel, "elapsed_seconds": record["elapsed_seconds"],
                      "local_changes": "none",
                      "redistribution": "No Verilator source or binary is committed; the build "
                                        "stays in the shared host tool cache outside every checkout"}
        atomic_json(base / INSTALLATION, provenance)
        record["installation"] = provenance
        return record

    # An installed prefix is reused without the lock, so one worktree's discovery
    # never waits on another's 26-minute build. Everything that writes the shared
    # cache runs inside it, including the one write a reuse still owes: a clone
    # this checkout holds and the cache does not. Skipping that write because the
    # installation was already cached is what would leave the clone to die with
    # the worktree, and with it `--offline` as a property of this host.
    if reuse() is not None:
        if adoptable_source(root, item):
            with cache_lock(base):
                record["adopted"]["source"] = adopt_source(root, item)
        return record
    with cache_lock(base):
        return adopt_or_build()


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
        # `or STEP_TIMEOUT` would turn `--timeout 0` into the default; the
        # install guard is what refuses it, so pass the caller's value through.
        timeout = STEP_TIMEOUT if args.timeout is None else args.timeout
        record = install(root, folder, item, jobs=args.jobs,
                         timeout=timeout, offline=args.offline)
        report.update(status="PASS", **record)
        report["discovered"] = str(installed(root, version=item["version"]) or "")
    except Exception as error:
        report["error"] = str(error)
    report["artifacts"] = {path.relative_to(root).as_posix(): file_hash(path)
                           for path in sorted(folder.rglob("*"))
                           if path.is_file() and path.name != "result.json"}
    atomic_json(folder / "result.json", report)
    return report
