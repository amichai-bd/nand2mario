"""Bounded ALTPLL generation; generated vendor HDL stays inside the attempt.

ALTPLL serves more than one device family, so the generation and the fit, lock,
metastability, reset-chain and clock-transfer checks here are shared. What a
family owns is small and stated at each site: the family name the generator is
given and the generated HDL must state back, the installed simulation atom model,
the netlist primitive table, its own supported proof tops, and any fitter
diagnostic only its board produces. `FAMILY` and `ATOM_MODEL` are this module's,
and a second family reuses these functions from its own module
([fpga_pll_cycloneive.py](fpga_pll_cycloneive.py)) rather than copying them.
"""
from pathlib import Path
import os
import math
import re

from . import fpga_clocking, fpga_lock, fpga_vga_dac, vendor_sources

# The reset chain audit and its report inventory are family-neutral; the
# clocking registry owns them and both families keep the same names.
CHAINS = fpga_clocking.CHAINS
chain_audit = fpga_clocking.chain_audit
required_reports = fpga_clocking.required_reports
FIT_ENCODING = fpga_clocking.FIT_ENCODING
TOOLS_KEY = "altpll"
# This module's own family. ALTPLL serves more than one, and the family is the
# one thing the generator, the generated HDL and the installed atom model each
# have to state, so every entry point takes it and defaults to this.
FAMILY = "MAX 10"
# The simulation atom model whose hash enters the request fingerprint. Each
# family installs its own, so it travels with the family rather than with ALTPLL.
ATOM_MODEL = "eda/sim_lib/fiftyfivenm_atoms.v"
# The proof tops whose exact u_clocking hierarchy these checks recognize. The
# list is this family's, not ALTPLL's: another family registers its own tops in
# its own module, so a target cannot point one family's checks at another's top.
SUPPORTED_TOPS = ("clocking_proof", "vga_proof", "ppu_proof", "intel_memory_proof", "controls_proof",
                  "v05_proof", "v05_controls_proof", "sdram_proof", "flash_proof")
SYSTEM_PLL = "u_clocking|u_system_pll|altpll_component|auto_generated|pll1"
PIXEL_PLL = "u_clocking|u_pll|altpll_component|auto_generated|pll1"
# The ADC support PLL. It stays here rather than moving to the shared ALTPLL
# facts: the block it clocks is a MAX 10 device feature, and neither Cyclone IV E
# nor Cyclone V has an ADC on the fabric.
ADC_PLL = "u_adc|u_pll|altpll_component|auto_generated|pll1"
SYSTEM_CLOCK = SYSTEM_PLL + "|clk[0]"
PIXEL_CLOCK = PIXEL_PLL + "|clk[0]"
SYSTEM_NET = r"\u_clocking|u_system_pll|altpll_component|auto_generated|wire_pll1_clk[0]~clkctrl_outclk"


def generated_sources(definition):
    """The generated vendor HDL the project compiles, in a fixed order."""
    validate(definition)
    return ["n2m_pixel_pll.v"] + (["n2m_system_pll.v"] if definition.get("system_divide") == 2 else [])


def assignments(definition):
    """ALTPLL needs no project assignment beyond its generated HDL."""
    validate(definition)
    return []


def cache_files(definition):
    """Generated HDL and generation log per PLL; reuse needs all of them."""
    validate(definition)
    names = ["n2m_pixel_pll.v", "generate-pll.log"]
    if definition.get("system_divide") == 2:
        names += ["n2m_system_pll.v", "generate-system-pll.log"]
    return names


def timed_clocks(target):
    """The clocks every corner and check must report."""
    if target.get("pll", {}).get("system_divide") == 2:
        return ("clk_reference", SYSTEM_CLOCK, PIXEL_CLOCK)
    return ("clk_sys", PIXEL_CLOCK)


def corner_slacks(target, corner):
    """No ALTPLL clock needs a corner entry beyond its timed clocks.

    ALTPLL publishes only its output clocks to the Timing Analyzer, so the
    analysed inventory is exactly the timed clocks and there is nothing further
    to require at a corner. The Altera PLL differs: it also publishes a VCO
    clock, which is why that family states its own entries. Measured on both
    ALTPLL families' clock inventories, which hold three clocks and no more.
    """
    return []


def no_clock_rows(target):
    """The no-clock rows this target's own generated ALTPLL instances report.

    One documented lock event latch per instance, named as `check_timing` reports
    it and with the reason that table gives it, so the owner states the whole row
    rather than half of it. The ADC backend's latch is not named here even though
    the controls compositions contain it: `fpga_adc` owns that row, because a
    target can place the backend without generating a PLL of its own.
    """
    rows = [(fpga_lock.ROW, fpga_lock.REGISTER_REASON)]
    if target.get("pll", {}).get("system_divide") == 2:
        rows.append((fpga_lock.SYSTEM_ROW, fpga_lock.REGISTER_REASON))
    return rows


def lock_event_count(target):
    """How many of them, so the count and the rows cannot state different things."""
    return len(no_clock_rows(target))


