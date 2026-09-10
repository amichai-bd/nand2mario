"""Optional cocotb integration; shared simulation owns execution and records."""
import importlib.metadata
import math
import os
from pathlib import Path
import re
import sys
import subprocess
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
    if not isinstance(config, dict) or not {"module", "test", "inputs"} <= set(config) or set(config) - {"module", "test", "inputs", "waves"}:
        raise ValueError("python testbench requires module, test and inputs")
    if "waves" in config:
        waves = config["waves"]
        if not isinstance(waves, list) or not waves or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in waves) or len(set(waves)) != len(waves):
            raise ValueError("Python waves require unique public top-level signal names")
    if "driver" in target or target["expected_exit"] != "zero":
        raise ValueError("python testbench requires zero raw exit and no driver")
    if target.get("vendor_model") not in (None, "intel-memory", "intel-controls"):
        raise ValueError("Python testbench requires supported Intel memory or controls models")
    if target.get("preload") not in (None, "integration", "v05", "palette-fc", "palette-00", "startup-read", "startup-write", "vram-read", "vram-write", "late-fe9c", "late-fe9d", "late-fe20", "timer234", "dma239", "display308", "oam299", "oam299-s", "courier292", "courier292-s", "hud300", "hud300-s", "hud-render300", "motion301", "motion301-s", "springtrail", "springtrail-unit", "flow", "flow-s", "render", "render-s", "stackdrop", "stackdrop-unit", "stackdrop-short", "mooneye-reg-f"):
        raise ValueError("unknown Python preload")
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
    if target.get("preload") in ("integration", "v05", "palette-fc", "palette-00", "startup-read", "startup-write", "vram-read", "vram-write", "late-fe9c", "late-fe9d", "late-fe20", "timer234", "dma239", "display308", "oam299", "oam299-s", "courier292", "courier292-s", "hud300", "hud300-s", "hud-render300", "motion301", "motion301-s", "springtrail", "springtrail-unit", "flow", "flow-s", "render", "render-s", "stackdrop", "stackdrop-unit", "stackdrop-short"):
        required = {"src/dv/integration/image.py", "src/dv/integration/program.asm",
                    "src/dv/integration/program.json", "src/dv/integration/retirement.json",
                    "src/sw/generated/interfaces.inc"}
        if target['preload'] in ('motion301', 'motion301-s'):
            required = {'src/dv/springtrail/motion_program.py', 'src/dv/springtrail/motion_cases.py',
                        'src/dv/springtrail/motion_reference.py', 'src/sw/generated/interfaces.inc',
                        'src/sw/springtrail/layout.json', 'src/sw/springtrail/assets/core/core-tiles.json'}
            required.update(p.relative_to(root).as_posix() for p in (root/'src/sw/springtrail').glob('*.asm'))
        if target['preload'] == 'hud-render300':
            required = {'src/dv/springtrail/hud_render_program.py','src/sw/generated/interfaces.inc','src/sw/springtrail/layout.json','src/sw/springtrail/assets/core/core-tiles.json'}
            required.update(p.relative_to(root).as_posix() for p in (root/'src/sw/springtrail').glob('*.asm'))
        if target['preload'] in ('hud300','hud300-s'):
            required = {'src/dv/springtrail/hud_program.py','src/dv/springtrail/hud_unit_cases.py',
                        'src/sw/generated/interfaces.inc','src/sw/springtrail/layout.json',
                        'src/sw/springtrail/assets/core/core-tiles.json'}
            required.update(p.relative_to(root).as_posix() for p in (root/'src/sw/springtrail').glob('*.asm'))
        if target['preload'] in ('courier292','courier292-s'):
            required = {'src/dv/springtrail/composition_program.py', 'src/dv/springtrail/composition_cases.py',
                        'src/sw/generated/interfaces.inc'}
            required.update(p.relative_to(root).as_posix() for p in (root/'src/sw/springtrail').glob('*.asm'))
            required.add('src/sw/springtrail/layout.json')
        if target["preload"] in ("oam299", "oam299-s"):
            required = {"src/dv/springtrail/dma_program.py", "src/sw/springtrail/oam_dma.asm", "src/sw/generated/interfaces.inc"}
        if target["preload"] == "display308":
            required = {"src/dv/display308/program.py", "src/sw/generated/interfaces.inc"}
        if target["preload"] == "dma239":
            required = {"src/dv/dma/program239.py", "src/sw/generated/interfaces.inc"}
        if target["preload"] == "timer234":
            required = {"src/dv/timer/program234.py", "src/sw/generated/interfaces.inc"}
        if target["preload"] == "v05":
            required = {"src/sw/v05/main.asm", "src/sw/v05/layout.json", "src/sw/generated/interfaces.inc"}
        if target["preload"] in ("springtrail", "springtrail-unit", "flow", "flow-s", "render", "render-s", "stackdrop", "stackdrop-unit", "stackdrop-short"):
            required = {"src/sw/targets.json", "src/sw/generated/interfaces.inc", "cfg/interfaces.json"}
            required.update(p.relative_to(root).as_posix() for p in (root / "src/sw" / ("stackdrop" if target["preload"].startswith("stackdrop") else "springtrail")).iterdir()
                            if p.suffix in (".asm", ".json"))
        if target['preload'].startswith('startup-'):
            required = {'src/dv/ppu/startup202.py', 'src/sw/generated/interfaces.inc'}
        if target['preload'].startswith('late-'):
            required = {'src/dv/ppu/late208.py', 'src/sw/generated/interfaces.inc'}
        if target['preload'].startswith('vram-'):
            required = {'src/dv/ppu/startup204.py', 'src/sw/generated/interfaces.inc'}
        if target['preload'].startswith('palette-'):
            required.update({'src/dv/ppu/palette194.py','src/dv/ppu/palette194.json'})
            required.update(p.relative_to(root).as_posix() for p in (root/'src/dv/sameboy').iterdir() if p.suffix in ('.py','.c','.json','.patch'))
        required.update(p.relative_to(root).as_posix() for p in (root / "tools/sw").glob("*")
                        if p.suffix in (".py", ".json"))
        if target.get("vendor_model") not in ("intel-memory", "intel-controls") or not required <= set(config["inputs"]):
            raise ValueError("preload requires Intel memory and all software image inputs")
    if target.get('preload') == 'mooneye-reg-f':
        required = {'src/dv/mooneye/pins.json', 'src/dv/mooneye/THIRD_PARTY.md',
                    'src/rtl/ppu/GPL-3.0.txt'}
        if target.get('vendor_model') != 'intel-memory' or not required <= set(config['inputs']):
            raise ValueError('Mooneye preload requires Intel memory and pinned source notices')


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
           if not k.startswith(("COCOTB_", "GPI_", "PYGPI_", "PYTHON")) and k != "LIBPYTHON_LOC"}
    config = target["python"]
    module = next(root / p for p in config["inputs"] if Path(p).stem == config["module"])
    prefixes = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
    runtime_paths = [p for p in sys.path if p and any(Path(p).resolve().is_relative_to(base) for base in prefixes)]
    env.update(PYTHONPATH=os.pathsep.join([str(module.parent), *runtime_paths]),
               PYGPI_PYTHON_BIN=runtime["executable"], LIBPYTHON_LOC=runtime["libpython"],
               COCOTB_TOPLEVEL=target["top"], COCOTB_TEST_MODULES=config["module"],
               COCOTB_RESULTS_FILE=str(attempt / "results.xml"), COCOTB_RANDOM_SEED=str(seed),
               PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONOPTIMIZE="0")
    return env


