"""Validate a structured Markdown draft and create one GitHub issue."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


META_RE = re.compile(r"<!--\s*issue-meta:\s*(\{.*\})\s*-->")
REPO_RE = re.compile(r"[^/\s]+/[^/\s]+")
HEADING_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$")
FENCE_RE = re.compile(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$")
CHECKBOX_RE = re.compile(r"^[ \t]*[-*+] \[[ xX]\] \S.*$")
REQUIRED_KEYS = {"title", "labels", "assignee", "repo"}


class DraftError(ValueError):
    """The draft does not meet the repository issue contract."""


def read_draft(path: Path) -> tuple[dict[str, Any], str]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        text = stream.read()
    newline = text.find("\n")
    if newline < 0:
        raise DraftError("draft needs a metadata line followed by an issue body")
    first_line = text[:newline].removesuffix("\r")
    match = META_RE.fullmatch(first_line)
    if not match:
        raise DraftError("first line must be an issue-meta JSON comment")
    try:
        metadata = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        raise DraftError(f"invalid metadata JSON: {error.msg}") from error
    if not isinstance(metadata, dict):
        raise DraftError("metadata must be a JSON object")
    body = text[newline + 1 :]
    validate_metadata(metadata)
    validate_body(body)
    return metadata, body


def validate_metadata(metadata: dict[str, Any]) -> None:
    missing = REQUIRED_KEYS - metadata.keys()
    extra = metadata.keys() - REQUIRED_KEYS
    if missing or extra:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if extra:
            details.append("unknown " + ", ".join(sorted(extra)))
        raise DraftError("metadata fields: " + "; ".join(details))

    title = metadata["title"]
    labels = metadata["labels"]
    assignee = metadata["assignee"]
    repo = metadata["repo"]
    if not isinstance(title, str) or not title.strip() or "\n" in title or "\r" in title:
        raise DraftError("title must be one non-empty line")
    if not isinstance(labels, list) or not labels or any(
        not isinstance(label, str) or not label.strip() for label in labels
    ):
        raise DraftError("labels must be a non-empty list of strings")
    if not isinstance(assignee, str) or not assignee.strip():
        raise DraftError("assignee must be a non-empty string")
    if not isinstance(repo, str) or not REPO_RE.fullmatch(repo):
        raise DraftError("repo must use owner/name")


def lines_outside_fences(body: str) -> list[tuple[int, str]]:
    lines = []
    fence: tuple[str, int] | None = None
    offset = 0
    for raw_line in body.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        match = FENCE_RE.fullmatch(line)
        if fence:
            marker, width = fence
            if re.fullmatch(rf"[ ]{{0,3}}{re.escape(marker)}{{{width},}}[ \t]*", line):
                fence = None
        elif match and (match.group(1)[0] == "~" or "`" not in match.group(2)):
            fence = (match.group(1)[0], len(match.group(1)))
        else:
            lines.append((offset, line))
        offset += len(raw_line)
    return lines


def find_headings(body: str) -> list[tuple[str, int, int]]:
    headings = []
    for offset, line in lines_outside_fences(body):
        match = HEADING_RE.fullmatch(line)
        if match:
            headings.append((match.group(1).strip(), offset, offset + len(line)))
    return headings


def validate_body(body: str) -> None:
    matches = find_headings(body)
    headings = [name for name, _, _ in matches]
    if len(headings) < 4:
        raise DraftError("issue body needs the four shared headings")
    if body[: matches[0][1]].strip():
        raise DraftError("issue body must start with the TL;DR heading")
    if headings[:2] != ["TL;DR", "Specification reference"]:
        raise DraftError("issue body must start with TL;DR, then Specification reference")
    if headings[-2:] != ["Goal", "Success criteria"]:
        raise DraftError("issue body must end with Goal, then Success criteria")
    for index, (_, _, content_start) in enumerate(matches):
        end = matches[index + 1][1] if index + 1 < len(matches) else len(body)
        if not body[content_start:end].strip():
            raise DraftError(f"section {headings[index]!r} is empty")
    success_body = body[matches[-1][2] :]
    checkboxes = sum(
        bool(CHECKBOX_RE.fullmatch(line))
        for _, line in lines_outside_fences(success_body)
    )
    if not 3 <= checkboxes <= 5:
        raise DraftError("Success criteria needs three to five checkboxes")


def build_command(metadata: dict[str, Any]) -> list[str]:
    command = [
        "gh",
        "issue",
        "create",
        "--repo",
        metadata["repo"],
        "--title",
        metadata["title"],
        "--body-file",
        "-",
    ]
    for label in metadata["labels"]:
        command.extend(["--label", label])
    command.extend(["--assignee", metadata["assignee"]])
    return command


def create_issue(metadata: dict[str, Any], body: str) -> str:
    result = subprocess.run(
        build_command(metadata),
        input=body.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or f"gh exited with {result.returncode}")
    return result.stdout.decode("utf-8", errors="replace").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("draft", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        metadata, body = read_draft(args.draft)
        if args.check:
            print("issue draft is valid")
        else:
            print(create_issue(metadata, body))
    except (DraftError, OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
