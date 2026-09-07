"""Resolve the installed ADC control core and generate its dedicated PLL."""
from pathlib import Path
import shutil
import re

from .records import file_hash
from . import fpga_pll

CONTROL = (
    "altera_modular_adc_control.v", "altera_modular_adc_control_fsm.v",
    "altera_modular_adc_control_avrg_fifo.v", "chsel_code_converter_sw_to_hw.v",
    "fiftyfivenm_adcblock_top_wrapper.v", "fiftyfivenm_adcblock_primitive_wrapper.v",
    "altera_modular_adc_control.sdc",
)
SUPPORTED_CONTROL = {
    "altera_modular_adc_control.v": "03fb3f3602704606e33a477491da61ae2415409e1376212b71c95354ece49d92",
    "altera_modular_adc_control_fsm.v": "dd39a51bd11f96ddea56de2be9ef56e2184985d2063a1ab2bda4ca1506e40105",
    "altera_modular_adc_control_avrg_fifo.v": "e4570567d633185546949acf6d6f9d875ee6567a6adc44e27d22c296361accf8",
}


def explained_diagnostics(text, folder, sources):
    """Exact unused dual-ADC and temperature paths in the two-channel proof.

    This does not permit general unused logic/RAM warnings. Raw lines, source
    identity and the complete 15-line inventory must all match.
    """
    if any(sources.get(name, {}).get("sha256") != pin for name, pin in SUPPORTED_CONTROL.items()):
        raise ValueError("unsupported ADC source for diagnostic classification")
    for name, pin in SUPPORTED_CONTROL.items():
        if file_hash(folder / name) != pin:
            raise ValueError("copied ADC source differs from supported diagnostic pin")
    lines = [line.strip() for line in text.splitlines()]
    unused = ('Warning (10036): Verilog HDL or VHDL warning at altera_modular_adc_control_fsm.v(70): '
              'object "sync_ctrl_state_nxt" assigned a value but never read File: '
              + (folder / 'altera_modular_adc_control_fsm.v').as_posix() + ' Line: 70')
    required = [unused, 'Warning (14284): Synthesized away the following node(s):',
                'Warning (14285): Synthesized away the following RAM node(s):']
    prefix = ('Warning (14320): Synthesized away node "n2m_adc_backend:u_adc|'
              'altera_modular_adc_control:u_control|altera_modular_adc_control_fsm:u_control_fsm|'
              'altera_modular_adc_control_avrg_fifo:ts_avrg_fifo|scfifo:scfifo_component|')
    for bit in range(12):
        pattern = (re.escape(prefix) + r'scfifo_\w+:auto_generated\|a_dpfifo_\w+:dpfifo\|'
                   + r'altsyncram_\w+:FIFOram\|q_b\[' + str(bit) + r'\]" File: '
                   + re.escape((folder / 'db').as_posix()) + r'/altsyncram_\w+\.tdf Line: '
                   + str(40 + 30 * bit))
        matches = [line for line in lines if re.fullmatch(pattern, line)]
        if len(matches) != 1:
            raise ValueError(f"missing or duplicate ADC temperature FIFO diagnostic bit {bit}")
        required.extend(matches)
    for line in required:
        if lines.count(line) != 1:
            raise ValueError("missing or duplicate ADC unused-feature diagnostic")
    actual = [line for line in lines if re.match(r'Warning \((10036|14284|14285|14320)\):', line)]
    if len(actual) != 15 or set(actual) != set(required):
        raise ValueError("unexpected ADC unused-feature diagnostic")
    return [{"code": re.match(r'Warning \((\d+)\)', line)[1], "text": line,
             "reason": "pinned Intel ADC1 control: unused dual-ADC state and channel17 temperature FIFO"}
            for line in required]


def identity(directory):
    quartus = Path(directory).resolve().parent
    ip = quartus.parent / "ip/altera"
    paths = {name: ip / "altera_modular_adc/control" / name for name in CONTROL}
    # Synthesis resolves the canonical megafunction automatically. Retain this
    # same source for explicit simulation compilation without shadowing it in QSF.
    paths["altera_std_synchronizer.v"] = quartus / "libraries/megafunctions/altera_std_synchronizer.v"
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
    for name in CONTROL:
        source = Path(sources[name]["path"])
        if file_hash(source) != sources[name]["sha256"]:
            raise ValueError("Intel ADC dependency changed before generation")
        shutil.copyfile(source, folder / name)
    command = [sources["generator"]["path"], "-silent", "module=altpll",
               "INTENDED_DEVICE_FAMILY=MAX 10", "INCLK0_INPUT_FREQUENCY=100000",
               "CLK0_MULTIPLY_BY=1", "CLK0_DIVIDE_BY=1", "CLK0_DUTY_CYCLE=50",
               "CLK0_PHASE_SHIFT=0", "COMPENSATE_CLOCK=CLK0", "OPERATION_MODE=NO_COMPENSATION",
               "areset=used", "locked=used", "clk0=used", "OPTIONAL_FILES=NONE", "n2m_adc_pll.v"]
    execute(command, folder, folder / "generate-adc-pll.log", timeout, record, build)
    text = (folder / "n2m_adc_pll.v").read_text()
    expected = {"clk0_divide_by": "1", "clk0_multiply_by": "1", "clk0_duty_cycle": "50",
                "clk0_phase_shift": '"0"', "inclk0_input_frequency": "100000",
                "intended_device_family": '"MAX 10"', "operation_mode": '"NO_COMPENSATION"',
                "port_areset": '"PORT_USED"', "port_locked": '"PORT_USED"'}
    for name, value in expected.items():
        if re.findall(r"altpll_component\." + name + r"\s*=\s*([^,;]+)", text) != [value]:
            raise ValueError(f"generated ADC PLL parameter mismatch: {name}")


def assignments():
    return [f'set_global_assignment -name VERILOG_FILE {name}'
            for name in (*CONTROL[:-1], "n2m_adc_pll.v")] + [
                "set_global_assignment -name SDC_FILE altera_modular_adc_control.sdc"]
