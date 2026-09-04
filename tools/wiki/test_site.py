"""Check source staging, navigation and links at the publication boundary."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import markdown

spec = importlib.util.spec_from_file_location("wiki_site", Path(__file__).with_name("site.py"))
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class PublicationTests(unittest.TestCase):
    def test_source_paths(self):
        sources = {
            "index.md": "README.md",
            "AGENTS.md": "AGENTS.md",
            "tools/build.md": "wiki/tools/build.md",
            "skills/test/templates/a.md": ".agents/skills/test/templates/a.md",
        }
        self.assertEqual(site.rewrite_url("wiki/tools/build.md#cache", "README.md", "index.md", sources), "tools/build.md#cache")
        self.assertEqual(site.rewrite_url("../../AGENTS.md", "wiki/tools/build.md", "tools/build.md", sources), "../AGENTS.md")
        self.assertEqual(site.rewrite_url("templates/a.md", ".agents/skills/test/SKILL.md", "skills/test/SKILL.md", sources), "templates/a.md")
        with self.assertRaisesRegex(ValueError, "Broken documentation link"):
            site.rewrite_url("missing.md", "README.md", "index.md", sources)

    def test_markdown_links_are_parsed_not_regex_replaced(self):
        with patch.object(site, "SOURCES", {"skills/a/examples/space name.md": ".agents/skills/a/examples/space name.md"}):
            site.LINKS.source = ".agents/skills/a/SKILL.md"
            site.LINKS.page = "skills/a/SKILL.md"
            rendered = markdown.markdown('[Example][ref]\n\n[ref]: examples/space%20name.md\n\n`[not a link](missing.md)`', extensions=[site.LINKS])
        self.assertIn('href="examples/space%20name.md"', rendered)
        self.assertIn("[not a link](missing.md)", rendered)

    def test_navigation_includes_support_files(self):
        sources = {"skills/a/SKILL.md": ".agents/skills/a/SKILL.md",
                   "skills/a/scripts/x.py.md": ".agents/skills/a/scripts/x.py"}
        self.assertEqual(site.navigation(sources, ".agents/skills/"),
                         [{"a": [{"SKILL.md": "skills/a/SKILL.md"}, {"scripts": [{"x.py": "skills/a/scripts/x.py.md"}]}]}])

    def test_staging_only_publishes_tracked_sources_and_removes_stale_output(self):
        temporary = site.ROOT / "workdir/wiki/tests"
        temporary.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temporary) as folder:
            root = Path(folder)
            files = {"README.md": "# Human\n", "AGENTS.md": "# Agent\n", "wiki/index.md": "# Wiki\n",
                     ".agents/skills/a/scripts/run.py": '<script>alert("no")</script>',
                     ".agents/skills/a/assets/picture.png": b"\x89PNG\r\n"}
            for name, value in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value if isinstance(value, bytes) else value.encode())
            (root / "wiki/private-draft.md").write_text("not tracked")
            (root / "tools/wiki/assets").mkdir(parents=True)
            docs = root / "workdir/wiki/docs"
            with patch.object(site.subprocess, "check_output", return_value="\0".join(files).encode()):
                sources = site.stage(root, docs)
                (docs / "stale.md").write_text("stale")
                site.stage(root, docs)
            self.assertFalse((docs / "stale.md").exists())
            self.assertFalse((docs / "private-draft.md").exists())
            self.assertEqual(len(sources), 5)
            rendered_script = (docs / "skills/a/scripts/run.py.md").read_text()
            self.assertIn("&lt;script&gt;", rendered_script)
            self.assertNotIn("<script>", rendered_script)
            self.assertEqual((docs / "skills/a/assets/picture.png").read_bytes(), b"\x89PNG\r\n")
            landing = (docs / "index.md").read_text()
            self.assertIn('data-view="readme" aria-pressed="true"', landing)
            self.assertIn('# Human', landing)
            self.assertIn('# Agent', landing)
            self.assertIn('/edit/main/AGENTS.md', landing)

    def test_staging_rejects_wrong_cleanup_path(self):
        with self.assertRaisesRegex(ValueError, "staging must"):
            site.stage(site.ROOT, site.ROOT / "wiki")

    def test_nonpublished_files_keep_source_links(self):
        link = site.rewrite_url("../../tools/wiki/check.py", "wiki/tools/wiki.md", "tools/wiki.md", {})
        self.assertEqual(link, site.REPO + "/blob/main/tools/wiki/check.py")


if __name__ == "__main__":
    unittest.main()
