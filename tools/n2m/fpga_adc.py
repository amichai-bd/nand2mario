"""Resolve the installed ADC control core and generate its dedicated PLL."""
from pathlib import Path
import shutil

from .records import file_hash
from . import fpga_pll

CONTROL = (
    "altera_modular_adc_control.v", "altera_modular_adc_control_fsm.v",
    "altera_modular_adc_control_avrg_fifo.v", "chsel_code_converter_sw_to_hw.v",
    "fiftyfivenm_adcblock_top_wrapper.v", "fiftyfivenm_adcblock_primitive_wrapper.v",
    "altera_modular_adc_control.sdc",
)


def identity(directory):
    quartus = Path(directory).resolve().parent
    ip = quartus.parent / "ip/altera"
    paths = {name: ip / "altera_modular_adc/control" / name for name in CONTROL}
    paths["altera_std_synchronizer.v"] = ip / "primitives/altera_std_synchronizer/altera_std_synchronizer.v"
    paths["control_definition"] = ip / "altera_modular_adc/control/altera_modular_adc_control_hw.tcl"
    paths["core_definition"] = ip / "altera_modular_adc/top/altera_modular_adc_hw.tcl"
    paths["atom_model"] = quartus / "eda/sim_lib/fiftyfivenm_atoms.v"
    paths["generator"] = Path(directory) / "qmegawiz.exe"
    paths["pll_definition"] = quartus / "libraries/megafunctions/altpll.tdf"
    if any(not p.is_file() for p in paths.values()):
        raise ValueError("missing installed Intel ADC/PLL dependency")
    result = {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}
    result.update({"pll_" + name: value for name, value in fpga_pll.identity(directory).items()})
    return result


def generate(folder, sources, execute, timeout, record, build):
    for name in (*CONTROL, "altera_std_synchronizer.v"):
        source = Path(sources[name]["path"])
        if file_hash(source) != sources[name]["sha256"]:
            raise ValueError("Intel ADC dependency changed before generation")
        shutil.copyfile(source, folder / name)
    command = [sources["generator"]["path"], "-silent", "module=altpll",
               "INTENDED_DEVICE_FAMILY=MAX 10", "INCLK0_INPUT_FREQUENCY=100000",
               "CLK0_MULTIPLY_BY=1", "CLK0_DIVIDE_BY=1", "CLK0_DUTY_CYCLE=50",
               "CLK0_PHASE_SHIFT=0", "COMPENSATE_CLOCK=CLK0", "OPERATION_MODE=NORMAL",
               "areset=used", "locked=used", "clk0=used", "OPTIONAL_FILES=NONE", "n2m_adc_pll.v"]
    execute(command, folder, folder / "generate-adc-pll.log", timeout, record, build)


def assignments():
    return [f'set_global_assignment -name VERILOG_FILE {name}'
            for name in (*CONTROL[:-1], "altera_std_synchronizer.v", "n2m_adc_pll.v")] + [
                "set_global_assignment -name SDC_FILE altera_modular_adc_control.sdc"]
