"""Publication boundary tests: links, text-only content, and safe output paths."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("wiki_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class PublicationTests(unittest.TestCase):
    def test_private_paths_rejected_even_when_content_is_text(self):
        for path in ("game.ROM", "backup.SAV", "boot.hex", "cart.mem", "cart.mif",
                     "game.srm", "game.state", "game.rtc", "game.gba", "game.nds",
                     "private/header.json", "src/private/facts.md", "workdir/log.txt",
                     ".env", ".env.local", ".n2m.local.toml", "keys/device.pem",
                     "keys/device.key", "credentials.json", "secrets.json"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "private content path"):
                site.checked_text(path, b"plain ASCII private data\n")
        self.assertEqual(site.checked_text("src/example.asm", b"nop\n"), "nop\n")

    def test_forced_tracked_private_file_stops_publication_scan(self):
        temporary = site.ROOT / "workdir/wiki/tests"
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text("*.sav\n", encoding="utf-8")
            (root / "game.sav").write_text("ASCII save", encoding="utf-8")
            subprocess.run(["git", "add", ".gitignore"], cwd=root, check=True)
            self.assertNotIn("game.sav", site.tracked_text(root))
            subprocess.run(["git", "add", "-f", "game.sav"], cwd=root, check=True)
            with self.assertRaisesRegex(ValueError, "private content path"):
                site.tracked_text(root)

    def test_binary_rejection_covers_extensions_signatures_and_disguised_bytes(self):
        cases = [("diagram.PNG", b"text"), ("slides.pptx", b"text"), ("report.pdf", b"text"),
                 ("photo.jpeg", b"text"), ("fake.md", b"%PDF-1.7\n"),
                 ("fake.md", b"\x89PNG\r\n"), ("source.sv", b"a\0b"), ("notes.md", b"\xff\xfe")]
        for path, content in cases:
            with self.subTest(path=path, content=content), self.assertRaises(ValueError):
                site.checked_text(path, content)
        self.assertEqual(site.checked_text("art.svg", '<svg>שלום</svg>'.encode()), '<svg>שלום</svg>')
        self.assertEqual(site.checked_text("source.py", b'SIGNATURE = b"%PDF-"\n'), 'SIGNATURE = b"%PDF-"\n')

    def test_markdown_links_anchors_and_examples(self):
        files = {"README.md": '[Spec][s]\n\n[s]: wiki/a.md#target\n\n`[example](missing.md)`',
                 "wiki/a.md": "# Target\n\n[Home](../README.md)"}
        documents = site.validate(files)
        self.assertIn('?page=wiki/a.md#target', ''.join(documents["README.md"].output))
        self.assertIn('[example](missing.md)', ''.join(documents["README.md"].output))
        files["README.md"] = '[Bad](wiki/a.md#absent)'
        with self.assertRaisesRegex(ValueError, "Broken anchor"):
            site.validate(files)

    def test_html_relative_assets_and_source_line_references(self):
        files = {"wiki/presentations/a.html": '<script src="../../tools/wiki/assets/presentation.js"></script><img src="a.svg"><a href="../../src/a.sv" data-source="src/a.sv" data-line="2">Code</a>',
                 "tools/wiki/assets/presentation.js": "// okay", "wiki/presentations/a.svg": '<svg id="diagram"></svg>', "src/a.sv": "line1\nline2"}
        site.validate(files)
        files["wiki/presentations/a.html"] = '<a href="missing.svg">Bad</a>'
        with self.assertRaisesRegex(ValueError, "Broken link"):
            site.validate(files)
        files["wiki/presentations/a.html"] = '<a data-source="src/a.sv" data-line="3">Bad</a>'
        with self.assertRaisesRegex(ValueError, "Invalid source line"):
            site.validate(files)

    def test_skill_document_formats_and_helper_exclusion(self):
        for path in (".agents/skills/a/SKILL.md", ".agents/skills/a/templates/body.md",
                     ".agents/skills/a/guide.html", ".agents/skills/a/diagram.svg"):
            self.assertTrue(site.content_page(path), path)
        for path in (".agents/skills/a/templates/deck.html", ".agents/skills/a/scripts/helper.py",
                     ".agents/skills/a/scripts/helper.js", "wiki/tool.py"):
            self.assertFalse(site.content_page(path), path)
            self.assertFalse(site.public_asset(path), path)

    def test_excluded_runtime_cannot_cross_boundary(self):
        for markup in ('<script src="../tools/helper.js"></script>', '<img srcset="../src/art.svg 1x">'):
            with self.subTest(markup=markup), self.assertRaisesRegex(ValueError, "Unpublished runtime asset"):
                site.validate({"wiki/a.html": markup, "tools/helper.js": "code", "src/art.svg": "<svg></svg>"})
        with self.assertRaisesRegex(ValueError, "Unpublished runtime asset"):
            site.validate({"wiki/a.css": '@import "../tools/helper.css";', "tools/helper.css": "body {}"})

    def test_template_html_is_source_not_a_live_document(self):
        files = {".agents/skills/a/templates/a.html": '<script src="../../future/path.js"></script>'}
        self.assertEqual(site.validate(files)[next(iter(files))].output, [])

    def test_srcset_svg_resource_links_and_embed_navigation(self):
        files = {"wiki/a.md": '<img srcset="art.svg 1x, art.svg 2x"><svg><defs><g id="shape"></g></defs><use href="#shape" /></svg>',
                 "wiki/art.svg": '<svg></svg>', "wiki/b.html": '<body><a href="a.md#shape">Spec</a></body>'}
        documents = site.validate(files)
        rendered = ''.join(documents["wiki/a.md"].output)
        self.assertIn('srcset="files/wiki/art.svg 1x, files/wiki/art.svg 2x"', rendered)
        self.assertIn(("wiki/art.svg", ""), documents["wiki/a.md"].links)
        self.assertIn('<use href="#shape" />', rendered)
        embedded = ''.join(documents["wiki/b.html"].output)
        self.assertIn('href="a.md#shape" data-wiki-page="wiki/a.md" data-wiki-fragment="shape"', embedded)
        self.assertIn('src="../tools/wiki/assets/embed.js" defer></script></body>', embedded)
        for markup in ('<svg><image href="https://example.com/art.svg" /></svg>', '<img srcset="https://example.com/art.svg 1x">'):
            with self.assertRaisesRegex(ValueError, "Runtime assets must be local"):
                site.validate({"wiki/a.md": markup})

    def test_source_aliases_fragments_and_local_runtime_assets(self):
        files = {"README.md": f'[Code]({site.REPO}/blob/main/src/a.sv#L1)', "src/a.sv": "module a;"}
        self.assertIn(site.REPO + '/blob/main/src/a.sv#L1', ''.join(site.validate(files)["README.md"].output))
        files["README.md"] = '[Code](src/a.sv#L2)'
        with self.assertRaisesRegex(ValueError, "Invalid source lines"):
            site.validate(files)
        for text in ('<script src="https://cdn.example/a.js"></script>', '<img src="data:image/png;base64,abcd">'):
            with self.assertRaises(ValueError):
                site.validate({"wiki/a.html": text})
        with self.assertRaisesRegex(ValueError, "Broken link"):
            site.validate({"tools/a.css": '@import "missing.css";'})

    def test_url_confinement_and_untracked_dependencies(self):
        with self.assertRaisesRegex(ValueError, "Broken link"):
            site.resolve("../../outside.md", "README.md", {"README.md": ""})
        with self.assertRaisesRegex(ValueError, "Unsupported URL"):
            site.resolve("javascript:alert(1)", "README.md", {})
        with self.assertRaisesRegex(ValueError, "Broken link"):
            site.resolve("untracked.md", "README.md", {"README.md": ""})

    def test_link_schemes_through_resolver_and_rendering(self):
        rejected = ("ftp://example.com/file.txt", "ssh://example.com/repo",
                    "custom://example.com/path", "javascript://example.com/path",
                    "ftp:file.txt", "javascript:alert(1)")
        allowed = ("http://example.com/path", "https://example.com/path",
                   "mailto:hello@example.com", "//example.com/path")
        files = {"wiki/index.md": "", "wiki/target.md": "# Target"}
        for url in rejected:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "Unsupported URL in wiki/index.md"):
                site.resolve(url, "wiki/index.md", files)
            for source, text in (("wiki/index.md", f'[Link]({url})'),
                                 ("wiki/index.html", f'<a href="{url}">Link</a>')):
                with self.subTest(url=url, source=source), self.assertRaisesRegex(ValueError, "Unsupported URL"):
                    site.validate({**files, source: text})
        for url in (*allowed, "target.md#target"):
            with self.subTest(url=url):
                expected = ("wiki/target.md", "target") if url == "target.md#target" else None
                self.assertEqual(site.resolve(url, "wiki/index.md", files), expected)
            for source, text in (("wiki/index.md", f'[Link]({url})'),
                                 ("wiki/index.html", f'<a href="{url}">Link</a>')):
                with self.subTest(url=url, source=source):
                    rendered = ''.join(site.validate({**files, source: text})[source].output)
                    href = '?page=wiki/target.md#target' if expected and source.endswith('.md') else url
                    self.assertIn(f'href="{href}"', rendered)
        for url in ("https://example.com/runtime.js", "//example.com/runtime.js"):
            with self.subTest(asset=url), self.assertRaisesRegex(ValueError, "Runtime assets must be local"):
                site.validate({"wiki/index.html": f'<script src="{url}"></script>'})

    def test_output_and_publication_boundary(self):
        parent = site.ROOT / "workdir/wiki/tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            root = Path(directory)
            files = {"README.md": "# Human\n[Guide](worktrees/README.md)", "AGENTS.md": "# Agents",
                     "worktrees/README.md": "# Guide\n[Helper](../tools/private.py)", "private-note.txt": "not a public dependency",
                     "wiki/index.md": "# Wiki", "src/rtl/a.sv": 'EXCLUDED_IMPLEMENTATION',
                     "tools/wiki/assets/shell.html": "<!doctype html><title>Test</title>",
                     ".agents/skills/a/scripts/run.py": "print('test')",
                     "wiki/demo.html": '<body><a href="../src/rtl/a.sv" data-source="src/rtl/a.sv" data-line="1">Source</a></body>',
                     "tools/wiki/assets/embed.js": "// bridge", "tools/private.py": "EXCLUDED_IMPLEMENTATION",
                     "cfg/build.toml": "EXCLUDED_IMPLEMENTATION", ".agents/skills/a/SKILL.md": "[Helper](scripts/run.py)",
                     "wiki/source.svg": '<svg><a href="../cfg/build.toml">Source</a></svg>'}
            for path, content in files.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8")
            with patch.object(site.subprocess, "check_output", return_value="\0".join(files).encode()):
                site.build(root)
                output = root / "workdir/wiki/site"
                (output / "stale.txt").write_text("stale")
                site.build(root)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertNotIn("private-note.txt", manifest)
            for path in ("worktrees/README.md", "src/rtl/a.sv", "tools/private.py", "cfg/build.toml", ".agents/skills/a/scripts/run.py", "tools/wiki/assets/embed.js", "tools/wiki/assets/shell.html"):
                self.assertNotIn(path, manifest)
                if path not in site.RUNTIME:
                    self.assertFalse((output / "files" / path).exists())
            for artifact in output.rglob("*"):
                if artifact.is_file():
                    self.assertNotIn("EXCLUDED_IMPLEMENTATION", artifact.read_text(), str(artifact))
            self.assertIn(site.REPO + "/blob/main/cfg/build.toml", (output / "files/wiki/source.svg").read_text())
            self.assertIn(site.REPO + "/blob/main/worktrees/README.md", manifest["README.md"]["html"])
            self.assertTrue((output / "files/tools/wiki/assets/embed.js").is_file())
            self.assertFalse((output / "stale.txt").exists())
            self.assertTrue((output / "wiki-index/index.html").is_file())
            self.assertFalse((output / "skills/a/scripts/run.py/index.html").exists())
            self.assertIn(site.REPO + '/blob/main/src/rtl/a.sv#L1', (output / 'files/wiki/demo.html').read_text())
            self.assertNotIn('data-source=', (output / 'files/wiki/demo.html').read_text())
            with self.assertRaisesRegex(ValueError, "output must"):
                site.build(root, root / "wiki")


if __name__ == "__main__":
    unittest.main()
