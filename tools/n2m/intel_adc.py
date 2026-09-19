"""Installed Intel ADC/PLL model for the physical-controls proof."""
import hashlib
import json
from pathlib import Path
import re

from . import fpga_adc, vendor_sources
from .records import file_hash

LIBRARY = "n2m_intel_adc"
ATOMS_LIBRARY = "n2m_intel_adc_atoms"
TOP_SOURCE = "ip/altera/altera_modular_adc/control/fiftyfivenm_adcblock_top_wrapper.v"


def resolve(root, simulator, directory=None):
    if directory is None:
        installation = Path(simulator.tools["vsim"]).resolve().parents[2]
        folder = installation / "quartus/eda/sim_lib"
    else:
        folder = Path(directory).resolve()
        installation = folder.parents[2]
    pin = json.loads((root / "tools/n2m/dependencies.json").read_text())["intel_adc"]
    for name in pin["sources"]:
        path = installation / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("missing installed Intel ADC source: " + name)
    provenance = vendor_sources.check(installation, {name: installation / name for name in pin["sources"]})
    sources = [{"name": name, **provenance[name]} for name in pin["sources"]]
    # The executables directory is quartus/bin64 on Windows and quartus/bin on
    # Linux, so the installation names its own layout instead of this line
    # encoding one platform's.
    generation = fpga_adc.identity(vendor_sources.executables(installation))
    return {"selection": "intel-adc", "library": LIBRARY, "version": pin["version"],
            "sources": sources, "generation_inputs": generation,
            "generation_command": fpga_adc.generation_command(generation),
            "binding_options": ["-L", LIBRARY, "-L", ATOMS_LIBRARY], "mixed_mode_instances": [],
            "stimulus": stimulus_manifest()}


def stimulus_manifest():
    # Original test voltages, not measured hardware or redistributed vendor data.
    files = {f"adc_ch{i}.txt": "0 " + ({1: "0.625", 2: "1.25"}.get(i, "0.0")) + "\n"
             for i in range(17)}
    return {"enable_usr_sim": 1, "reference_voltage_sim": 49648,
            "files": {name: {"text": text, "sha256": hashlib.sha256(text.encode("ascii")).hexdigest()}
                      for name, text in files.items()}}


def write_stimulus(attempt):
    """Write the original voltage fixture for the ADC control double under Verilator.

    The double reads adc_ch0.txt to adc_ch16.txt from the run directory; a
    file already holding the fixture text is left as it is.
    """
    for name, entry in stimulus_manifest()["files"].items():
        path = Path(attempt) / name
        if path.is_file() and path.read_text(encoding="ascii") == entry["text"]:
            continue
        if path.exists():
            raise ValueError("ADC stimulus path already exists")
        path.write_text(entry["text"], encoding="ascii")


def prepare_stimulus(attempt, descriptor):
    if descriptor.get("stimulus") != stimulus_manifest():
        raise ValueError("ADC stimulus descriptor differs from the original voltage fixture")
    for name, entry in descriptor["stimulus"]["files"].items():
        path = attempt / name
        data = entry["text"].encode("ascii")
        if path.exists():
            raise ValueError("ADC stimulus path already exists")
        path.write_bytes(data)
        if file_hash(path) != entry["sha256"]:
            raise ValueError("ADC stimulus file hash differs")


def reject_shadow_models(root, inputs):
    names = ("altera_modular_adc_control", "altera_modular_adc_control_fsm",
             "altera_modular_adc_control_avrg_fifo", "chsel_code_converter_sw_to_hw",
             "fiftyfivenm_adcblock_top_wrapper", "fiftyfivenm_adcblock_primitive_wrapper",
             "altera_std_synchronizer", "fiftyfivenm_adcblock", "fiftyfivenm_adcblock_encrypted",
             "fiftyfivenm_pll", "altpll", "n2m_adc_pll", "n2m_pixel_pll", "n2m_system_pll")
    for name in inputs:
        text = (root / name).read_text()
        text = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", " ", text)
        if re.search(r"\bmodule\s+(?:automatic\s+)?(?:" + "|".join(names) + r")\b", text):
            raise ValueError("repository source shadows installed ADC/PLL model: " + name)


def commands(simulator, compiler, attempt, descriptor):
    prepare_stimulus(attempt, descriptor)
    tools = simulator.tools
    library = descriptor["library"]
    path = (compiler / library).as_posix()
    atoms_path = (compiler / ATOMS_LIBRARY).as_posix()
    atoms = [source["path"] for source in descriptor["sources"] if source["name"].startswith("quartus/eda/sim_lib/")]
    control = [source["path"] for source in descriptor["sources"] if not source["name"].startswith("quartus/eda/sim_lib/")]
    return [
        (descriptor["generation_command"], compiler, compiler / "adc-pll-generate.log", "zero"),
        ([tools["vlib"], ATOMS_LIBRARY], compiler, compiler / "intel-adc-atoms-library.log", "zero"),
        ([tools["vmap"], ATOMS_LIBRARY, atoms_path], compiler, compiler / "intel-adc-atoms-map.log", "zero"),
        ([tools["vlog"], "-work", ATOMS_LIBRARY, *atoms], compiler, compiler / "intel-adc-atoms-compile.log", "zero"),
        ([tools["vlib"], library], compiler, compiler / "intel-adc-library.log", "zero"),
        ([tools["vmap"], library, path], compiler, compiler / "intel-adc-map.log", "zero"),
        ([tools["vlog"], "-work", library, *control, str(compiler / "n2m_adc_pll.v")],
         compiler, compiler / "intel-adc-control-compile.log", "zero"),
    ], [([tools["vmap"], library, path], attempt, attempt / "intel-adc-map.log", "zero"),
        ([tools["vmap"], ATOMS_LIBRARY, atoms_path], attempt, attempt / "intel-adc-atoms-map.log", "zero")], descriptor["binding_options"]


