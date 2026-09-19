"""Resolve the installed Intel On-Chip Flash IP and stage its accepted sources.

The IP is plain parameterised Verilog: n2m_flash_reader instantiates
altera_onchip_flash directly with the parameters its hw.tcl derives, so no
generator runs. The builder copies the four synthesis files into the attempt,
names them in the QSF and sets the internal configuration mode the contract
(wiki/src/rtl/storage/MAS_flash_library.md) requires.
"""
from pathlib import Path
import re
import shutil

from . import flash_library, vendor_sources
from .records import file_hash

READER = "src/rtl/storage/n2m_flash_reader.sv"
IP_NAME = "altera_onchip_flash"
# ip/altera/altera_onchip_flash: the synthesis fileset of
# altera_onchip_flash_hw_proc.tcl generate_synth for the parallel read-only
# configuration (no csr controller, no vendor SDC), each with the IP folder that
# holds it. Digests are not stated here: `identity` compares every installed file
# with the digest [the ledger](accepted_vendor_sources.json) accepted for that
# installation, and [the dependency record](dependencies.json) keeps the licence
# and the installation the first digests came from.
SOURCES = {
    "altera_onchip_flash.v": "altera_onchip_flash",
    "altera_onchip_flash_avmm_data_controller.v": "altera_onchip_flash",
    "altera_onchip_flash_util.v": "altera_onchip_flash",
    "altera_onchip_flash_block.v": "rtl",
}
DEFINITIONS = ("altera_onchip_flash_hw.tcl", "altera_onchip_flash_hw_proc.tcl")
CONFIGURATION_MODE = 'set_global_assignment -name INTERNAL_FLASH_UPDATE_MODE "Single Comp Image"'
# The reader's INIT_FILENAME parameter names the Intel HEX the assembler folds
# into the .pof user range; the file sits beside the generated project.
INIT_PARAMETER = "INIT_FILENAME"
POF = "output/design.pof"
# Reader instance path per registered top as (module, instance) pairs from
# the top down; a top not listed here has no classified flash diagnostics and
# fails on the first one. reader_path() gives the QSF instance path and
# strobe_node() the fitted netlist name.
READER_INSTANCES = {
    "flash_proof": (("n2m_flash_reader", "u_reader"),),
    "v05_proof": (("n2m_v05_system", "u_system"), ("n2m_boot_copier", "u_copier"), ("n2m_flash_reader", "u_reader")),
    "v05_controls_proof": (("n2m_controls_system", "u_controls"), ("n2m_v05_system", "u_system"),
                           ("n2m_boot_copier", "u_copier"), ("n2m_flash_reader", "u_reader")),
}
# Registers of the vendor data controller that only its read-and-write mode
# reads: Quartus 25.1 names each once with its line in the accepted file.
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
# the strobe once in compile.log; the audit reports it once per timing
# netlist update in its script (one for flash_proof, ten for the composed
# images whose audit walks three corners three times), read from audit.tcl.
STROBE_COUNTS = {"compile.log": 4}
STROBE_LOGS = ("compile.log", "audit.log")
AUDIT_UPDATE = "update_timing_netlist"


def flash_target(target):
    """An image that places the flash reader, and therefore the IP."""
    return READER in target.get("sources", [])


def identity(directory):
    """Paths, digests and accepted record of the installed IP.

    A file whose digest changed since this installation accepted it fails here,
    before any stage runs; a file this installation has never recorded is
    recorded and marked as such.
    """
    quartus = Path(directory).resolve().parent
    ip = quartus.parent / "ip/altera" / IP_NAME
    paths = {name: ip / folder / name for name, folder in SOURCES.items()}
    paths.update({name: ip / IP_NAME / name for name in DEFINITIONS})
    paths["atom_model"] = quartus / "eda/sim_lib/fiftyfivenm_atoms.v"
    if any(not p.is_file() for p in paths.values()):
        raise ValueError("missing installed Intel On-Chip Flash IP dependency")
    return vendor_sources.check(directory, paths)


def stage(folder, sources):
    """Copy the accepted synthesis files beside the generated project."""
    for name in SOURCES:
        source = Path(sources[name]["path"])
        if file_hash(source) != sources[name]["sha256"]:
            raise ValueError("Intel On-Chip Flash IP dependency changed before staging")
        shutil.copyfile(source, folder / name)


def init_assignment(top):
    """QSF parameter assignment naming library.hex on the reader instance."""
    return f'set_parameter -name {INIT_PARAMETER} "{flash_library.HEX_NAME}" -to "{reader_path(top)}"'


def assignments(top):
    return ([f"set_global_assignment -name VERILOG_FILE {name}" for name in SOURCES]
            + [CONFIGURATION_MODE, init_assignment(top)])


def verify(folder, top):
    """The fit placed the one UFM block, kept the compressed single image mode and the .pof holds the library."""
    summary = (folder / "output/design.fit.summary").read_text(encoding="utf-8")
    blocks = re.findall(r"(?m)^UFM blocks\s*:\s*(\d+)\s*/\s*(\d+)", summary)
    if blocks != [("1", "1")]:
        raise ValueError("On-Chip Flash IP fit did not place the UFM block")
    qsf = (folder / "design.qsf").read_text(encoding="utf-8")
    if qsf.count(CONFIGURATION_MODE) != 1 or qsf.count(init_assignment(top)) != 1:
        raise ValueError("internal flash configuration mode or library initialization assignment missing")
    words = flash_library.parse_verilog_hex((folder / flash_library.DAT_NAME).read_text(encoding="ascii"))
    hex_bytes = flash_library.parse_intel_hex((folder / flash_library.HEX_NAME).read_text(encoding="ascii"))
    if hex_bytes != dict(enumerate(flash_library.words_to_bytes(words))):
        raise ValueError("library.hex and library.dat define different words")
    return {"ufm_blocks": 1, "configuration_mode": "Single Comp Image",
            "sources": {name: file_hash(folder / name) for name in SOURCES},
            "init_filename": flash_library.HEX_NAME, "reader": reader_path(top),
            "pof": pof_evidence(folder / POF, words)}


