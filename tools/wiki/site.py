"""Build the text-only repository wiki. No source document is maintained twice."""

from __future__ import annotations

import html
from html.parser import HTMLParser
import json
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
from urllib.parse import quote, unquote, urlsplit

import markdown

ROOT = Path(__file__).resolve().parents[2]
REPO = "https://github.com/amichai-bd/nand2mario"
PROHIBITED = set(".png .jpg .jpeg .gif .webp .ico .bmp .tif .tiff .avif .pdf .ppt .pptx .doc .docx .xls .xlsx .zip .gz .7z .woff .woff2 .ttf .mp3 .mp4 .wav .exe .dll .gb .gbc .bin".split())
SIGNATURES = (b"%PDF-", b"\x89PNG", b"GIF87a", b"GIF89a", b"PK\x03\x04", b"\xff\xd8\xff", b"RIFF", b"\xd0\xcf\x11\xe0")
PUBLISH_ROOTS = ("wiki/", ".agents/skills/", "src/", "tools/", "cfg/")


def checked_text(path: str, data: bytes) -> str:
    if Path(path).suffix.lower() in PROHIBITED or data.startswith(SIGNATURES):
        raise ValueError(f"Prohibited binary content: {path}")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Not UTF-8 text: {path}") from error
    if any(ord(char) < 32 and char not in "\t\r\n" for char in text) or "\x7f" in text:
        raise ValueError(f"Binary control bytes: {path}")
    return text


def tracked_text(root: Path) -> dict[str, str]:
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    result = {}
    for path in filter(None, paths):
        source = root / path
        if source.is_symlink() or not source.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Source must stay inside checkout: {path}")
        result[path] = checked_text(path, source.read_bytes())
    return result


def category(path: str) -> str:
    if path.startswith((".agents/", "wiki/agents/")):
        return "Agents/Skills"
    if path.startswith(("src/", "wiki/src/")):
        return "Src"
    if path.startswith(("tools/", "wiki/tools/")):
        return "Tools"
    if path.startswith(("cfg/", "wiki/cfg/")):
        return "Cfg"
    if path.startswith("wiki/presentations/"):
        return "Presentations"
    return "Home"


def route(path: str, fragment: str = "") -> str:
    return "?page=" + quote(path, safe="/") + ("#" + quote(fragment) if fragment else "")


def resolve(url: str, source: str, files: dict[str, str]) -> tuple[str, str] | None:
    parts = urlsplit(url)
    if parts.scheme or parts.netloc:
        if parts.scheme not in ("https", "http", "mailto") and not parts.netloc:
            raise ValueError(f"Unsupported URL in {source}: {url}")
        return None
    path = unquote(parts.path)
    target = posixpath.normpath(path.lstrip("/") if path.startswith("/") else
                                 posixpath.join(posixpath.dirname(source), path)) if path else source
    if target not in files:
        target = next((candidate for candidate in (target + "/README.md", target + "/index.md")
                       if candidate in files), target)
    if target not in files:
        raise ValueError(f"Broken link in {source}: {url}")
    return target, unquote(parts.fragment)


