"""Bounded ALTPLL generation; generated vendor HDL stays inside the attempt."""
from pathlib import Path
import os
import math
import re

from .records import file_hash
from . import fpga_lock

CHAINS = ("board_release", "lock_samples", "sys_release", "pix_release")
SYSTEM_PLL = "u_clocking|u_system_pll|altpll_component|auto_generated|pll1"
PIXEL_PLL = "u_clocking|u_pll|altpll_component|auto_generated|pll1"
ADC_PLL = "u_adc|u_pll|altpll_component|auto_generated|pll1"
SYSTEM_CLOCK = SYSTEM_PLL + "|clk[0]"
SYSTEM_NET = r"\u_clocking|u_system_pll|altpll_component|auto_generated|wire_pll1_clk[0]~clkctrl_outclk"


def chain_audit(quote):
    lines = []
    for name in CHAINS:
        for i in (0, 1):
            endpoint = quote(f"u_clocking|u_reset|{name}[{i}]")
            message = quote(f"missing reset stage: {name}[{i}]")
            lines.extend([f"set chain_{i} [get_registers {endpoint}]",
                          f'if {{[get_collection_size $chain_{i}] != 1}} {{error {message}}}'])
        for check in ("setup", "hold"):
            lines.append(f"report_timing -from $chain_0 -to $chain_1 -{check} -npaths 1 -detail full_path -file output/chain_{name}_{check}.rpt")
    return "\n".join(lines) + "\n"


def required_reports():
    return ["metastability.rpt", "clock_transfers.rpt"] + [f"chain_{name}_{check}.rpt" for name in CHAINS for check in ("setup", "hold")]


def verify_lock_event(folder, checks, top="clocking_proof", *, parallel=False):
    checker = fpga_lock.verify_parallel if parallel else fpga_lock.verify
    return checker((folder / "simulation/questa/design.vo").read_text(encoding="utf-8"), checks, top)


def explained_diagnostics(text, folder, definition):
    if definition.get("system_divide") != 2:
        return []
    verify(folder, definition)
    prefix = ('Warning (176127): The parameters of the PLL '
              'n2m_clocking:u_clocking|n2m_pixel_pll:u_pll|altpll:altpll_component|n2m_pixel_pll_altpll:auto_generated|pll1 '
              'and the PLL n2m_clocking:u_clocking|n2m_system_pll:u_system_pll|altpll:altpll_component|n2m_system_pll_altpll:auto_generated|pll1 '
              'do not have the same values - hence these PLLs cannot be merged File: ')
    lines = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(lines) > 1 or any(not re.fullmatch(re.escape(prefix + (folder / "db/n2m_pixel_pll_altpll.v").resolve().as_posix()) + r" Line: \d+", line) for line in lines):
        raise ValueError("parallel PLL diagnostic identity/count differs")
    return [{"code": "176127", "text": line,
             "reason": "Separate verified 25 MHz and 25.2 MHz PLLs must retain different ratios."} for line in lines]


