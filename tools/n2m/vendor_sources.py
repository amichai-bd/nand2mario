"""Accepted digests of the installed vendor sources, kept per installation.

Recording a vendor file's digest is provenance: it says which bytes produced a
result. Comparing that digest with one fixed constant is a pin: it ties the
project to one vendor installation. This repository spent the same numbers on
both jobs, so a second legitimate Quartus installation was refused for shipping
different bytes while the provenance it recorded was never in doubt.

This module keeps the provenance and drops the pin. Every build hashes the
installed vendor sources it reads and compares them with the digests this
installation's platform has accepted in [the ledger](accepted_vendor_sources.json):

- absent: this platform has never recorded that source. The build writes the
  digest into the ledger, marks the entry `recorded` rather than `unchanged`,
  and names it in a notice. The new line is a working-tree change, so the first
  sighting is reviewed like any other source change instead of passing as if it
  had been checked.
- equal: unchanged since it was accepted. The entry is `unchanged`.
- different: a vendor file changed under our evidence. The build refuses and
  names the source, the platform, the accepted digest and the installed one.

A build may only add a source the ledger does not hold. It never replaces a
digest the ledger already holds: [`vendor accept`](cli.py) does that, it requires
a reason, and it leaves the old and new digests in the entry's history. That is
what keeps the record from being rewritten by the builds it guards.

Licence, redistribution terms, purpose and the originating installation of each
vendor source stay in [dependencies.json](dependencies.json). This file holds
only the digests each installation has been accepted with.
"""
from datetime import date
import json
from pathlib import Path
import re

from .records import atomic_json, file_hash

LEDGER = "accepted_vendor_sources.json"
SPEC = "wiki/tools/n2m/SPEC.md#accepted-vendor-sources"
# The one layout fact that tells the two installations apart, so the platform is
# read from the tree being hashed and no host setting can disagree with it.
# Quartus keeps its 64-bit executables in quartus/bin64 on Windows and ships
# quartus/linux64 beside the launcher scripts on Linux.
LAYOUTS = {"windows": "quartus/bin64", "linux": "quartus/linux64"}
# The executables directory each platform's builds pass as --quartus-bin.
EXECUTABLES = {"windows": "quartus/bin64", "linux": "quartus/bin"}
RECORDED = "recorded"
UNCHANGED = "unchanged"
STATUSES = (RECORDED, UNCHANGED)
DIGEST = re.compile(r"[0-9a-f]{64}")
# A reason short enough to be a placeholder is not a review record.
REASON_LENGTH = 20


def ledger_path():
    """The tracked ledger, beside this module. Tests point this at their own copy."""
    return Path(__file__).resolve().parent / LEDGER


def load():
    """The ledger, checked. An unreadable or unsupported ledger fails the build."""
    path = ledger_path()
    if not path.is_file():
        raise ValueError(f"missing accepted vendor source ledger: {path.as_posix()}; see {SPEC}")
    return validate(json.loads(path.read_text(encoding="utf-8")))


def validate(ledger):
    """The one schema check, run on every read and before every write."""
    if (not isinstance(ledger, dict) or set(ledger) != {"schema_version", "purpose", "acceptance", "installations"}
            or ledger["schema_version"] != 1 or not isinstance(ledger["installations"], dict)
            or any(not isinstance(ledger[field], str) or not ledger[field] for field in ("purpose", "acceptance"))):
        raise ValueError("unsupported accepted vendor source ledger schema")
    for name, entry in ledger["installations"].items():
        if (name not in LAYOUTS or not isinstance(entry, dict)
                or not {"quartus", "sources", "history"}.issubset(entry)
                or set(entry) - {"quartus", "note", "sources", "history"}
                or not (entry["quartus"] is None or isinstance(entry["quartus"], str) and entry["quartus"])
                or not isinstance(entry["sources"], dict) or not isinstance(entry["history"], list)
                or any(not _relative_name(key) or not DIGEST.fullmatch(str(value))
                       for key, value in entry["sources"].items())):
            raise ValueError(f"unsupported accepted vendor source entry: {name}")
        for change in entry["history"]:
            if (not isinstance(change, dict) or set(change) != {"date", "reason", "changed"}
                    or not isinstance(change["changed"], dict)
                    or any(not isinstance(change[field], str) or not change[field] for field in ("date", "reason"))):
                raise ValueError(f"unsupported accepted vendor source history: {name}")
    return ledger