def prepare(target, attempt, root=None, fixture_tools=None):
    if target.get('preload') == 'mooneye-reg-f':
        from .mooneye import prepare as prepare_mooneye
        prepare_mooneye(root, attempt, fixture_tools)
    if target.get("preload") in ("integration", "v05", "palette-fc", "palette-00", "startup-read", "startup-write", "vram-read", "vram-write", "late-fe9c", "late-fe9d", "late-fe20", "timer234", "dma239", "display308", "oam299", "oam299-s", "courier292", "courier292-s", "hud300", "hud300-s", "hud-render300", "motion301", "motion301-s", "springtrail", "springtrail-unit", "flow", "flow-s", "render", "render-s", "stackdrop", "stackdrop-unit", "stackdrop-short"):
        import hashlib
        import importlib.util
        from .preload import prepare as prepare_preload, verify
        if target["preload"] in ("v05", "springtrail", "springtrail-unit", "flow", "flow-s", "render", "render-s", "stackdrop", "stackdrop-unit", "stackdrop-short"):
            from types import SimpleNamespace
            from sw.rom_build import build_target
            from .records import git_state
            report = build_target(root, attempt / "sw",
                                  SimpleNamespace(target=target["preload"], rebuild=True), git_state(root))
            if report["status"] != "PASS":
                raise ValueError("v05 preload software build failed")
            image = (root / report["rom"]).read_bytes()
            expected_sha = report["artifacts"][report["rom"]]
            (attempt / "program.gb").write_bytes(image)
        elif target['preload'] in ('motion301', 'motion301-s'):
            spec=importlib.util.spec_from_file_location('motion301_image',root/'src/dv/springtrail/motion_program.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload']=='motion301-s')
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] == 'hud-render300':
            spec=importlib.util.spec_from_file_location('hud_render300_image',root/'src/dv/springtrail/hud_render_program.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            image=module.build(root,attempt)
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] in ('hud300','hud300-s'):
            spec=importlib.util.spec_from_file_location('hud300_image',root/'src/dv/springtrail/hud_program.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload']=='hud300-s')
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] in ('courier292','courier292-s'):
            spec=importlib.util.spec_from_file_location('courier292_image',root/'src/dv/springtrail/composition_program.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload']=='courier292-s')
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] in ('oam299','oam299-s'):
            spec=importlib.util.spec_from_file_location('oam299_image',root/'src/dv/springtrail/dma_program.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload']=='oam299-s')
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] == 'display308':
            spec=importlib.util.spec_from_file_location('display308_image',root/'src/dv/display308/program.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt)
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] == 'dma239':
            spec=importlib.util.spec_from_file_location('dma239_image',root/'src/dv/dma/program239.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt)
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'] == 'timer234':
            spec=importlib.util.spec_from_file_location('timer234_image',root/'src/dv/timer/program234.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt)
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'].startswith('startup-'):
            spec=importlib.util.spec_from_file_location('startup202_image',root/'src/dv/ppu/startup202.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload'].split('-')[1])
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'].startswith('late-'):
            spec=importlib.util.spec_from_file_location('late208_image',root/'src/dv/ppu/late208.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload'].split('-')[1])
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'].startswith('vram-'):
            spec=importlib.util.spec_from_file_location('startup204_image',root/'src/dv/ppu/startup204.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,target['preload'].split('-')[1])
            expected_sha=hashlib.sha256(image).hexdigest()
        elif target['preload'].startswith('palette-'):
            spec=importlib.util.spec_from_file_location('palette194_image',root/'src/dv/ppu/palette194.py')
            module=importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image=module.build(root,attempt,int(target['preload'][-2:],16))
            expected_sha=hashlib.sha256(image).hexdigest()
            command=[sys.executable,'-X','utf8','-B',str(root/'src/dv/sameboy/probe.py'),
                     '--case',target['preload'],'--source',str(root/'workdir/research/sameboy/source'),
                     '--rom',str(attempt/'program.gb'),'--output',str(attempt/'reference')]
            with (attempt/'reference-build.log').open('w') as output:
                subprocess.run(command,cwd=root,stdout=output,stderr=subprocess.STDOUT,timeout=300,check=True)
        else:
            spec = importlib.util.spec_from_file_location("integration_image", root / "src/dv/integration/image.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            image = module.build(root, attempt)
            expected_sha = hashlib.sha256(image).hexdigest()
        prepare_preload(image, expected_sha, attempt)
        verify(attempt)
    wave_paths = " ".join(f"/{target['top']}/{name}" for name in target.get("python", {}).get("waves", [])) or "/*"
    (attempt / "run.do").write_text(
        f"onerror {{quit -code 1}}\nlog {wave_paths}\nvcd file waves/simulation.vcd\n"
        f"vcd add {wave_paths}\nrun -all\nquit -code 0\n", encoding="utf-8")


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