def verify_fit(folder, target):
    if target["pll"].get("system_divide") == 2:
        return verify_parallel_fit(folder, target)
    fit = (folder / "output/design.fit.rpt").read_text(encoding="cp1252" if os.name == "nt" else "utf-8")
    combined = target.get("top") in ("controls_proof", "v05_controls_proof")
    adc_values = {"PLL mode": "No compensation", "Compensate clock": "--", "Input frequency 0": "10.0 MHz",
                  "Nominal PFD frequency": "10.0 MHz", "Nominal VCO frequency": "400.0 MHz",
                  "M value": "40", "N value": "1", "Inclk0 signal type": "Dedicated Pin"}
    if combined:
        names = re.findall(r";\s*SDC pin name\s*;\s*([^;]+?)\s*;\s*([^;]+?)\s*;", fit)
        if names != [("u_clocking|u_pll|altpll_component|auto_generated|pll1",
                      "u_adc|u_pll|altpll_component|auto_generated|pll1")]:
            raise ValueError("combined PLL columns differ")
    for key, value in {"PLL mode": "Normal", "Compensate clock": "clock0", "Input frequency 0": "50.0 MHz",
                       "Nominal PFD frequency": "10.0 MHz", "Nominal VCO frequency": "630.0 MHz",
                       "M value": "63", "N value": "5", "Inclk0 signal type": "Dedicated Pin"}.items():
        rows = re.findall(r";\s*" + re.escape(key) + r"\s*;\s*([^;]+?)\s*;" +
                          (r"\s*([^;]+?)\s*;" if combined else ""), fit)
        if rows != ([(value, adc_values[key])] if combined else [value]):
            raise ValueError(f"PLL fit mismatch: {key}")
    usage = [line.split(';')[1:-1] for line in fit.splitlines() if '; clock0 ' in line and 'wire_pll1_clk' in line]
    if combined:
        adc_usage = [[v.strip() for v in row] for row in usage if 'n2m_adc_backend:u_adc|' in row[0]]
        if (len(usage) != 2 or len(adc_usage) != 1 or adc_usage[0][1:6] != ["clock0", "1", "1", "10.0 MHz", "0 (0 ps)"]
                or adc_usage[0][7:10] != ["50/50", "C0", "40"]):
            raise ValueError("combined ADC PLL rate/phase/counter differs")
        usage = [row for row in usage if 'n2m_clocking:u_clocking|' in row[0]]
    if len(usage) != 1 or [v.strip() for v in usage[0]][1:5] != ["clock0", "63", "125", "25.2 MHz"]:
        raise ValueError("PLL fit rate mismatch")
    row = [v.strip() for v in usage[0]]
    if row[5] != "0 (0 ps)" or row[7:10] != ["50/50", "C0", "25"]:
        raise ValueError("PLL fit phase, duty, or counter mismatch")
    sta = (folder / "output/design.sta.rpt").read_text(encoding="utf-8")
    if combined:
        adc_clocks = [[v.strip() for v in line.split(';')[1:-1]] for line in sta.splitlines()
                      if re.match(r";\s*(?:clk_adc_reference|u_adc\|u_pll\|altpll_component\|auto_generated\|pll1\|clk\[0\])\s*;\s*(?:Base|Generated)\s*;", line)]
        if (len(adc_clocks) != 2 or adc_clocks[0][:3] != ['clk_adc_reference', 'Base', '100.000']
                or adc_clocks[1][:3] != ['u_adc|u_pll|altpll_component|auto_generated|pll1|clk[0]', 'Generated', '100.000']
                or adc_clocks[1][6:9] != ['50.00', '1', '1'] or adc_clocks[1][14] != 'clk_adc_reference'):
            raise ValueError('combined ADC generated clock relationship differs')
    clocks = [[v.strip() for v in line.split(';')[1:-1]] for line in sta.splitlines()
              if re.match(r";\s*(?:clk_sys|u_clocking\|u_pll\|altpll_component\|auto_generated\|pll1\|clk\[0\])\s*;\s*(?:Base|Generated)\s*;", line)]
    if len(clocks) != 2:
        raise ValueError("missing or extra clock report rows")
    base = next((r for r in clocks if r[1] == "Base"), None)
    generated = next((r for r in clocks if r[1] == "Generated"), None)
    reference = target["timing"]["reference_ns"]
    if not base or not generated or base[2] != reference or generated[6:9] != ["50.00", "125", "63"] or generated[14] != "clk_sys":
        raise ValueError("generated clock relationship mismatch")
    # TimeQuest prints periods to 1 ps and may truncate the rational period.
    if abs(float(generated[2]) - float(reference) * 125 / 63) >= 0.001:
        raise ValueError("generated clock period mismatch")
    for name in required_reports():
        path = folder / "output" / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError(f"missing clocking analysis: {name}")
        if name.startswith("chain_"):
            chain, check = name.removeprefix("chain_").removesuffix(".rpt").rsplit("_", 1)
            report = path.read_text(encoding="utf-8")
            result = re.findall(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)\.  Worst case slack is (\S+)", report)
            if len(result) != 1 or not float(result[0]) >= 0:
                raise ValueError(f"reset stage path is missing or violated: {name}")
            if any(f"u_reset|{chain}[{i}]" not in report for i in (0, 1)):
                raise ValueError(f"reset stage path endpoints differ: {name}")