def _relative_name(value):
    """A source name is an installation-relative posix path, nothing else."""
    return (isinstance(value, str) and value and not value.startswith("/")
            and ":" not in value and ".." not in value.split("/") and "\\" not in value)


def save(ledger):
    """Write the ledger back, refusing content the schema would not accept.

    The check runs before the write, so a rejected change never reaches the file.
    """
    atomic_json(ledger_path(), validate(ledger))


def installation(directory):
    """The installation root above a directory inside a Quartus installation.

    Callers hand this the executables directory a build was given, an explicit
    `eda/sim_lib` selection, or any other folder inside the installation. The
    root is the nearest parent carrying a recognized Quartus layout, so a
    directory that is not inside an installation has no accepted provenance and
    says so here rather than being hashed against another installation's record.
    """
    directory = Path(directory).resolve()
    for candidate in (directory, *directory.parents):
        if any((candidate / folder).is_dir() for folder in LAYOUTS.values()):
            return candidate
    raise ValueError("not inside a recognized Quartus installation: " + directory.as_posix()
                     + "; expected a parent holding " + " or ".join(sorted(LAYOUTS.values())))


def platform_name(root):
    """Which platform this installation is, read from its own layout."""
    root = Path(root).resolve()
    found = sorted(name for name, folder in LAYOUTS.items() if (root / folder).is_dir())
    if len(found) != 1:
        raise ValueError("unrecognized Quartus installation layout: " + root.as_posix()
                         + "; expected exactly one of " + ", ".join(sorted(LAYOUTS.values())))
    return found[0]


def executables(root):
    """The executables directory of this installation, by its own layout."""
    root = Path(root).resolve()
    folder = root / EXECUTABLES[platform_name(root)]
    if not folder.is_dir():
        raise ValueError("missing Quartus executables directory: " + folder.as_posix())
    return folder


