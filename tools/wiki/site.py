"""Stage tracked documentation and adapt it to MkDocs without source copies."""

from __future__ import annotations

import html
import posixpath
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "workdir/wiki/docs"
REPO = "https://github.com/amichai-bd/nand2mario"
SOURCES: dict[str, str] = {}
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}


def destination(source: str) -> str:
    if source == "README.md":
        return "index.md"
    if source == "wiki/index.md":
        return "wiki-index.md"
    if source.startswith("wiki/"):
        return source.removeprefix("wiki/")
    if source.startswith(".agents/skills/"):
        path = source.removeprefix(".agents/")
        return path if Path(path).suffix.lower() in IMAGES | {".md"} else path + ".md"
    return source


def source_links(source: str) -> str:
    path = quote(source, safe="/")
    return f"[Source]({REPO}/blob/main/{path}) · [Edit]({REPO}/edit/main/{path})\n\n"


def stage(root: Path, docs: Path) -> dict[str, str]:
    # Only this generated directory is replaced; tracked and ignored inputs stay put.
    expected = root / "workdir/wiki/docs"
    if (docs.resolve() != expected.resolve() or docs.is_symlink()
            or not docs.resolve().is_relative_to(root.resolve())):
        raise ValueError("Wiki staging must be workdir/wiki/docs")
    if docs.exists():
        shutil.rmtree(docs)
    docs.mkdir(parents=True)
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "wiki", "README.md", "AGENTS.md", ".agents/skills"],
        cwd=root,
    ).decode("utf-8").split("\0")
    sources = {}
    for source in filter(None, tracked):
        original = root / source
        if original.is_symlink() or not original.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Documentation source must stay inside the checkout: {source}")
        target = destination(source)
        if target in sources:
            raise ValueError(f"Wiki path collision: {target}")
        sources[target] = source
        output = docs / target
        output.parent.mkdir(parents=True, exist_ok=True)
        if source.startswith(".agents/skills/") and not source.endswith(".md") and original.suffix.lower() not in IMAGES:
            # Show scripts/config as escaped text; never execute or serve active content.
            try:
                content = "<pre><code>" + html.escape(original.read_text(encoding="utf-8")) + "</code></pre>"
            except UnicodeDecodeError:
                content = "Binary supporting file. Open the source link to inspect it."
            output.write_text(f"# {original.name}\n\n{source_links(source)}{content}\n", encoding="utf-8")
        else:
            shutil.copyfile(original, output)
    readme = (root / "README.md").read_text(encoding="utf-8")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8")
    landing = '<div class="document-toggle" role="group" aria-label="Document view">\n'
    landing += '<button type="button" data-view="readme" aria-pressed="true" aria-controls="readme-view">README</button>\n'
    landing += '<button type="button" data-view="agents" aria-pressed="false" aria-controls="agents-view">AGENTS</button>\n</div>\n\n'
    for name, source, content in (("readme", "README.md", readme), ("agents", "AGENTS.md", agents)):
        landing += f'<div id="{name}-view" data-source="{source}" markdown="1">\n\n'
        landing += source_links(source) + content + "\n\n</div>\n\n"
    (docs / "index.md").write_text(landing, encoding="utf-8")
    assets = docs / "site-assets"
    assets.mkdir()
    for asset in (root / "tools/wiki/assets").iterdir():
        shutil.copyfile(asset, assets / asset.name)
    return sources


def navigation(sources: dict[str, str], prefix: str) -> list:
    tree = {}
    for target, source in sorted(sources.items()):
        if not source.startswith(prefix) or not target.endswith(".md"):
            continue
        parts = source.removeprefix(prefix).split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = target

    def entries(node):
        return [{name: entries(value) if isinstance(value, dict) else value}
                for name, value in node.items()]

    return entries(tree)


def rewrite_url(url: str, source: str, page: str, sources: dict[str, str]) -> str:
    parts = urlsplit(url)
    if parts.scheme or parts.netloc or not parts.path:
        return url
    path = unquote(parts.path)
    resolved = posixpath.normpath(path.lstrip("/") if path.startswith("/")
                                 else posixpath.join(posixpath.dirname(source), path))
    reverse = {original: target for target, original in sources.items()}
    if resolved in reverse:
        target = posixpath.relpath(reverse[resolved], posixpath.dirname(page) or ".")
        return urlunsplit(("", "", quote(target, safe="/"), parts.query, parts.fragment))
    # Files outside the published set remain repository links. Missing files must fail.
    if (ROOT / resolved).exists() and (ROOT / resolved).resolve().is_relative_to(ROOT):
        kind = "tree" if (ROOT / resolved).is_dir() else "blob"
        return urlunsplit(("https", "github.com", f"/amichai-bd/nand2mario/{kind}/main/{quote(resolved, safe='/')}", parts.query, parts.fragment))
    raise ValueError(f"Broken documentation link in {source}: {url}")


class SourceLinks(Treeprocessor):
    def run(self, tree):
        def visit(element, source):
            source = element.get("data-source", source)
            for attr in ("href", "src"):
                if element.get(attr):
                    element.set(attr, rewrite_url(element.get(attr), source, LINKS.page, SOURCES))
            for child in element:
                visit(child, source)
        visit(tree, LINKS.source)


class Links(Extension):
    source = ""
    page = ""

    def extendMarkdown(self, md):
        # Run after Markdown links are parsed and before MkDocs validates relative links.
        md.treeprocessors.register(SourceLinks(md), "repository_links", 2)


LINKS = Links()


def on_config(config):
    global SOURCES
    SOURCES = stage(ROOT, DOCS)
    config.nav = [{"Home": "index.md"}, {"AGENTS.md": "AGENTS.md"},
                  {"Wiki": navigation(SOURCES, "wiki/")},
                  {"Skills": navigation(SOURCES, ".agents/skills/")}]
    config.markdown_extensions.extend(["md_in_html", LINKS])
    return config


def on_page_markdown(markdown, page, **kwargs):
    LINKS.page = page.file.src_uri
    LINKS.source = SOURCES[LINKS.page]
    path = quote(LINKS.source, safe="/")
    page.edit_url = f"{REPO}/edit/main/{path}"
    if LINKS.page == "index.md" or not LINKS.source.endswith(".md"):
        return markdown
    return source_links(LINKS.source) + markdown