def pof_evidence(path, words):
    """The .pof carries the library byte for byte in the user range and the compressed image fits CFM0.

    The assembler's .pof holds the flash content in address order after its
    header: the 736 KiB user range (UFM1, UFM0, CFM2, CFM1), then the 672 KiB
    CFM0, each 32-bit word bit-reversed (flash_library.pof_words). The user
    range is located by its exact expected bytes, so a shifted, reordered or
    altered library fails here, and CFM0 usage is the last programmed byte
    after it. The assembler enforces the CFM0 fit: a compressed image that
    does not fit produces no .pof at all, so the required .pof is the
    overflow evidence and the usage below is measured, not thresholded.
    """
    if not path.is_file() or not path.stat().st_size:
        raise ValueError("missing FPGA evidence: design.pof")
    pof = path.read_bytes()
    expected = flash_library.pof_words(flash_library.words_to_bytes(words))
    base = pof.find(expected)
    if base < 0 or pof.find(expected, base + 1) >= 0:
        raise ValueError("the .pof user range does not hold the assembled library exactly once")
    cfm0 = pof[base + flash_library.USER_BYTES:base + flash_library.USER_BYTES + flash_library.CFM0_BYTES]
    if len(cfm0) != flash_library.CFM0_BYTES:
        raise ValueError("the .pof ends before the CFM0 sector")
    used = len(cfm0.rstrip(b"\xFF"))
    programmed = sum(1 for byte in cfm0 if byte != 0xFF)
    return {"sha256": file_hash(path), "bytes": len(pof), "user_range_offset": base,
            "user_range_match": True, "library_bytes": len(words) * flash_library.WORD_BYTES,
            "cfm0_bytes": flash_library.CFM0_BYTES, "cfm0_used_bytes": used, "cfm0_programmed_bytes": programmed,
            "cfm0_spare_bytes": flash_library.CFM0_BYTES - used}


def reader_path(top):
    """QSF instance path of the reader under the given top (`set_parameter -to`)."""
    if top not in READER_INSTANCES:
        raise ValueError("unsupported flash reader top for diagnostic classification")
    return "|".join(instance for _, instance in READER_INSTANCES[top])


def reader_node(top):
    """Fitted netlist name of the reader instance under the given top."""
    reader_path(top)
    return "|".join(f"{module}:{instance}" for module, instance in READER_INSTANCES[top])


def strobe_node(top):
    """Fitted name of the IP's sense-enable strobe register under the given top."""
    return f"{reader_node(top)}|{STROBE}"


def no_clock_rows(top):
    """check_timing no-clock rows the IP adds: the strobe register and the atom register it clocks."""
    return (strobe_node(top),
            f"{reader_node(top)}|altera_onchip_flash:u_flash|"
            "altera_onchip_flash_block:altera_onchip_flash_block|ufm_block~XE_YE_TO_SE_FF")


def explained_diagnostics(text, folder, sources, top, log_name):
    """Exact vendor read-only-mode and strobe diagnostics of the installed IP.

    The data controller keeps its write and erase registers under a generate
    branch the read-only mode never reads, and the IP's sense-enable strobe
    clocks one register inside the UFM atom without a clock assignment; the
    vendor's own generated project suppresses that message
    (MESSAGE_DISABLE 332060). Here both are classified line by line: the
    complete inventory, the accepted source identity and the count per log
    must all match, and nothing is suppressed.
    """
    for name, digest in vendor_sources.require_accepted(sources, *SOURCES).items():
        if file_hash(folder / name) != digest:
            raise ValueError("staged Intel On-Chip Flash IP source differs from the accepted installed source")
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
    strobe_count = strobe_expected(folder, log_name)
    if lines.count(strobe) != strobe_count:
        raise ValueError("On-Chip Flash IP strobe clock diagnostic count differs")
    actual = [line for line in lines if re.match(r"Warning \((10036|332060)\):", line)
              and CONTROLLER in line or line == strobe]
    if sorted(actual) != sorted(required + [strobe] * strobe_count):
        raise ValueError("unexpected On-Chip Flash IP diagnostic")
    return [{"code": re.match(r"Warning \((\d+)\)", line)[1], "text": line,
             "reason": "accepted Intel On-Chip Flash IP: read-only mode leaves the vendor write/erase registers "
                       "unread and its sense-enable strobe clocks one UFM atom register without a clock assignment"}
            for line in required + [strobe]]


def strobe_expected(folder, log_name):
    """Strobe diagnostics a log must carry: fixed for compile.log, one per audit netlist update."""
    if log_name in STROBE_COUNTS:
        return STROBE_COUNTS[log_name]
    if log_name != "audit.log":
        raise ValueError("unsupported log for On-Chip Flash IP diagnostic classification")
    script = (Path(folder) / "audit.tcl").read_text(encoding="utf-8")
    return sum(1 for line in script.splitlines() if line.strip() == AUDIT_UPDATE)


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