def verify_parallel_fit(folder, target):
    """Bind each fitted column and clock to its declared physical owner."""
    fit = (folder / "output/design.fit.rpt").read_text(encoding="cp1252" if os.name == "nt" else "utf-8")
    rows = [[v.strip() for v in line.split(';')[1:-1]] for line in fit.splitlines()]
    adc_pll = ("u_controls|" if target["top"] == "v05_controls_proof" else "") + ADC_PLL
    expected = {
        SYSTEM_PLL: ("Normal", "clock0", "50.0 MHz", "6.3 MHz", "650.0 MHz", "104", "8", "Dedicated Pin"),
        PIXEL_PLL: ("Normal", "clock0", "50.0 MHz", "10.0 MHz", "630.0 MHz", "63", "5", "Dedicated Pin"),
    }
    if target["top"] in ("controls_proof", "v05_controls_proof"):
        expected[adc_pll] = ("No compensation", "--", "10.0 MHz", "10.0 MHz", "400.0 MHz", "40", "1", "Dedicated Pin")
    headings = [r[1:] for r in rows if r and r[0] == "SDC pin name"]
    if len(headings) != 1 or len(headings[0]) != len(expected) or set(headings[0]) != set(expected):
        raise ValueError("parallel PLL owner columns differ")
    for index, key in enumerate(("PLL mode", "Compensate clock", "Input frequency 0", "Nominal PFD frequency",
                                 "Nominal VCO frequency", "M value", "N value", "Inclk0 signal type")):
        actual = [r[1:] for r in rows if r and r[0] == key]
        if actual != [[expected[name][index] for name in headings[0]]]:
            raise ValueError("parallel PLL configuration differs: " + key)
    shapes = {SYSTEM_PLL: ["1", "2", "25.0 MHz", "26"], PIXEL_PLL: ["63", "125", "25.2 MHz", "25"],
              adc_pll: ["1", "1", "10.0 MHz", "40"]}
    usage = [r for r in rows if len(r) == 15 and r[1] == "clock0" and "wire_pll1_clk" in r[0]]
    if len(usage) != len(expected):
        raise ValueError("parallel PLL output count differs")
    for name in expected:
        matches = [r for r in usage if r[-1] == name + "|clk[0]"]
        if len(matches) != 1:
            raise ValueError("parallel PLL output owner differs")
        row = matches[0]
        if row[2:5] + [row[9]] != shapes[name] or row[5] != "0 (0 ps)" or row[7:9] != ["50/50", "C0"]:
            raise ValueError("parallel PLL output rate/phase/duty differs")
    sta = (folder / "output/design.sta.rpt").read_text(encoding="utf-8")
    clocks = [[v.strip() for v in line.split(';')[1:-1]] for line in sta.splitlines()
              if re.match(r";[^;]+;\s*(?:Base|Generated)\s*;", line)]
    reference = float(target["timing"]["reference_ns"])
    wanted = {"clk_reference": ("Base", reference, None, None),
              SYSTEM_CLOCK: ("Generated", reference*2, ["50.00", "2", "1"], "clk_reference"),
              PIXEL_PLL + "|clk[0]": ("Generated", reference*125/63, ["50.00", "125", "63"], "clk_reference")}
    if adc_pll in expected:
        wanted.update({"clk_adc_reference": ("Base", 100.0, None, None),
                       adc_pll + "|clk[0]": ("Generated", 100.0, ["50.00", "1", "1"], "clk_adc_reference")})
    if len(clocks) != len(wanted) or {r[0] for r in clocks} != set(wanted):
        raise ValueError("parallel PLL clock inventory differs")
    for row in clocks:
        kind, period, ratio, master = wanted[row[0]]
        if row[1] != kind or not abs(float(row[2])-period) < .001:
            raise ValueError("parallel PLL clock period differs")
        if ratio is not None and (row[6:9] != ratio or row[14] != master):
            raise ValueError("parallel PLL clock relationship differs")
    summary = (folder / "output/design.fit.summary").read_text()
    if re.findall(r"(?m)^Total PLLs : (\d+) /", summary) != [str(len(expected))]:
        raise ValueError("parallel PLL physical resource count differs")
    for name in required_reports():
        path = folder / "output" / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("missing parallel clock report: " + name)
        if name.startswith("chain_"):
            chain, check = name.removeprefix("chain_").removesuffix(".rpt").rsplit("_", 1)
            text = path.read_text()
            result = re.findall(r"Report Timing: Found 1 " + check + r" paths \(0 violated\)\.  Worst case slack is (\S+)", text)
            if len(result) != 1 or (not math.isfinite(float(result[0])) or float(result[0]) < 0) or any(f"u_reset|{chain}[{i}]" not in text for i in (0, 1)):
                raise ValueError("parallel reset chain missing or violated: " + name)


