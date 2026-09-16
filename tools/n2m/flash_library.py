"""Assemble the flash-resident game library image from the registered packages.

Contract: wiki/src/rtl/storage/MAS_flash_library.md. The library mirrors the
SDRAM layout word for word from flash word 0x00800: flash_word(a) = 0x00800 +
(a >> 2) for SDRAM device byte address a. The On-Chip Flash IP's Avalon data
slave, its Intel HEX initialization file and the Verilator double's $readmemh
image all number the same words from 0 (the contract's Terms: "every image the
IP or its double loads is written in the 0-based Avalon numbering"), so:

    avalon_word(a) = flash_word(a) - 0x00800 = a >> 2
    Intel HEX byte address of slot byte b of slot i = 4 * avalon_word = i * 32768 + b

The catalogue entry bytes come from one code path, tools/n2m/host/library.py,
so the host loader and the flash image cannot disagree. Slots the registry
leaves empty and the reserved range are omitted from both files and read
erased (0xFFFFFFFF).
"""
import json
from pathlib import Path
import re
from types import SimpleNamespace
import zlib

from .host import library
from .records import atomic_json, file_hash

REGISTRY = "src/fpga/de10_lite/library.json"
SW_REGISTRY = "src/sw/targets.json"
# Flash geometry of the 10M50 in the single compressed image mode
# (n2m_flash_pkg mirrors these for the RTL; the contract owns them).
FLASH_DATA_BASE = 0x00800
USER_WORDS = 0x2E000
USER_BYTES = USER_WORDS * 4
CFM0_BYTES = 84 * 8192
WORD_BYTES = 4
RECORD_BYTES = 16
ERASED_WORD = 0xFFFFFFFF
HEX_NAME = "library.hex"
DAT_NAME = "library.dat"
CATALOGUE_NAME = "catalogue.bin"
NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")


def flash_word(address):
    """Contract mapping of an SDRAM device byte address to its flash word."""
    return FLASH_DATA_BASE + (address >> 2)


def avalon_word(address):
    """The IP's 0-based data word of an SDRAM device byte address."""
    return flash_word(address) - FLASH_DATA_BASE


def load_registry(root):
    """The validated slot registry: {index: package name} and the menu package name."""
    root = Path(root)
    data = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    if (not isinstance(data, dict) or set(data) != {"schema_version", "slots", "menu"}
            or type(data["schema_version"]) is not int or data["schema_version"] != 1
            or not isinstance(data["slots"], dict) or not data["slots"]):
        raise ValueError("unsupported flash library registry schema")
    packages = json.loads((root / SW_REGISTRY).read_text(encoding="utf-8"))
    if not isinstance(packages, dict) or not isinstance(packages.get("targets"), dict):
        raise ValueError("unsupported software target registry")
    slots = {}
    for key, name in data["slots"].items():
        if not re.fullmatch(r"(0|[1-9][0-9]?)", key) or not 0 <= int(key) < library.GAME_SLOTS:
            raise ValueError(f"flash library slot must be 0..{library.GAME_SLOTS - 1}: {key!r}")
        slots[int(key)] = name
    for index, name in sorted(slots.items()) + [(library.MENU_INDEX, data["menu"])]:
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise ValueError(f"invalid flash library package name at {library.slot_name(index)}")
        package = packages["targets"].get(name)
        if not isinstance(package, dict) or package.get("profile") not in library.PROFILE_IDS:
            raise ValueError(f"flash library {library.slot_name(index)} names no packaged software target: {name}")
    if packages["targets"][data["menu"]]["profile"] != library.LOADER_PROFILE_NAME:
        raise ValueError(f"the menu image must run in {library.LOADER_PROFILE_NAME}")
    names = list(slots.values()) + [data["menu"]]
    if len(set(names)) != len(names):
        raise ValueError("a package may occupy only one flash library slot")
    return {"slots": slots, "menu": data["menu"], "sha256": file_hash(root / REGISTRY)}