def verify_lock_event(folder, checks, top="clocking_proof", *, parallel=False, rows=(),
                      primitives=fpga_lock.MAX10):
    """Classify the lock event in the checked netlist, in this family's primitives.

    `rows` is the accepted no-clock inventory the caller resolved from every
    owner; this family's own rows are part of it and the checker refuses a list
    that omits them.

    `primitives` names the family's fitted atom set; the default is MAX 10's.
    Only the parallel checker takes one, because only the parallel composition is
    shared with another family.
    """
    if not parallel and primitives is not fpga_lock.MAX10:
        raise ValueError("the single-PLL lock checker recognizes MAX 10 primitives only")
    text = (folder / "simulation/questa/design.vo").read_text(encoding="utf-8")
    if parallel:
        return fpga_lock.verify_parallel(text, checks, top, rows=rows, primitives=primitives)
    return fpga_lock.verify(text, checks, top, rows=rows)


MERGE_PAIR = ("n2m_clocking:u_clocking|n2m_pixel_pll:u_pll|altpll:altpll_component|n2m_pixel_pll_altpll:auto_generated|pll1",
              "n2m_clocking:u_clocking|n2m_system_pll:u_system_pll|altpll:altpll_component|n2m_system_pll_altpll:auto_generated|pll1")
MERGE_FILES = ("n2m_pixel_pll_altpll.v", "n2m_system_pll_altpll.v")


def explained_diagnostics(text, folder, definition, family=FAMILY):
    """Explain the one 176127 merge refusal for the verified system/pixel pair.

    Quartus names the two PLLs in either order and cites whichever generated
    file it visited second; the pair and the file set are matched as sets. The
    refusal is ALTPLL's, not one family's: two instances with different ratios
    are never merged, whichever family they are generated for.
    """
    if definition.get("system_divide") != 2:
        return []
    verify(folder, definition, family=family)
    pattern = re.compile(r"Warning \(176127\): The parameters of the PLL (\S+) and the PLL (\S+) "
                         r"do not have the same values - hence these PLLs cannot be merged File: (.+) Line: \d+")
    lines = [line for line in text.splitlines() if line.startswith("Warning (176127):")]
    if len(lines) > 1:
        raise ValueError("parallel PLL diagnostic identity/count differs")
    database = (folder / "db").resolve()
    for line in lines:
        match = pattern.fullmatch(line)
        if (not match or sorted(match.group(1, 2)) != sorted(MERGE_PAIR)
                or match[3] not in {(database / name).as_posix() for name in MERGE_FILES}):
            raise ValueError("parallel PLL diagnostic identity/count differs")
    return [{"code": "176127", "text": line,
             "reason": "Separate verified 25 MHz and 25.2 MHz PLLs must retain different ratios."} for line in lines]


def verify_fit(folder, target):
    if target["pll"].get("system_divide") == 2:
        return verify_parallel_fit(folder, target)
    fit = (folder / "output/design.fit.rpt").read_text(encoding=FIT_ENCODING)
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


SDRAM_CLOCK = "sdram_clk"


def pin_clocks(target):
    """Generated clocks this composition drives out to a pin, name -> port.

    A pin clock is declared in the target's own SDC as its source clock inverted
    at that port, so the clock inventory below both expects the row and binds it
    to the port. Two exist: the SDRAM contract's inverted system clock, and the
    DE2-115 video DAC's inverted pixel clock. Each is recognized by the port it
    leaves on rather than by a list of tops, because more than one image drives
    the same pin: the DE2-115's standalone DAC fixture and its system image both
    carry `vga_clk`, and a top that places the port and does not declare the clock
    fails this inventory rather than passing with a clock missing.
    """
    clocks = {}
    pins = target.get("pins", {})
    if target.get("top") == "sdram_proof" or "DRAM_CLK" in pins:
        clocks[SDRAM_CLOCK] = ("DRAM_CLK", SYSTEM_CLOCK, 2)
    if target.get("top") == fpga_vga_dac.TOP or fpga_vga_dac.CLOCK_PORT in pins:
        clocks[fpga_vga_dac.CLOCK_NAME] = (fpga_vga_dac.CLOCK_PORT, PIXEL_CLOCK, 125 / 63)
    return clocks


def clock_inventory(target, reference, adc_pll=None):
    """Every STA clock row a parallel-PLL target must show: name -> (kind, period, ratio, master)."""
    wanted = {"clk_reference": ("Base", reference, None, None),
              SYSTEM_CLOCK: ("Generated", reference*2, ["50.00", "2", "1"], "clk_reference"),
              PIXEL_PLL + "|clk[0]": ("Generated", reference*125/63, ["50.00", "125", "63"], "clk_reference")}
    if adc_pll:
        wanted.update({"clk_adc_reference": ("Base", 100.0, None, None),
                       adc_pll + "|clk[0]": ("Generated", 100.0, ["50.00", "1", "1"], "clk_adc_reference")})
    # A pin clock keeps its source's period at unit ratio and prints no duty
    # column, because the port inverts the clock rather than dividing it.
    for name, (_, master, ratio) in pin_clocks(target).items():
        wanted[name] = ("Generated", reference*ratio, ["", "1", "1"], master)
    return wanted