def validate(definition):
    if definition not in ({"module": "n2m_pixel_pll", "input_ps": 20000,
                          "multiply": 63, "divide": 125},
                         {"module": "n2m_pixel_pll", "input_ps": 20000,
                          "multiply": 63, "divide": 125, "system_divide": 2}):
        raise ValueError("unsupported PLL definition")


def identity(directory):
    directory = Path(directory).resolve()
    paths = {"generator": directory / ("qmegawiz.exe" if os.name == "nt" else "qmegawiz"),
             "definition": directory.parent / "libraries/megafunctions/xml_info/altpll_info.xml",
             "primitive": directory.parent / "libraries/megafunctions/altpll.tdf",
             "atom_model": directory.parent / "eda/sim_lib/fiftyfivenm_atoms.v",
             "register_model": directory.parent / "eda/sim_lib/altera_primitives.v",
             "rules": directory.parent / "libraries/megafunctions/xml_info/altpll_rules.xml",
             "wizard": directory.parent / "libraries/megafunctions/xml_info/altpll_wiz_map.xml"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("missing explicit Quartus ALTPLL generation dependency")
    return {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}


def _command(identity, module, input_ps, multiply, divide, bandwidth=None):
    command = [identity["generator"]["path"], "-silent", "module=altpll",
               "INTENDED_DEVICE_FAMILY=MAX 10", f"INCLK0_INPUT_FREQUENCY={input_ps}",
               f"CLK0_MULTIPLY_BY={multiply}", f"CLK0_DIVIDE_BY={divide}",
               "CLK0_DUTY_CYCLE=50", "CLK0_PHASE_SHIFT=0", "COMPENSATE_CLOCK=CLK0",
               "OPERATION_MODE=NORMAL", "areset=used", "locked=used", "clk0=used",
               "OPTIONAL_FILES=NONE"]
    if bandwidth:
        command.append(f"BANDWIDTH_TYPE={bandwidth}")
    return command + [module + ".v"]


def generation_command(identity, definition):
    validate(definition)
    return _command(identity, "n2m_pixel_pll", 20000, 63, 125)


def generate(folder, identity, definition, execute, timeout, record, build):
    execute(generation_command(identity, definition), folder,
            folder / "generate-pll.log", timeout, record, build)
    if definition.get("system_divide") == 2:
        execute(_command(identity, "n2m_system_pll", 20000, 1, 2, "LOW"), folder,
                folder / "generate-system-pll.log", timeout, record, build)
    verify(folder, definition)


def verify(folder, definition=None):
    if definition is None:
        definition = {"module": "n2m_pixel_pll", "input_ps": 20000, "multiply": 63, "divide": 125}
    validate(definition)
    _verify_module(folder, definition, None)
    if definition.get("system_divide") == 2:
        _verify_module(folder, {"module": "n2m_system_pll", "input_ps": 20000,
                               "multiply": 1, "divide": 2}, "LOW")


def _verify_module(folder, definition, bandwidth):
    path = folder / (definition["module"] + ".v")
    text = path.read_text(encoding="utf-8")
    expected = {"clk0_divide_by": str(definition["divide"]), "clk0_multiply_by": str(definition["multiply"]), "clk0_duty_cycle": "50",
                "clk0_phase_shift": '"0"', "inclk0_input_frequency": str(definition["input_ps"]),
                "intended_device_family": '"MAX 10"', "operation_mode": '"NORMAL"',
                "compensate_clock": '"CLK0"', "self_reset_on_loss_lock": '"OFF"',
                "port_areset": '"PORT_USED"', "port_locked": '"PORT_USED"'}
    if bandwidth:
        expected["bandwidth_type"] = '"' + bandwidth + '"'
    for key, value in expected.items():
        values = re.findall(r"altpll_component\." + key + r"\s*=\s*([^,;]+)", text)
        if values != [value]:
            raise ValueError(f"generated PLL parameter mismatch: {key}")
    if re.search(r'`include\b|\$(?:readmemh|readmemb|fopen)\b', text):
        raise ValueError("untracked generated PLL dependency")
    if not re.search(r"module\s+" + re.escape(definition["module"]) + r"\s*\(", text):
        raise ValueError("generated PLL module mismatch")
