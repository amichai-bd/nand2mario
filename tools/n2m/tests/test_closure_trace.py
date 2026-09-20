"""The dynamic closure tracer names reads outside a declared closure, on a fixture tree."""
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import catalogue, closure_trace, host_closure

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


# Spends its own CPU until it has spent that much, however fast or busy the host is.
BURN = ("import time, unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_burn(self):\n"
        "        deadline = time.process_time() + 2.0\n"
        "        while time.process_time() < deadline:\n            pass\n")
# Blocks inside a child it waits for, so that child holds the traced unit's own stdout
# pipe. Killing the unit alone leaves the pipe open, which the ceiling has to survive.
WAIT_IN_CHILD = ("import subprocess, sys, unittest\n"
                 "class T(unittest.TestCase):\n"
                 "    def test_wait(self):\n"
                 "        subprocess.run([sys.executable, '-c', 'import time; time.sleep(60)'])\n")


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

    def test_a_traced_unit_that_grows_past_its_cpu_budget_fails(self):
        """The trace gives a unit the same bound the catalogue runner does, so growth that
        fails a run fails a trace. Tracing itself adds an audit hook to every interpreter
        the unit starts, so its CPU is the unit's plus that hook's, never less."""
        self.write(UNIT, BURN)
        with patch.object(catalogue, "UNIT_CPU_BUDGET", 1):
            outcome, _, _ = self.trace([])
        self.assertEqual(outcome["status"], "FAIL", outcome)
        self.assertGreater(outcome["cpu_seconds"], 1)
        self.assertRegex(outcome["error"], r"^unit used \d+ s of CPU, over its 1-second CPU budget$")
        # The same unit inside a budget that covers it passes, so the bound is what failed it.
        self.assertEqual(self.trace([])[0]["status"], "PASS")

    def test_a_traced_unit_that_stops_making_progress_fails_on_the_wall_ceiling(self):
        self.write(UNIT, WAIT_IN_CHILD)
        started = time.monotonic()
        with patch.object(catalogue, "UNIT_CPU_BUDGET", 1), \
                patch.object(catalogue, "UNIT_WALL_STRETCH", 1):
            outcome, _, _ = self.trace([])
        elapsed = time.monotonic() - started
        self.assertEqual(outcome["status"], "FAIL", outcome)
        self.assertEqual(outcome["error"], "unit made no progress past its wall ceiling")
        # Well under the 60 s the abandoned descendant still has to run.
        self.assertLess(elapsed, 30, f"the ceiling waited {elapsed:.1f} s on a held pipe")

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
