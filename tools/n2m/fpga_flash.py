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
