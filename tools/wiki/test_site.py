"""Publication boundary tests: links, text-only content, and safe output paths."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("wiki_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class PublicationTests(unittest.TestCase):
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
        files = {"wiki/presentations/a.html": '<script src="../../tools/a.js"></script><img src="a.svg"><a href="../../src/a.sv" data-source="src/a.sv" data-line="2">Code</a>',
                 "tools/a.js": "// okay", "wiki/presentations/a.svg": '<svg id="diagram"></svg>', "src/a.sv": "line1\nline2"}
        site.validate(files)
        files["wiki/presentations/a.html"] = '<a href="missing.svg">Bad</a>'
        with self.assertRaisesRegex(ValueError, "Broken link"):
            site.validate(files)
        files["wiki/presentations/a.html"] = '<a data-source="src/a.sv" data-line="3">Bad</a>'
        with self.assertRaisesRegex(ValueError, "Invalid source line"):
            site.validate(files)

    def test_template_html_is_source_not_a_live_document(self):
        files = {".agents/skills/a/templates/a.html": '<script src="../../future/path.js"></script>'}
        self.assertEqual(site.validate(files)[next(iter(files))].output, [])

    def test_srcset_svg_resource_links_and_embed_navigation(self):
        files = {"wiki/a.md": '<img srcset="../assets/art.svg 1x, ../assets/art.svg 2x"><svg><defs><g id="shape"></g></defs><use href="#shape" /></svg>',
                 "assets/art.svg": '<svg></svg>', "wiki/b.html": '<body><a href="a.md#shape">Spec</a></body>'}
        documents = site.validate(files)
        rendered = ''.join(documents["wiki/a.md"].output)
        self.assertIn('srcset="files/assets/art.svg 1x, files/assets/art.svg 2x"', rendered)
        self.assertIn(("assets/art.svg", ""), documents["wiki/a.md"].links)
        self.assertIn('<use href="#shape" />', rendered)
        embedded = ''.join(documents["wiki/b.html"].output)
        self.assertIn('href="a.md#shape" data-wiki-page="wiki/a.md" data-wiki-fragment="shape"', embedded)
        self.assertIn('src="../tools/wiki/assets/embed.js" defer></script></body>', embedded)
        for markup in ('<svg><image href="https://example.com/art.svg" /></svg>', '<img srcset="https://example.com/art.svg 1x">'):
            with self.assertRaisesRegex(ValueError, "Runtime assets must be local"):
                site.validate({"wiki/a.md": markup})

    def test_source_aliases_fragments_and_local_runtime_assets(self):
        files = {"README.md": f'[Code]({site.REPO}/blob/main/src/a.sv#L1)', "src/a.sv": "module a;"}
        self.assertIn('?page=src/a.sv#L1', ''.join(site.validate(files)["README.md"].output))
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

    def test_output_and_publication_boundary(self):
        parent = site.ROOT / "workdir/wiki/tests"
        parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            root = Path(directory)
            files = {"README.md": "# Human\n[Guide](worktrees/README.md)", "AGENTS.md": "# Agents",
                     "worktrees/README.md": "# Guide", "private-note.txt": "not a public dependency",
                     "wiki/index.md": "# Wiki", "src/rtl/a.sv": '<script>alert(1)</script>',
                     "tools/wiki/assets/shell.html": "<!doctype html><title>Test</title>",
                     ".agents/skills/a/scripts/run.py": "print('test')",
                     "wiki/demo.html": '<body><a href="../src/rtl/a.sv">Source</a></body>',
                     "tools/wiki/assets/embed.js": "// bridge"}
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
            self.assertIn("worktrees/README.md", manifest)
            self.assertFalse(manifest["worktrees/README.md"]["nav"])
            self.assertEqual(manifest["src/rtl/a.sv"]["kind"], "source")
            self.assertFalse((output / "stale.txt").exists())
            self.assertTrue((output / "wiki-index/index.html").is_file())
            self.assertTrue((output / "skills/a/scripts/run.py/index.html").is_file())
            self.assertIn('data-wiki-page="src/rtl/a.sv"', (output / "files/wiki/demo.html").read_text())
            with self.assertRaisesRegex(ValueError, "output must"):
                site.build(root, root / "wiki")


if __name__ == "__main__":
    unittest.main()
