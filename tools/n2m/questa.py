"""Questa macro completion and strict transcript checks."""
import re
from .intel_memory import commands as intel_commands


def write_macro(folder):
    # stop retains the reason; -onfinish exit can return zero for $fatal.
    (folder / "run.do").write_text(
        "onbreak {if {[lindex [runStatus -full] 2] eq {$finish}} "
        "{quit -code 0} else {quit -code 1}}\n"
        "onerror {quit -code 1}\nrun -all\nquit -code 1\n",
        encoding="utf-8")


def diagnostic(output, expected_failure=None):
    # A zero-warning summary is not a warning diagnostic.
    if re.search(r"(?im)^.*\bwarnings?\b(?!\s*:\s*0\b).*$", output):
        return "unexplained simulator warning"
    lines = re.findall(r"(?im)^.*\b(?:error|fatal)(?: \([^)]*\))?:.*$", output)
    if any(not (expected_failure and expected_failure in line) for line in lines):
        return "unexpected simulator diagnostic"
    if any(int(count) != (1 if expected_failure else 0)
           for count in re.findall(r"\bErrors:\s*(\d+)", output)):
        return "unexpected simulator error count"
    return None


def commands(simulator, root, target, seed, compiler, attempt, *, prepare=True, vendor_model=None, python_runtime=None):
    tools = simulator.tools
    library = (compiler / "work").as_posix()
    if prepare:
        if python_runtime:
            from .python_tb import prepare as prepare_python
            prepare_python(target, attempt, root)
        else:
            write_macro(attempt)
    vendor_compile, vendor_map, vendor_binding = intel_commands(simulator, compiler, attempt, vendor_model)
    return [
        ([tools["vmap"], "-c"], compiler, compiler / "ini.log", "zero"),
        ([tools["vlib"], "work"], compiler, compiler / "library.log", "zero"),
        ([tools["vmap"], "work", library], compiler, compiler / "map.log", "zero"),
        *vendor_compile,
        ([tools["vlog"], "-sv", "-work", "work", "+incdir+" + simulator.path(root),
          *[simulator.path(root / source) for source in target["sources"]]],
         compiler, compiler / "compile.log", "zero"),
        ([tools["vmap"], "-c"], attempt, attempt / "ini.log", "zero"),
        ([tools["vmap"], "work", library], attempt, attempt / "map.log", "zero"),
        *vendor_map,
        ([tools["vsim"], "-c", "-onfinish", "exit" if python_runtime else "stop", "-wlf", "waves/simulation.wlf",
          *(["-pli", python_runtime["library"], "-no_autoacc", "-voptargs=+acc=rnbp+/" + target["top"]] if python_runtime else []),
          *vendor_binding,
          *(["-voptargs=" + " ".join("-access=rw+/" + target["top"] + "/" + name
              for name in target["driver"].get("access", []))] if target.get("driver", {}).get("access") else []),
          "work." + target["top"], f"+seed={seed}", *target["args"],
          *(["+smoke_root=" + simulator.path(root)] if "driver" in target else []), "-do", "do run.do"],
         attempt, attempt / "sim.log", target["expected_exit"]),
    ]
