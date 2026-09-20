"""Every module in this directory imports on its own, with no earlier module's help.

`check` runs a whole group pattern in one interpreter, so the first module to put
the repository's `tools/` directory on `sys.path` repairs it for every module
imported after it. A module that never does so of its own accord still passes
inside its group, and fails the moment someone runs it alone to look at a
failure, or if the group ranges are rebalanced so that module leads. Nothing in
the group run can see that dependency, because the group run is what hides it.

So it is checked where it is observable: one fresh interpreter per module, with
no inherited `PYTHONPATH`, loading exactly that module the way
`unittest discover` does. The list of modules is the directory itself, never a
table, so a module added tomorrow is checked without anyone remembering to
enrol it.
"""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
# Derived, never spelled: a literal repository path here would be an undeclared input.
ROOT = HERE.parents[2]
TOOLS = HERE.parents[1]
# Loads one module exactly as `unittest discover -s <dir> -p <module>` does, and reports only
# whether it loaded: `discover` turns an import failure into a placeholder test, so the loader's
# own error list is the one place an unimportable module is still visible as an import failure.
PROBE = ("import sys, unittest\n"
         "loader = unittest.TestLoader()\n"
         "loader.discover(start_dir=sys.argv[1], pattern=sys.argv[2])\n"
         "for error in loader.errors:\n"
         "    print(error.strip().splitlines()[-1])\n"
         "sys.exit(1 if loader.errors else 0)\n")
# The probes are independent processes, so they overlap. Each one spends much of its life
# starting an interpreter and reading source, so twice the core count shortens this unit's
# wall without spending more CPU: on a four-core host, 13 to 21 s of wall for the same 25 to
# 40 s of CPU, the spread being load and whether the tree holds bytecode caches, since these
# run -B. Capped, because the sibling check groups are running beside it.
WORKERS = min(8, 2 * (os.cpu_count() or 1))


def probe(start_dir, pattern):
    """Load `pattern` in a fresh interpreter under `start_dir`; returns (ok, last error line).

    The child gets a deliberately bare environment. Inheriting `PYTHONPATH` would
    hand it the `tools/` entry whose absence is the whole point, and inheriting the
    closure tracer would charge every probed module's reads to this unit instead of
    to the unit that declares them.
    """
    environment = {key: value for key, value in os.environ.items()
                   if key not in ("PYTHONPATH", "N2M_TRACE_LOG", "N2M_TRACE_ROOT")}
    result = subprocess.run([sys.executable, "-B", "-c", PROBE, start_dir, pattern],
                            cwd=str(ROOT), env=environment, text=True, timeout=120,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.returncode == 0, (result.stdout or "").strip().splitlines()[-1:]


class StandaloneImports(unittest.TestCase):
    def test_every_module_in_this_directory_imports_in_a_fresh_interpreter(self):
        names = sorted(path.name for path in HERE.glob("test_*.py"))
        self.assertIn(Path(__file__).name, names)
        with ThreadPoolExecutor(WORKERS) as pool:
            outcomes = list(pool.map(lambda name: probe(str(HERE), name), names))
        broken = {name: reason for name, (ok, reason) in zip(names, outcomes) if not ok}
        self.assertEqual(broken, {}, "these modules need another module imported first: "
                                     + "; ".join(f"{name}: {reason}" for name, reason in broken.items()))

    def test_the_probe_fails_a_module_that_depends_on_an_earlier_import(self):
        # The witness for the check above: the same probe, on a module written both ways.
        base = ROOT / "workdir/builds/standalone-import-unit-tests"
        base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="space ", dir=base) as temp:
            directory = Path(temp)
            (directory / "test_undeclared.py").write_text("from n2m import records\n", encoding="utf-8")
            (directory / "test_repaired.py").write_text(
                f"import sys\nsys.path.insert(0, {str(TOOLS)!r})\nfrom n2m import records\n",
                encoding="utf-8")
            ok, reason = probe(str(directory), "test_undeclared.py")
            self.assertFalse(ok, reason)
            self.assertEqual(reason, ["ModuleNotFoundError: No module named 'n2m'"])
            self.assertEqual(probe(str(directory), "test_repaired.py"), (True, []))


if __name__ == "__main__":
    unittest.main()
