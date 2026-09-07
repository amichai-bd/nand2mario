"""Pinned installed Intel ADC/PLL model for the physical-controls proof."""
import json
from pathlib import Path
import re

from . import fpga_adc
from .records import file_hash

LIBRARY = "n2m_intel_adc"


def resolve(root, simulator, directory=None):
    if directory is None:
        installation = Path(simulator.tools["vsim"]).resolve().parents[2]
        folder = installation / "quartus/eda/sim_lib"
    else:
        folder = Path(directory).resolve()
        installation = folder.parents[2]
    pin = json.loads((root / "tools/n2m/dependencies.json").read_text())["intel_adc"]
    sources = []
    for name, expected in pin["sources"].items():
        path = installation / name
        if not path.is_file() or path.is_symlink() or file_hash(path) != expected:
            raise ValueError("missing or unsupported installed Intel ADC source: " + name)
        sources.append({"name": name, "path": str(path), "sha256": expected})
    generation = fpga_adc.identity(installation / "quartus/bin64")
    return {"selection": "intel-adc", "library": LIBRARY, "version": pin["version"],
            "sources": sources, "generation_inputs": generation,
            "generation_command": fpga_adc.generation_command(generation),
            "binding_options": ["-L", LIBRARY], "mixed_mode_instances": []}


def reject_shadow_models(root, inputs):
    names = ("altera_modular_adc_control", "altera_modular_adc_control_fsm",
             "altera_modular_adc_control_avrg_fifo", "chsel_code_converter_sw_to_hw",
             "fiftyfivenm_adcblock_top_wrapper", "fiftyfivenm_adcblock_primitive_wrapper",
             "altera_std_synchronizer", "fiftyfivenm_adcblock", "fiftyfivenm_adcblock_encrypted",
             "fiftyfivenm_pll", "altpll", "n2m_adc_pll")
    for name in inputs:
        text = (root / name).read_text()
        text = re.sub(r"//[^\n]*|/\*[\s\S]*?\*/", " ", text)
        if re.search(r"\bmodule\s+(?:automatic\s+)?(?:" + "|".join(names) + r")\b", text):
            raise ValueError("repository source shadows installed ADC/PLL model: " + name)


def commands(simulator, compiler, attempt, descriptor):
    tools = simulator.tools
    library = descriptor["library"]
    path = (compiler / library).as_posix()
    return [
        (descriptor["generation_command"], compiler, compiler / "adc-pll-generate.log", "zero"),
        ([tools["vlib"], library], compiler, compiler / "intel-adc-library.log", "zero"),
        ([tools["vmap"], library, path], compiler, compiler / "intel-adc-map.log", "zero"),
        ([tools["vlog"], "-work", library,
          *[source["path"] for source in descriptor["sources"]], str(compiler / "n2m_adc_pll.v")],
         compiler, compiler / "intel-adc-compile.log", "zero"),
    ], [([tools["vmap"], library, path], attempt, attempt / "intel-adc-map.log", "zero")], descriptor["binding_options"]


def verify_generated(folder):
    fpga_adc.verify_generated(folder)
    return {"path": str(folder / "n2m_adc_pll.v"), "sha256": file_hash(folder / "n2m_adc_pll.v"),
            "parameters_verified": True}