def quartus_release(root):
    """The ACDS release this installation states, or None when it states none.

    Provenance only: the digests decide whether a build may proceed. A release
    string cannot, because an installation may not carry one and because two
    releases can ship the same bytes.
    """
    path = Path(root) / "quartus/version.txt"
    if not path.is_file():
        return None
    section, fields = None, {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif section == "ACDS" and "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    return " ".join(part for part in (fields.get("Version"), fields.get("Edition")) if part) or None


def _entry(ledger, name):
    return ledger["installations"].setdefault(name, {"quartus": None, "sources": {}, "history": []})


def _source_name(root, path):
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except ValueError:
        raise ValueError("vendor source outside the Quartus installation: " + Path(path).as_posix()) from None


def _changed(name, source, accepted, installed, entry, release):
    releases = ""
    if entry.get("quartus") and release and entry["quartus"] != release:
        releases = (f" The accepted record was made against Quartus {entry['quartus']};"
                    f" this installation states {release}.")
    return (f"vendor source changed since it was accepted: {source} on the {name} Quartus installation "
            f"was accepted as {accepted}, the installed file is {installed}." + releases +
            " A vendor file changing under retained evidence fails closed by design. Review the change and "
            f'record it with `python tools/build.py vendor accept --quartus-bin <dir> --source {source} '
            f'--reason "<why>"`, or build against the accepted installation. See ' + SPEC + ".")


def check(directory, paths):
    """Compare the installed vendor sources with the digests this platform accepted.

    `paths` maps each caller's own name to an installed file, and `directory` is
    any directory inside the installation being read. The result keeps those
    names and records the path, the digest, the installation-relative source name
    and one of `unchanged` or `recorded`. A digest that changed since it was
    accepted raises; a source this platform has never recorded is written into
    the ledger and marked `recorded`.
    """
    root = installation(directory)
    name = platform_name(root)
    ledger = load()
    entry = _entry(ledger, name)
    release = quartus_release(root)
    result, added = {}, {}
    for label, path in paths.items():
        path = Path(path)
        if not path.is_file():
            raise ValueError("missing installed vendor source: " + path.as_posix())
        source = _source_name(root, path)
        digest = file_hash(path)
        accepted = entry["sources"].get(source)
        if accepted is None:
            added[source] = digest
        elif accepted != digest:
            raise ValueError(_changed(name, source, accepted, digest, entry, release))
        result[label] = {"path": str(path), "sha256": digest, "source": source, "installation": name,
                         "accepted": RECORDED if accepted is None else UNCHANGED}
    if added:
        _record(name, added, release)
    return result


def _record(name, added, release):
    """Add digests this platform has never recorded. Present digests are left alone.

    The merge re-reads and only writes names that are still absent, so a build
    never replaces a digest the ledger already holds. That load-modify-save is
    not locked, so a write landing inside it could leave the run proceeding on
    bytes the ledger does not accept; the read-back afterwards refuses that run
    instead, naming the source the ledger ended up holding.
    """
    ledger = load()
    entry = _entry(ledger, name)
    entry["sources"].update({source: digest for source, digest in added.items()
                             if source not in entry["sources"]})
    if entry["quartus"] is None and release:
        entry["quartus"] = release
    try:
        save(ledger)
    except OSError as error:
        raise ValueError(f"cannot record the installed vendor sources in {ledger_path().as_posix()}: {error}."
                         f" A first build on a new installation records what it read; see {SPEC}") from error
    accepted = _entry(load(), name)["sources"]
    for source, digest in sorted(added.items()):
        if accepted.get(source) != digest:
            raise ValueError(f"the record of {source} on the {name} Quartus installation changed while this run "
                             f"was recording it: the run read {digest}, the ledger holds "
                             f"{accepted.get(source) or 'nothing'}. Nothing is accepted on this run; rerun it "
                             f"once the other writer has finished. See {SPEC}")


NOTICE = ("Recorded vendor source for the first time on the {installation} Quartus installation: "
          "{source} sha256 {sha256}. Review the ledger change before keeping this result.")


def notices(recorded):
    """One line per vendor source a run recorded for the first time.

    Walks whatever nested record the caller assembled, dicts and lists alike, so
    a build's tool identities and a simulation descriptor's source list both
    report without a second inventory to keep in step.
    """
    lines = []

    def walk(value):
        if isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("accepted") in STATUSES:
            if value["accepted"] == RECORDED:
                lines.append(NOTICE.format(**{field: value[field] for field in ("installation", "source", "sha256")}))
            return
        for item in value.values():
            walk(item)

    walk(recorded)
    return sorted(set(lines))


def require_accepted(entries, *names):
    """The digests of named entries that went through the ledger.

    A diagnostic classifier explains warnings that belong to specific vendor
    bytes, so it states which sources it read and refuses a record that never
    reached the ledger. It no longer states one expected digest: the ledger
    already refused a source whose digest changed.
    """
    digests = {}
    for name in names:
        entry = entries.get(name)
        if (not isinstance(entry, dict) or entry.get("accepted") not in STATUSES
                or not DIGEST.fullmatch(str(entry.get("sha256")))
                or entry.get("installation") not in LAYOUTS
                or not _relative_name(entry.get("source"))):
            raise ValueError("vendor source is not an accepted ledger record: " + str(name))
        digests[name] = entry["sha256"]
    return digests


def accept(directory, sources, reason, today=None):
    """Record reviewed vendor bytes as accepted for this installation's platform.

    The only way an accepted digest changes. It refuses a reason too short to be
    a record and a source whose digest already matches, so the history holds one
    line per actual review rather than a trail of no-ops.
    """
    if not isinstance(reason, str) or len(reason.strip()) < REASON_LENGTH:
        raise ValueError("vendor accept needs a reason of at least "
                         f"{REASON_LENGTH} characters recording why the changed vendor bytes are accepted")
    if not sources or len(set(sources)) != len(sources):
        raise ValueError("vendor accept needs at least one source, each named once")
    root = installation(directory)
    name = platform_name(root)
    ledger = load()
    entry = _entry(ledger, name)
    changed = {}
    for source in sources:
        if not _relative_name(source):
            raise ValueError("vendor source name must be an installation-relative path: " + str(source))
        path = root / source
        if not path.is_file():
            raise ValueError("missing installed vendor source: " + path.as_posix())
        digest = file_hash(path)
        before = entry["sources"].get(source)
        if before == digest:
            raise ValueError("vendor source is already accepted with this digest: " + source)
        changed[source] = {"from": before, "to": digest}
        entry["sources"][source] = digest
    release = quartus_release(root)
    entry["quartus"] = release
    entry["history"].append({"date": today or date.today().isoformat(),
                             "reason": reason.strip(), "changed": changed})
    save(ledger)
    return {"platform": name, "quartus": release, "reason": reason.strip(), "changed": changed,
            "ledger": ledger_path().name,
            "notices": [f"Accepted {source}: {value['from'] or 'not recorded'} -> {value['to']}"
                        for source, value in sorted(changed.items())]
            + ["Commit the ledger change with the reason so the acceptance is reviewed."]}