def verify_parallel_fit(folder, target):
    """Bind each fitted column and clock to its declared physical owner."""
    fit = (folder / "output/design.fit.rpt").read_text(encoding=FIT_ENCODING)
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
    wanted = clock_inventory(target, reference, adc_pll if adc_pll in expected else None)
    ports = {name: port for name, (port, _, _) in pin_clocks(target).items()}
    if len(clocks) != len(wanted) or {r[0] for r in clocks} != set(wanted):
        raise ValueError("parallel PLL clock inventory differs")
    for row in clocks:
        kind, period, ratio, master = wanted[row[0]]
        if row[1] != kind or not abs(float(row[2])-period) < .001:
            raise ValueError("parallel PLL clock period differs")
        if ratio is not None and (row[6:9] != ratio or row[14] != master):
            raise ValueError("parallel PLL clock relationship differs")
        if row[0] in ports and (row[13] != "true" or row[16] != "{ " + ports[row[0]] + " }"):
            raise ValueError("pin clock is not its source clock inverted at " + ports[row[0]])
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


def generator(directory):
    """The megafunction generator in an explicit Quartus binary directory.

    The `.exe` suffix is a genuine platform fact: Quartus ships `qmegawiz.exe`
    on Windows and `qmegawiz` elsewhere. Every caller that needs the generator
    takes it from here, so no second copy of the fact can drift. The path is
    joined as given; resolving belongs to the caller that wants it.
    """
    return Path(directory) / ("qmegawiz.exe" if os.name == "nt" else "qmegawiz")


def identity(directory, atom_model=ATOM_MODEL):
    """The explicit ALTPLL generation dependencies, with this family's atom model.

    Every path but the atom model is ALTPLL's own or the generator's, so it is
    shared; the atom model is per family and the caller states which one.
    """
    directory = Path(directory).resolve()
    paths = {"generator": generator(directory),
             "definition": directory.parent / "libraries/megafunctions/xml_info/altpll_info.xml",
             "primitive": directory.parent / "libraries/megafunctions/altpll.tdf",
             "atom_model": directory.parent / atom_model,
             "register_model": directory.parent / "eda/sim_lib/altera_primitives.v",
             "rules": directory.parent / "libraries/megafunctions/xml_info/altpll_rules.xml",
             "wizard": directory.parent / "libraries/megafunctions/xml_info/altpll_wiz_map.xml"}
    if any(not path.is_file() for path in paths.values()):
        raise ValueError("missing explicit Quartus ALTPLL generation dependency")
    return vendor_sources.check(directory, paths)


def _command(identity, module, input_ps, multiply, divide, bandwidth=None, family=FAMILY):
    command = [identity["generator"]["path"], "-silent", "module=altpll",
               f"INTENDED_DEVICE_FAMILY={family}", f"INCLK0_INPUT_FREQUENCY={input_ps}",
               f"CLK0_MULTIPLY_BY={multiply}", f"CLK0_DIVIDE_BY={divide}",
               "CLK0_DUTY_CYCLE=50", "CLK0_PHASE_SHIFT=0", "COMPENSATE_CLOCK=CLK0",
               "OPERATION_MODE=NORMAL", "areset=used", "locked=used", "clk0=used",
               "OPTIONAL_FILES=NONE"]
    if bandwidth:
        command.append(f"BANDWIDTH_TYPE={bandwidth}")
    return command + [module + ".v"]


def generation_command(identity, definition, family=FAMILY):
    validate(definition)
    return _command(identity, "n2m_pixel_pll", 20000, 63, 125, family=family)


def generate(folder, identity, definition, execute, timeout, record, build, *, device=None, family=FAMILY):
    """Generate both ALTPLL instances. The device is implied by the family here."""
    execute(generation_command(identity, definition, family), folder,
            folder / "generate-pll.log", timeout, record, build)
    if definition.get("system_divide") == 2:
        execute(_command(identity, "n2m_system_pll", 20000, 1, 2, "LOW", family=family), folder,
                folder / "generate-system-pll.log", timeout, record, build)
    verify(folder, definition, family=family)


def verify(folder, definition=None, family=FAMILY):
    if definition is None:
        definition = {"module": "n2m_pixel_pll", "input_ps": 20000, "multiply": 63, "divide": 125}
    validate(definition)
    _verify_module(folder, definition, None, family)
    if definition.get("system_divide") == 2:
        _verify_module(folder, {"module": "n2m_system_pll", "input_ps": 20000,
                               "multiply": 1, "divide": 2}, "LOW", family)


def _verify_module(folder, definition, bandwidth, family=FAMILY):
    path = folder / (definition["module"] + ".v")
    text = path.read_text(encoding="utf-8")
    expected = {"clk0_divide_by": str(definition["divide"]), "clk0_multiply_by": str(definition["multiply"]), "clk0_duty_cycle": "50",
                "clk0_phase_shift": '"0"', "inclk0_input_frequency": str(definition["input_ps"]),
                "intended_device_family": '"' + family + '"', "operation_mode": '"NORMAL"',
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