def build_images(root, build, registry, provenance, rebuild=False):
    """Build every registered package under this tag; {index: (image, profile, package report)}."""
    from sw.rom_build import build_target
    images = {}
    for index, name in sorted(registry["slots"].items()) + [(library.MENU_INDEX, registry["menu"])]:
        report = build_target(root, build, SimpleNamespace(target=name, rebuild=rebuild), provenance)
        if report.get("status") != "PASS":
            raise ValueError(f"software build of {name} failed: {report.get('error', 'no error recorded')}")
        rom = Path(root) / report["rom"]
        image = rom.read_bytes()
        if file_hash(rom) != report["artifacts"].get(report["rom"]) or len(image) != library.SLOT_BYTES:
            raise ValueError(f"software build of {name} left no complete {library.SLOT_BYTES}-byte image")
        images[index] = (image, report["profile"], {"package": name, "attempt": report["attempt"],
                                                    "result": (Path(root) / report["rom"]).parent.joinpath("result.json").relative_to(Path(root)).as_posix(),
                                                    "image_sha256": report["artifacts"][report["rom"]],
                                                    "fingerprint": report["fingerprint"]})
    return images


def assemble(images):
    """Words of the library in the IP's 0-based numbering, the catalogue and its rows.

    ``images`` is {index: (image, profile_name[, extra])}; every other slot is empty.
    """
    words = {}
    entries = {}
    rows = []
    for index in sorted(images):
        image, profile = images[index][0], images[index][1]
        image = bytes(image)
        if type(index) is not int or not 0 <= index < library.IMAGE_COUNT:
            raise ValueError(f"library index must be 0..{library.MENU_INDEX}")
        if len(image) != library.SLOT_BYTES or len(image) % WORD_BYTES:
            raise ValueError(f"library image must be exactly one {library.SLOT_BYTES}-byte slot")
        entry = library.image_entry(image, library.profile_id(profile))
        entries[index] = entry
        base = avalon_word(library.slot_address(index))
        for offset in range(0, len(image), WORD_BYTES):
            words[base + offset // WORD_BYTES] = int.from_bytes(image[offset:offset + WORD_BYTES], "little")
        row = library.describe(index, entry)
        row.update(flash_word=f"0x{flash_word(library.slot_address(index)):05X}", profile_name=profile)
        if len(images[index]) > 2:
            row.update(images[index][2])
        rows.append(row)
    if library.MENU_INDEX not in entries:
        raise ValueError("the flash library requires the menu image at index 16")
    catalogue = library.build_catalogue(entries)
    base = avalon_word(library.CATALOGUE_ADDRESS)
    for offset in range(0, len(catalogue), WORD_BYTES):
        words[base + offset // WORD_BYTES] = int.from_bytes(catalogue[offset:offset + WORD_BYTES], "little")
    if max(words) >= USER_WORDS:
        raise ValueError("library words exceed the user range")
    return {"words": words, "catalogue": catalogue, "rows": rows}


def intel_hex(words):
    """Intel HEX of the words, byte addressed at 4 * avalon word, 16 bytes per record.

    Records are type 00 data, type 04 extended linear address at each 64 KiB
    boundary and one type 01 end record; every record carries its checksum.
    """
    lines = []
    upper = None

    def record(kind, address, data):
        body = bytes([len(data), address >> 8, address & 0xFF, kind]) + data
        return ":" + (body + bytes([(-sum(body)) & 0xFF])).hex().upper()

    for start in sorted({word - word % (RECORD_BYTES // WORD_BYTES) for word in words}):
        data = b"".join((words.get(word, ERASED_WORD)).to_bytes(WORD_BYTES, "little")
                        for word in range(start, start + RECORD_BYTES // WORD_BYTES))
        address = start * WORD_BYTES
        if address >> 16 != upper:
            upper = address >> 16
            lines.append(record(0x04, 0, upper.to_bytes(2, "big")))
        lines.append(record(0x00, address & 0xFFFF, data))
    lines.append(record(0x01, 0, b""))
    return "\n".join(lines) + "\n"


def verilog_hex(words):
    """Word-addressed Verilog hex for the double's $readmemh: one @<avalon word> <word> line each."""
    return "".join(f"@{word:05X} {value:08X}\n" for word, value in sorted(words.items()))


def parse_intel_hex(text):
    """{byte address: byte} of an Intel HEX text, checking every record's checksum."""
    result = {}
    upper = 0
    ended = False
    for number, line in enumerate(text.splitlines(), 1):
        if not line:
            continue
        if ended or not re.fullmatch(r":[0-9A-F]+", line) or len(line) % 2 == 0:
            raise ValueError(f"malformed Intel HEX record at line {number}")
        body = bytes.fromhex(line[1:])
        if sum(body) & 0xFF or len(body) != body[0] + 5:
            raise ValueError(f"Intel HEX checksum or length mismatch at line {number}")
        kind, address, data = body[3], int.from_bytes(body[1:3], "big"), body[4:-1]
        if kind == 0x04 and len(data) == 2:
            upper = int.from_bytes(data, "big")
        elif kind == 0x00:
            for offset, value in enumerate(data):
                result[(upper << 16) + address + offset] = value
        elif kind == 0x01 and not data:
            ended = True
        else:
            raise ValueError(f"unsupported Intel HEX record type at line {number}")
    if not ended:
        raise ValueError("Intel HEX without an end record")
    return result


def parse_verilog_hex(text):
    words = {}
    for number, line in enumerate(text.splitlines(), 1):
        match = re.fullmatch(r"@([0-9A-F]{5}) ([0-9A-F]{8})", line)
        if not match:
            raise ValueError(f"malformed word record at line {number}")
        words[int(match[1], 16)] = int(match[2], 16)
    return words


def words_to_bytes(words, count=USER_BYTES):
    """The user range as flash bytes, erased where undefined."""
    image = bytearray(b"\xFF" * count)
    for word, value in words.items():
        image[word * WORD_BYTES:(word + 1) * WORD_BYTES] = value.to_bytes(WORD_BYTES, "little")
    return bytes(image)


def write(folder, assembled):
    """Write library.hex, library.dat and catalogue.bin into the folder; return their hashes."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / HEX_NAME).write_text(intel_hex(assembled["words"]), encoding="ascii", newline="\n")
    (folder / DAT_NAME).write_text(verilog_hex(assembled["words"]), encoding="ascii", newline="\n")
    (folder / CATALOGUE_NAME).write_bytes(assembled["catalogue"])
    return {name: file_hash(folder / name) for name in (HEX_NAME, DAT_NAME, CATALOGUE_NAME)}


def summary(registry, assembled, hashes, folder, root):
    folder = Path(folder)
    return {"registry": {"path": REGISTRY, "sha256": registry["sha256"]},
            "convention": "Intel HEX byte address = 4 * (flash word - 0x00800); library.dat @<avalon word> records",
            "images": assembled["rows"], "defined_words": len(assembled["words"]),
            "catalogue_flash_word": f"0x{flash_word(library.CATALOGUE_ADDRESS):05X}",
            "catalogue_crc32": f"{zlib.crc32(assembled['catalogue']):08x}",
            "files": {name: {"path": (folder / name).relative_to(root).as_posix(), "sha256": sha}
                      for name, sha in hashes.items()}}


def library_stage(root, build, args, provenance):
    """`sw library`: build the registered packages and write the flash image files under sw/library."""
    import uuid
    root = Path(root)
    stage = build / "sw/library"
    folder = stage / "runs" / uuid.uuid4().hex[:12]
    folder.mkdir(parents=True)
    report = {"status": "FAIL", **provenance, "attempt": folder.name}
    try:
        registry = load_registry(root)
        images = build_images(root, build, registry, provenance, rebuild=getattr(args, "rebuild", False))
        assembled = assemble(images)
        hashes = write(folder, assembled)
        report.update(status="PASS", library=summary(registry, assembled, hashes, folder, root),
                      artifacts={(folder / name).relative_to(root).as_posix(): sha for name, sha in hashes.items()})
    except Exception as error:
        report.update(error=str(error))
        (folder / "failure.log").write_text(str(error) + "\n", encoding="utf-8")
        report["artifacts"] = {(folder / "failure.log").relative_to(root).as_posix(): file_hash(folder / "failure.log")}
    atomic_json(folder / "result.json", report)
    atomic_json(stage / "result.json", report)
    return report
