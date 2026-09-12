"""Rewrite the work caps everywhere they are stated, then prove no stale number survives."""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path


WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve"]
NUMBER_RE = r"(?P<n>[A-Za-z]+|\d+)"

# Every sentence that states a cap. Each pattern must match its file exactly once.
# The fourth field names the noun the cap counts, as (singular, plural), so a cap
# of one reads "one open PR" rather than "one open PRs"; None where the sentence
# states no noun. Extend this table when a new location states a cap; the scan
# below catches a location that was added without being listed here.
LOCATIONS = [
    ("AGENTS.md", "prs", rf"at most {NUMBER_RE} open (?P<w>PRs?)", ("PR", "PRs")),
    ("AGENTS.md", "crewmates", rf"at most {NUMBER_RE} active (?P<w>crewmates?)",
     ("crewmate", "crewmates")),
    ("AGENTS.md", "prs", rf"has fewer than {NUMBER_RE} open\.", None),
]

# Where any cap statement may legitimately appear. The scan reads every file here.
SEARCH_PATHS = ["AGENTS.md", "CLAUDE.md", "README.md", ".agents", "wiki/agents",
                "worktrees/README.md", ".claude"]
# Phrases that state a cap. Any number word or digit in the slot is checked
# against the expected value for that kind.
SCAN = [
    ("prs", rf"\b{NUMBER_RE} open PRs?\b"),
    ("prs", rf"fewer than {NUMBER_RE} open\b"),
    ("crewmates", rf"\b{NUMBER_RE} active (?:crewmates?|subagents?)\b"),
    ("crewmates", rf"\b{NUMBER_RE} crewmates?\b"),
]
HISTORY = ".agents/skills/update-crewmates/HISTORY.md"
# The log keeps old numbers on purpose; the scan skips it and the script sources.
SKIP_SCAN = {HISTORY, ".agents/skills/update-crewmates/scripts"}
TEXT_SUFFIXES = {".md", ".txt", ".py", ".yml", ".yaml", ".json", ".toml"}


class CapError(ValueError):
    """A cap could not be rewritten or a stale cap survived."""


def word(value: int) -> str:
    if not 1 <= value <= len(WORDS):
        raise CapError(f"cap must be between 1 and {len(WORDS)}, got {value}")
    return WORDS[value - 1]


def number(token: str) -> int | None:
    """The integer a token names, or None when it is not a number."""
    if token.isdigit():
        return int(token)
    if token.lower() in WORDS:
        return WORDS.index(token.lower()) + 1
    return None


