"""Resolve the installed Intel On-Chip Flash IP and stage its pinned sources.

The IP is plain parameterised Verilog: n2m_flash_reader instantiates
altera_onchip_flash directly with the parameters its hw.tcl derives, so no
generator runs. The builder copies the four synthesis files into the attempt,
names them in the QSF and sets the internal configuration mode the contract
(wiki/src/rtl/storage/MAS_flash_library.md) requires.
"""
from pathlib import Path
import re
import shutil

from .records import file_hash

READER = "src/rtl/storage/n2m_flash_reader.sv"
IP_NAME = "altera_onchip_flash"
# Quartus Prime 25.1std Lite ip/altera/altera_onchip_flash: the synthesis
# fileset of altera_onchip_flash_hw_proc.tcl generate_synth for the parallel
# read-only configuration (no csr controller, no vendor SDC).
SOURCES = {
    "altera_onchip_flash.v": ("altera_onchip_flash", "03a088deb2baaef6b33229b2bf3717d659efceac30043a1243066672195db316"),
    "altera_onchip_flash_avmm_data_controller.v": ("altera_onchip_flash", "a87a4f86b581ba3b78fb9189bf6215bf1722bc56757fc5cd30a1853787d8f517"),
    "altera_onchip_flash_util.v": ("altera_onchip_flash", "4091b0255ebe2b534f87b6af95ee0d4dda965c975b9a0457c7e6f36d38b2e301"),
    "altera_onchip_flash_block.v": ("rtl", "6afaeaf53c8596647ee4e56b7d79193970c79efd7c774584a84b0e444a88dfb1"),
}
DEFINITIONS = {
    "altera_onchip_flash_hw.tcl": "d4a832155d41eaf776d3fea061e22bc09ffc1050d2e7048c6e2e84c0b914f613",
    "altera_onchip_flash_hw_proc.tcl": "bd6465a1f3cb08e65888ed5a7d5f085b5979bc8073d8878844bd8f422ac29a2c",
}
CONFIGURATION_MODE = 'set_global_assignment -name INTERNAL_FLASH_UPDATE_MODE "Single Comp Image"'
# Reader instance path per registered top; a top not listed here has no
# classified flash diagnostics and fails on the first one.
READER_INSTANCES = {"flash_proof": "u_reader"}
# Registers of the vendor data controller that only its read-and-write mode
# reads: Quartus 25.1 names each once with its line in the pinned file.
UNUSED_OBJECTS = (
    (201, "flash_sector_addr"), (217, "flash_drdin_neg_reg"), (218, "write_count"), (219, "erase_count"),
    (222, "write_timeout"), (224, "write_wait_neg"), (225, "erase_timeout"), (231, "flash_se_pass_reg"),
    (232, "flash_sp_pass_reg"), (233, "flash_busy_reg"), (234, "flash_busy_clear_reg"), (235, "erase_busy_scan"),
    (236, "write_busy_scan"), (237, "is_sector1_writable_reg"), (238, "is_sector2_writable_reg"),
    (239, "is_sector3_writable_reg"), (240, "is_sector4_writable_reg"), (241, "is_sector5_writable_reg"),
    (248, "cur_e_addr"), (262, "valid_csr_sector_erase_addr"),
)
CONTROLLER = "altera_onchip_flash_avmm_data_controller.v"
STROBE = "altera_onchip_flash:u_flash|altera_onchip_flash_avmm_data_controller:avmm_data_controller|flash_se_neg_reg"
STROBE_WARNING = ("Warning (332060): Node: {node} was determined to be a clock but was found without an "
                  "associated clock assignment.")
# The fitter's own timing pass and the three quartus_sta corners each report
# the strobe once in compile.log; the audit's single netlist reports it once.
STROBE_COUNTS = {"compile.log": 4, "audit.log": 1}


def flash_target(target):
    """An image that places the flash reader, and therefore the IP."""
    return READER in target.get("sources", [])


def identity(directory):
    """Paths and hashes of the installed IP; a changed vendor file is unsupported."""
    quartus = Path(directory).resolve().parent
    ip = quartus.parent / "ip/altera" / IP_NAME
    paths = {name: ip / folder / name for name, (folder, _) in SOURCES.items()}
    paths.update({name: ip / IP_NAME / name for name in DEFINITIONS})
    paths["atom_model"] = quartus / "eda/sim_lib/fiftyfivenm_atoms.v"
    if any(not p.is_file() for p in paths.values()):
        raise ValueError("missing installed Intel On-Chip Flash IP dependency")
    result = {name: {"path": str(path), "sha256": file_hash(path)} for name, path in paths.items()}
    pinned = {name: sha for name, (_, sha) in SOURCES.items()} | DEFINITIONS
    for name, sha in pinned.items():
        if result[name]["sha256"] != sha:
            raise ValueError(f"unsupported Intel On-Chip Flash IP source: {name}")
    return result


