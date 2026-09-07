"""Optional cocotb integration; shared simulation owns execution and records."""
import importlib.metadata
import math
import os
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

from .records import file_hash


def validate(root, target):
    kind = target.get("testbench", "systemverilog")
    if kind not in ("systemverilog", "python"):
        raise ValueError("testbench must be systemverilog or python")
    if kind == "systemverilog":
        if "python" in target:
            raise ValueError("python configuration requires testbench=python")
        return
    config = target.get("python")
    if not isinstance(config, dict) or set(config) != {"module", "test", "inputs"}:
        raise ValueError("python testbench requires module, test and inputs")
    if "driver" in target or "vendor_model" in target or target["expected_exit"] != "zero":
        raise ValueError("python testbench requires zero raw exit and no driver/vendor model")
    if not isinstance(target.get("top"), str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", target["top"]):
        raise ValueError("python top must be an HDL identifier")
    if not all(isinstance(config[k], str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", config[k]) for k in ("module", "test")):
        raise ValueError("python module and test must be identifiers")
    if not isinstance(config["inputs"], list) or not config["inputs"]:
        raise ValueError("python inputs must be a nonempty path list")
    for source in config["inputs"]:
        if not isinstance(source, str):
            raise ValueError("python inputs must be paths")
        path = (root / source).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError(f"missing or out-of-tree Python input: {source}")
    matches = [p for p in config["inputs"] if Path(p).name == config["module"] + ".py"]
    if len(matches) != 1:
        raise ValueError("python inputs must contain exactly one named test module")


def discover():
    """No installs at run time. Hash installed package contents, not just versions."""
    if sys.version_info[:3] != (3, 12, 14):
        raise ValueError("Python TB requires Python 3.12.14; use the isolated src/dv/python environment")
    try:
        from cocotb_tools.config import lib_name_path
        from find_libpython import find_libpython
        packages = {}
        for name, version in (("cocotb", "2.0.1"), ("find-libpython", "0.4.1")):
            dist = importlib.metadata.distribution(name)
            if dist.version != version:
                raise ValueError(f"Python TB requires {name}=={version}")
            files = [Path(dist.locate_file(p)).resolve() for p in dist.files
                     if not str(p).endswith((".pyc", ".pyo"))]
            packages[name] = {"version": version, "files": {str(p): file_hash(p) for p in files if p.is_file()}}
        library = Path(lib_name_path("vpi", "questa")).resolve()
        libpython = Path(find_libpython()).resolve()
        return {"executable": sys.executable, "version": sys.version,
                "executable_sha256": file_hash(Path(sys.executable)),
                "library": str(library), "library_sha256": file_hash(library),
                "libpython": str(libpython), "libpython_sha256": file_hash(libpython),
                "packages": packages}
    except (ImportError, importlib.metadata.PackageNotFoundError, TypeError, OSError) as error:
        raise ValueError("Python TB dependencies unavailable; install src/dv/python/requirements.txt in the pinned environment") from error


def environment(root, target, attempt, seed, runtime):
    # External filters, result locations or seed settings must not alter a target.
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("COCOTB_", "GPI_", "PYGPI_")) and k not in ("PYTHONHOME", "PYTHONPATH", "LIBPYTHON_LOC")}
    config = target["python"]
    module = next(root / p for p in config["inputs"] if Path(p).stem == config["module"])
    env.update(PYTHONPATH=os.pathsep.join([str(module.parent), *[p for p in sys.path if p]]),
               PYGPI_PYTHON_BIN=runtime["executable"], LIBPYTHON_LOC=runtime["libpython"],
               COCOTB_TOPLEVEL=target["top"], COCOTB_TEST_MODULES=config["module"],
               COCOTB_RESULTS_FILE=str(attempt / "results.xml"), COCOTB_RANDOM_SEED=str(seed),
               PYTHONDONTWRITEBYTECODE="1")
    return env


def prepare(target, attempt):
    (attempt / "run.do").write_text(
        "onerror {quit -code 1}\nlog -r /*\nvcd file waves/simulation.vcd\n"
        "vcd add -r /*\nrun -all\nquit -code 0\n", encoding="utf-8")


def classify(output):
    """Explain only Questa's exact classic-access optimization warning."""
    pattern = r"^# \*\* Warning: \(vopt-10908\) Some optimizations are turned off because the \+acc switch is in effect\.$"
    explained = [line for line in output.splitlines() if re.fullmatch(pattern, line)]
    if len(explained) != 1:
        return output, []
    if len(explained) == 1:
        for line in output.splitlines():
            if line in ("# ** Note: (vsim-12126) Error and warning message counts have been restored: Errors=0, Warnings=1.",
                        "# Errors: 0, Warnings: 1"):
                explained.append(line)
    return "\n".join(line for line in output.splitlines() if line not in explained), explained


def results(path, config):
    """Require the single named completed test; never infer PASS from vsim exit."""
    try:
        root = ET.parse(path).getroot()
        suites = list(root)
        tests = list(root.iter("testcase"))
        if root.tag != "testsuites" or len(suites) != 1 or suites[0].tag != "testsuite" or len(tests) != 1:
            raise ValueError("expected exactly one completed Python test")
        if set(root.attrib) - {"name"} or set(suites[0].attrib) - {"name", "package"}:
            raise ValueError("unexpected Python result suite attributes")
        test = tests[0]
        if test not in list(suites[0]) or test.get("name") != config["test"] or test.get("classname") != config["module"]:
            raise ValueError("unexpected Python test identity")
        if set(test.attrib) - {"name", "classname", "file", "lineno", "time", "sim_time_ns", "ratio_time"}:
            raise ValueError("unexpected Python testcase attributes")
        if any(child.tag not in ("property", "testcase") for child in suites[0]):
            raise ValueError("unexpected Python result element")
        for key in ("time", "sim_time_ns"):
            number = float(test.attrib[key])
            if not math.isfinite(number) or number <= 0:
                raise ValueError("incomplete Python test timing")
        if list(test):
            return {"status": "FAIL", "test": config["test"],
                    "diagnostics": [dict(child.attrib, kind=child.tag) for child in test]}
        return {"status": "PASS", "test": config["test"], "sim_time_ns": float(test.attrib["sim_time_ns"])}
    except (OSError, ET.ParseError, ValueError, KeyError) as error:
        return {"status": "FAIL", "error": f"invalid Python results: {error}"}


def evidence(root, record, config):
    """Require the inventory as well as hashes before accepting/reusing success."""
    name = record.get("python_results_file")
    if not isinstance(name, str) or name not in record["artifacts"]:
        return False
    folder = (root / name).parent
    required = [folder / p for p in ("results.xml", "transactions.jsonl", "waves/simulation.vcd", "waves/simulation.wlf", "sim.log", "run.do")]
    return all(p.relative_to(root).as_posix() in record["artifacts"] and p.is_file() and p.stat().st_size > 0 for p in required) and results(root / name, config)["status"] == "PASS"
