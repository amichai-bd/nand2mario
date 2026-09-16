"""The dynamic closure tracer names reads outside a declared closure, on a fixture tree."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import closure_trace, host_closure

ROOT = Path(__file__).resolve().parents[3]
UNIT = "src/x/test_unit.py"
# Reads its data through a bare string path from the repository root: invisible to the static guard.
READER = ("import json, os, unittest\n"
          "class T(unittest.TestCase):\n"
          "    def test_reads(self):\n"
          "        os.listdir('src')\n"
          "        json.load(open('src/x/data.json'))\n"
          "        json.load(open('src/x/scratch.json'))\n"
          "        open('tools/shared.txt').read()\n")


class Tracer(unittest.TestCase):
    def setUp(self):
        base = ROOT / "workdir/builds/closure-trace-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="space ", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write(UNIT, READER)
        self.write("src/x/data.json", "{}\n")
        self.write("src/x/scratch.json", "{}\n")
        self.write("tools/shared.txt", "shared\n")
        self.tracked = {UNIT, "src/x/data.json", "tools/shared.txt"}
        self.tracer = closure_trace.install(self.root / "workdir/tracer")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def trace(self, inputs):
        entry = {"kind": "unit", "labels": [], "inputs": inputs}
        outcome, accessed, popen = closure_trace.trace_unit(self.root, UNIT, entry, self.tracer,
                                                            self.root / "workdir/trace.log")
        closure = host_closure.closure(self.root, UNIT, entry, {}, {},
                                       lambda d: [p for p in self.tracked if p.startswith(d + "/")])
        return outcome, accessed, closure_trace.misses(self.root, entry, closure, accessed, self.tracked)

    def test_an_undeclared_content_read_is_a_miss_and_a_declaration_clears_it(self):
        outcome, accessed, misses = self.trace([])
        self.assertEqual(outcome["status"], "PASS", outcome)
        self.assertEqual(misses, {"src/x/data.json": ["open"]})
        self.assertIn("list", accessed["src"])
        self.assertEqual(self.trace(["src/x/data.json"])[2], {})
        self.assertEqual(self.trace(["src/x"])[2], {})

    def test_listings_untracked_files_and_global_fallback_reads_are_not_misses(self):
        _, accessed, misses = self.trace(["src/x/data.json"])
        self.assertIn("src/x/scratch.json", accessed)
        self.assertIn("tools/shared.txt", accessed)
        self.assertEqual(misses, {})

    def test_a_failing_unit_is_reported_with_its_first_failure(self):
        self.write(UNIT, READER.replace("os.listdir('src')", "self.fail('broken')"))
        outcome, _, _ = self.trace(["src/x/data.json"])
        self.assertEqual(outcome["status"], "FAIL")
        self.assertTrue(outcome["error"].startswith("FAIL: test_reads"), outcome["error"])


if __name__ == "__main__":
    unittest.main()