def stage(folder, sources):
    """Copy the pinned synthesis files beside the generated project."""
    for name in SOURCES:
        source = Path(sources[name]["path"])
        if file_hash(source) != sources[name]["sha256"]:
            raise ValueError("Intel On-Chip Flash IP dependency changed before staging")
        shutil.copyfile(source, folder / name)


def assignments():
    return [f"set_global_assignment -name VERILOG_FILE {name}" for name in SOURCES] + [CONFIGURATION_MODE]


def verify(folder):
    """The fit placed the one UFM block and kept the compressed single image mode."""
    summary = (folder / "output/design.fit.summary").read_text(encoding="utf-8")
    blocks = re.findall(r"(?m)^UFM blocks\s*:\s*(\d+)\s*/\s*(\d+)", summary)
    if blocks != [("1", "1")]:
        raise ValueError("On-Chip Flash IP fit did not place the UFM block")
    qsf = (folder / "design.qsf").read_text(encoding="utf-8")
    if qsf.count(CONFIGURATION_MODE) != 1:
        raise ValueError("internal flash configuration mode assignment missing")
    return {"ufm_blocks": 1, "configuration_mode": "Single Comp Image",
            "sources": {name: file_hash(folder / name) for name in SOURCES}}


def strobe_node(top):
    """Fitted name of the IP's sense-enable strobe register under the given top."""
    if top not in READER_INSTANCES:
        raise ValueError("unsupported flash reader top for diagnostic classification")
    return f"n2m_flash_reader:{READER_INSTANCES[top]}|{STROBE}"


def no_clock_rows(top):
    """check_timing no-clock rows the IP adds: the strobe register and the atom register it clocks."""
    return (strobe_node(top),
            f"n2m_flash_reader:{READER_INSTANCES[top]}|altera_onchip_flash:u_flash|"
            "altera_onchip_flash_block:altera_onchip_flash_block|ufm_block~XE_YE_TO_SE_FF")


def explained_diagnostics(text, folder, sources, top, log_name):
    """Exact vendor read-only-mode and strobe diagnostics of the pinned IP.

    The data controller keeps its write and erase registers under a generate
    branch the read-only mode never reads, and the IP's sense-enable strobe
    clocks one register inside the UFM atom without a clock assignment; the
    vendor's own generated project suppresses that message
    (MESSAGE_DISABLE 332060). Here both are classified line by line: the
    complete inventory, the pinned source identity and the count per log
    must all match, and nothing is suppressed.
    """
    for name, (_, sha) in SOURCES.items():
        if sources.get(name, {}).get("sha256") != sha or file_hash(folder / name) != sha:
            raise ValueError("unsupported Intel On-Chip Flash IP source for diagnostic classification")
    lines = [line.strip() for line in text.splitlines()]
    required = []
    if log_name == "compile.log":
        path = (Path(folder) / CONTROLLER).resolve().as_posix()
        for line_number, name in UNUSED_OBJECTS:
            required.append(f'Warning (10036): Verilog HDL or VHDL warning at {CONTROLLER}({line_number}): '
                            f'object "{name}" assigned a value but never read File: {path} Line: {line_number}')
    strobe = STROBE_WARNING.format(node=strobe_node(top))
    for line in required:
        if lines.count(line) != 1:
            raise ValueError("missing or duplicate On-Chip Flash IP read-only diagnostic")
    if lines.count(strobe) != STROBE_COUNTS[log_name]:
        raise ValueError("On-Chip Flash IP strobe clock diagnostic count differs")
    actual = [line for line in lines if re.match(r"Warning \((10036|332060)\):", line)
              and CONTROLLER in line or line == strobe]
    if sorted(actual) != sorted(required + [strobe] * STROBE_COUNTS[log_name]):
        raise ValueError("unexpected On-Chip Flash IP diagnostic")
    return [{"code": re.match(r"Warning \((\d+)\)", line)[1], "text": line,
             "reason": "pinned Intel On-Chip Flash IP: read-only mode leaves the vendor write/erase registers "
                       "unread and its sense-enable strobe clocks one UFM atom register without a clock assignment"}
            for line in required + [strobe]]


def accepted_unconstrained_clock(count, target, report):
    """The one unconstrained clock of a flash image: the IP's sense-enable strobe.

    Only when exactly one clock is unconstrained and the report names that
    strobe register as the only unconstrained target. Every other
    unconstrained count stays a failure.
    """
    if not flash_target(target) or count != 1:
        return False
    rows = re.findall(r";\s*(\S+)\s*;\s*;\s*Base\s*;\s*Unconstrained\s*;", report)
    return rows == [strobe_node(target["top"])]