def classify_compile_diagnostics(output, descriptor, stage):
    """Explain only the unchanged wrapper's extra CR around its timescale."""
    if stage != "intel-adc-control-compile.log":
        raise ValueError("ADC lexical diagnostic is only valid in the control compilation stage")
    records = {source["name"]: source for source in descriptor["sources"]}
    wrapper = vendor_sources.require_accepted(records, TOP_SOURCE)[TOP_SOURCE]
    expected = ("** Warning: (vlog-2083) " + records[TOP_SOURCE]["path"] +
                "(24): Carriage return (0x0D) is not followed by a newline (0x0A).")
    lines = output.splitlines()
    warnings = [line for line in lines if re.search(r"\bWarning:", line)]
    summaries = [line for line in lines if re.fullmatch(r"Errors: \d+, Warnings: \d+", line)]
    if warnings != [expected] or summaries != ["Errors: 0, Warnings: 1"]:
        raise ValueError("ADC lexical diagnostic count, location, or summary differs")
    # Raw stdout/logs remain intact. Only the strict generic check receives this
    # classified view; the one actual compiler warning stays visible in evidence.
    checked = "\n".join("Errors: 0, Warnings: 0" if line == summaries[0] else line
                        for line in lines if line != expected)
    return checked, [{"id": "intel-adc-wrapper-lone-cr", "raw": expected,
                      "raw_summary": summaries[0], "warning_count": 1,
                      "source_sha256": wrapper,
                      "reason": "Accepted wrapper bytes1380/1403 contain CR-CR-LF around the timescale; no HDL tokens change."}]


def verify_generated(folder):
    fpga_adc.verify_generated(folder)
    return {"path": str(folder / "n2m_adc_pll.v"), "sha256": file_hash(folder / "n2m_adc_pll.v"),
            "parameters_verified": True}


def classify_sim_diagnostics(output, descriptor, *, python_access=False):
    """Keep the exact accepted ADC model's elaboration diagnostics visible.

    The same profile occurs with 50 MHz and 25 MHz control clocks. The FIFO
    leaves its unused ECC output open. The encrypted vendor model also emits
    seven internal width and nine ignored $rewind-return diagnostics. They do
    not describe a product port connection; their hidden widths cannot be
    inspected. Actual sample/channel/lock tests and fitted boundary checks
    remain required. Any changed message, source, count or extra warning fails.
    """
    names = ("quartus/eda/sim_lib/mentor/fiftyfivenm_atoms_ncrypt.v",
             "ip/altera/altera_modular_adc/control/altera_modular_adc_control_avrg_fifo.v")
    records = {source["name"]: source for source in descriptor["sources"]}
    pins = vendor_sources.require_accepted(records, *names)
    atom, fifo = (records[name]["path"] for name in names)
    expected = [f"# ** Warning: {atom}(38): (vopt-2241) Connection width does not match width of port '<protected>'.<protected>"] * 7
    expected += [f"# ** Warning: {fifo}(79): (vopt-2685) [TFMPC] - Too few port connections for 'scfifo_component'.  Expected 13, found 12.",
                 f"# ** Warning: {fifo}(79): (vopt-2718) [TFMPC] - Missing connection for port 'eccstatus'."]
    expected += [f"# ** Warning: {atom}(38): (vopt-PLI-3691) Expected a system task, not a system function '$rewind'."] * 9
    if python_access:
        expected.insert(0, "# ** Warning: (vopt-10908) Some optimizations are turned off because the +acc switch is in effect.")
    count = 19 if python_access else 18
    lines = output.splitlines()
    warnings = [line for line in lines if re.search(r"\bWarning:", line)]
    restored = f"# ** Note: (vsim-12126) Error and warning message counts have been restored: Errors=0, Warnings={count}."
    summaries = [line for line in lines if re.fullmatch(r"# Errors: \d+, Warnings: \d+", line)]
    if warnings != expected or lines.count(restored) != 1 or len(summaries) != 1 or not re.fullmatch(rf"# Errors: [01], Warnings: {count}", summaries[0]):
        raise ValueError("ADC simulation diagnostic profile differs")
    checked = "\n".join(line.replace(f"Warnings: {count}", "Warnings: 0") if line == summaries[0] else line
                        for line in lines if line not in expected and line != restored)
    return checked, [{"id": "intel-adc-pinned-elaboration", "raw": warnings,
                      "raw_summary": summaries[0], "raw_restored": restored,
                      "sources": pins, "warning_count": count, "python_access": python_access,
                      "reason": "Unchanged 50/25 MHz vendor profile: unused FIFO ECC output, encrypted model widths and ignored rewind returns; sample/channel/lock and fitted boundary checks remain required."}]