class Document(HTMLParser):
    """Validate parsed attributes, and rewrite only rendered Markdown URLs."""

    def __init__(self, source, files, rewrite=False):
        super().__init__(convert_charrefs=False)
        self.source, self.files, self.rewrite = source, files, rewrite
        self.output, self.links, self.ids = [], [], set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            self.ids.add(attributes["id"])
        for key, value in attrs:
            if key in ("href", "src", "poster", "data") and value:
                target = resolve(value, self.source, self.files)
                if target:
                    path, fragment = target
                    self.links.append((path, fragment))
                    if self.rewrite:
                        attributes[key] = route(path, fragment) if key == "href" else "files/" + quote(path, safe="/")
            if key == "srcset" and value:
                for candidate in value.split(","):
                    resolve(candidate.strip().split()[0], self.source, self.files)
        if attributes.get("data-source"):
            path = attributes["data-source"]
            if path not in self.files:
                raise ValueError(f"Unknown source reference in {self.source}: {path}")
            line = attributes.get("data-line", "1")
            if not line.isdigit() or not 1 <= int(line) <= max(1, len(self.files[path].splitlines())):
                raise ValueError(f"Invalid source line in {self.source}: {path}:{line}")
        rendered = " ".join(key if value is None else f'{key}="{html.escape(value, quote=True)}"'
                            for key, value in attributes.items())
        self.output.append(f"<{tag}{' ' if rendered else ''}{rendered}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
    def handle_endtag(self, tag):
        self.output.append(f"</{tag}>")
    def handle_data(self, data):
        self.output.append(data)
    def handle_entityref(self, name):
        self.output.append(f"&{name};")
    def handle_charref(self, name):
        self.output.append(f"&#{name};")
    def handle_comment(self, data):
        self.output.append(f"<!--{data}-->")
    def handle_decl(self, decl):
        self.output.append(f"<!{decl}>")


def render(path: str, text: str, files: dict[str, str]) -> Document:
    suffix = Path(path).suffix.lower()
    parser = Document(path, files, rewrite=suffix == ".md")
    if suffix == ".md":
        parser.feed(markdown.markdown(text, extensions=["extra", "toc", "sane_lists"]))
    elif suffix in (".html", ".svg") and path.startswith("wiki/"):
        parser.feed(text)
    return parser


def validate(files: dict[str, str]) -> dict[str, Document]:
    documents = {path: render(path, text, files) for path, text in files.items()}
    for path, document in documents.items():
        for target, fragment in document.links:
            if fragment and not re.fullmatch(r"L\d+(?:-L\d+)?", fragment) and fragment not in documents[target].ids:
                raise ValueError(f"Broken anchor in {path}: {target}#{fragment}")
        if Path(path).suffix == ".css":
            for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", files[path]):
                resolve(url.strip(), path, files)
    return documents


def build(root: Path = ROOT, output: Path | None = None):
    output = output or root / "workdir/wiki/site"
    expected = root / "workdir/wiki/site"
    if (output.resolve() != expected.resolve() or output.is_symlink()
            or not output.resolve().is_relative_to(root.resolve())):
        raise ValueError("Wiki output must be workdir/wiki/site inside the checkout")
    tracked = tracked_text(root)
    documents = validate(tracked)
    selected = {path for path in tracked if path in ("README.md", "AGENTS.md") or path.startswith(PUBLISH_ROOTS)}
    pending = list(selected)
    while pending:
        path = pending.pop()
        for target, _ in documents[path].links:
            if target not in selected:
                selected.add(target)
                pending.append(target)
    files = {path: text for path, text in tracked.items() if path in selected}
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    manifest = {}
    for path, text in files.items():
        published = path in ("README.md", "AGENTS.md") or path.startswith(PUBLISH_ROOTS)
        suffix = Path(path).suffix.lower()
        kind = "html" if suffix in (".html", ".svg") and path.startswith("wiki/") else "md" if suffix == ".md" else "source"
        manifest[path] = {"category": category(path), "nav": published, "kind": kind,
                          "text": text, "html": "".join(documents[path].output) if kind == "md" else ""}
        destination = output / "files" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (output / "index.html").write_text((root / "tools/wiki/assets/shell.html").read_text(encoding="utf-8"), encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    for path in manifest:
        old = (path.removeprefix("wiki/") if path.startswith("wiki/") else
               path.removeprefix(".agents/") if path.startswith(".agents/skills/") else path)
        if not old.endswith(".md") or path == "README.md":
            continue
        old = "wiki-index.md" if path == "wiki/index.md" else old
        target = output / old[:-3] / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        relative = posixpath.relpath("index.html", old[:-3]) + route(path)
        target.write_text(f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={html.escape(relative)}"><a href="{html.escape(relative)}">Open document</a>', encoding="utf-8")
    print(f"Wiki built: {len(files)} tracked text files checked; {output}")


if __name__ == "__main__":
    build()