def read(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def plan(root: Path, caps: dict[str, int]) -> tuple[dict[str, int], dict[str, str]]:
    """The old caps and the rewritten text of every listed file; writes nothing."""
    texts: dict[str, str] = {}
    old: dict[str, int] = {}
    for relative, kind, pattern, forms in LOCATIONS:
        text = texts.setdefault(relative, read(root / relative))
        matches = list(re.finditer(pattern, text))
        if len(matches) != 1:
            raise CapError(f"{relative}: expected one match for {pattern!r}, found {len(matches)}")
        match = matches[0]
        token = match.group("n")
        current = number(token)
        if current is None:
            raise CapError(f"{relative}: {match.group(0)!r} does not carry a number")
        if old.setdefault(kind, current) != current:
            raise CapError(f"{relative}: {kind} reads {current}, another location reads {old[kind]}")
        replacement = word(caps[kind])
        if token[0].isupper():
            replacement = replacement.capitalize()
        if forms is not None:
            # The noun sits after the number, so rewrite it first and the number's
            # span still holds.
            noun = forms[0] if caps[kind] == 1 else forms[1]
            start, end = match.span("w")
            text = text[:start] + noun + text[end:]
        start, end = match.span("n")
        texts[relative] = text[:start] + replacement + text[end:]
    return old, texts


def scan_files(root: Path):
    for relative in SEARCH_PATHS:
        base = root / relative
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for path in candidates:
            posix = path.relative_to(root).as_posix()
            if any(posix == skip or posix.startswith(skip + "/") for skip in SKIP_SCAN):
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                yield posix, path


def verify(root: Path, caps: dict[str, int],
           pending: dict[str, str] | None = None) -> tuple[list[str], list[str]]:
    """Every cap statement under the search paths; (consistent, stale).

    `pending` maps a relative path to text that replaces the file's content for
    the scan, so a rewrite can be checked before it is written.
    """
    found, stale = [], []
    pending = pending or {}
    for posix, path in scan_files(root):
        text = pending[posix] if posix in pending else read(path)
        for line_number, line in enumerate(text.splitlines(), 1):
            for kind, pattern in SCAN:
                for match in re.finditer(pattern, line):
                    value = number(match.group("n"))
                    if value is None:
                        continue
                    entry = f"{posix}:{line_number}: {kind}={value} {match.group(0)!r}"
                    (found if value == caps[kind] else stale).append(entry)
    return found, stale


def logged(root: Path) -> dict[str, int]:
    """The caps recorded by the last HISTORY.md entry."""
    path = root / HISTORY
    if not path.exists():
        raise CapError(f"{HISTORY} does not exist; give both caps")
    entries = [line for line in read(path).splitlines() if line.startswith("- ")]
    if not entries:
        raise CapError(f"{HISTORY} has no entries; give both caps")
    match = re.fullmatch(r"- .*: crewmates \d+ -> (\d+), open PRs \d+ -> (\d+) \(asked by .*\)",
                         entries[-1])
    if not match:
        raise CapError(f"{HISTORY}: cannot read the last entry {entries[-1]!r}")
    return {"crewmates": int(match.group(1)), "prs": int(match.group(2))}


def requested(args: argparse.Namespace) -> dict[str, int]:
    given = [args.crewmates, args.open_prs]
    if all(value is None for value in given) and args.check:
        return logged(args.root)
    if any(value is None for value in given):
        raise CapError("give both caps: <crewmates> <open-prs>")
    return {"crewmates": args.crewmates, "prs": args.open_prs}


def log(root: Path, old: dict[str, int], caps: dict[str, int], by: str, date: str) -> None:
    path = root / HISTORY
    line = (f"- {date}: crewmates {old['crewmates']} -> {caps['crewmates']}, "
            f"open PRs {old['prs']} -> {caps['prs']} (asked by {by})\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = read(path) if path.exists() else "# Cap history\n\nOne line per invocation, newest last.\n\n"
    if not text.endswith("\n"):
        text += "\n"
    write(path, text + line)


def report(found: list[str], stale: list[str]) -> None:
    for entry in found:
        print(f"ok    {entry}")
    for entry in stale:
        print(f"STALE {entry}")
    if stale:
        raise CapError(f"{len(stale)} cap statement(s) disagree with the requested caps")
    print(f"verified {len(found)} cap statements under {', '.join(SEARCH_PATHS)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crewmates", type=int, nargs="?",
                        help="active subagents, reviewers and scouts included")
    parser.add_argument("open_prs", type=int, nargs="?", help="open PRs per orchestration tree")
    parser.add_argument("--by", default="owner", help="who asked for the change")
    parser.add_argument("--date", default=datetime.date.today().isoformat())
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--check", action="store_true",
                        help="only scan for statements that disagree with the given caps "
                             "(or, with no numbers, with the last HISTORY.md entry)")
    args = parser.parse_args(argv)
    try:
        caps = requested(args)
        word(caps["crewmates"]), word(caps["prs"])
        if args.check:
            report(*verify(args.root, caps))
            return 0
        old, texts = plan(args.root, caps)
        # Scan the planned text first: a stale statement elsewhere leaves the tree untouched.
        report(*verify(args.root, caps, texts))
        # Compare text, not only caps: a cap that already reads right may still
        # need its noun agreed with the number.
        changed = {relative: text for relative, text in texts.items()
                   if text != read(args.root / relative)}
        if not changed:
            print("caps already read crewmates "
                  f"{caps['crewmates']}, open PRs {caps['prs']}; nothing written")
            return 0
        for relative, text in changed.items():
            write(args.root / relative, text)
        log(args.root, old, caps, args.by, args.date)
        print(f"rewrote {len(LOCATIONS)} locations: crewmates {old['crewmates']} -> "
              f"{caps['crewmates']}, open PRs {old['prs']} -> {caps['prs']}")
    except (CapError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
