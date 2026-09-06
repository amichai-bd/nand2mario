"""Reproduce the bounded CPU fixture from the reviewed immutable source archive."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

PIN = "f9c30210245dd691661db39f5ace022c465ecc2f"
ARCHIVE_SHA256 = "0a492d69b69cff0d440c9f795a6528c9374a4b771465fbbf42606c98492ab2f2"
ROOT = Path(__file__).resolve().parent / "singlestep"


def registers(state: dict) -> int:
    fields = [(state[k], 8) for k in ("a", "f", "b", "c", "d", "e", "h", "l")]
    fields += [(state[k], 16) for k in ("sp", "pc")]
    packed = offset = 0
    for value, width in fields:
        if not isinstance(value, int) or not 0 <= value < 1 << width:
            raise ValueError("invalid source register")
        packed |= value << offset
        offset += width
    return packed


def instruction_length(opcode: int) -> int:
    # Original enumeration of the documented immediate operand forms. This is
    # independent of the product decoder and the assembler's encoding data.
    if opcode > 255:
        return 2
    if opcode in (0x01, 0x11, 0x21, 0x31, 0x08, 0xC2, 0xCA, 0xD2,
                  0xDA, 0xC3, 0xC4, 0xCC, 0xD4, 0xDC, 0xCD, 0xEA, 0xFA):
        return 3
    if opcode in (0x06, 0x0E, 0x16, 0x1E, 0x26, 0x2E, 0x36, 0x3E,
                  0x18, 0x20, 0x28, 0x30, 0x38, 0xC6, 0xCE, 0xD6,
                  0xDE, 0xE6, 0xEE, 0xF6, 0xFE, 0xE0, 0xF0, 0xE8, 0xF8):
        return 2
    return 1


def pack(case: dict, opcode: int, index: int) -> int:
    initial, final, cycles = case["initial"], case["final"], case["cycles"]
    if len(initial["ram"]) > 8 or len(final["ram"]) > 8 or len(cycles) > 6:
        raise ValueError("source exceeds reviewed fixture bounds")
    value = registers(initial) | registers(final) << 96
    value |= len(initial["ram"]) << 192 | len(final["ram"]) << 196
    value |= len(cycles) << 200 | instruction_length(opcode) << 204
    value |= opcode << 206 | index << 215
    for offset, rows in ((225, initial["ram"]), (417, final["ram"])):
        for address, byte in rows:
            if not 0 <= address <= 65535 or not 0 <= byte <= 255:
                raise ValueError("invalid source RAM byte")
            value |= (address | byte << 16) << offset
            offset += 24
    for offset, (address, byte, flags) in enumerate(cycles):
        if flags not in ("r-m", "-wm", "---"):
            raise ValueError("unknown source bus flags")
        row = (address or 0) | (byte or 0) << 16
        row |= {"---": 0, "r-m": 1, "-wm": 2}[flags] << 24
        row |= (address is not None) << 26 | (byte is not None) << 27
        value |= row << (609 + 28 * offset)
    return value


def generate(archive: Path) -> dict[str, bytes]:
    data = archive.read_bytes()
    if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("source archive integrity mismatch")
    metadata = {"pin": PIN, "archive_sha256": ARCHIVE_SHA256,
                "url": f"https://codeload.github.com/SingleStepTests/sm83/zip/{PIN}",
                "selection": "first vector for every initial F high nibble in each opcode file",
                "sources": [], "cases": [], "missing_flags": [],
                "exclusions": {"10": "STOP model/timing uses independent directed tests",
                               "76": "HALT model/timing uses independent directed tests",
                               "interrupt_fields": "upstream IME/IE/EI are not reliable expectations"}}
    lines = ["// Selected MIT-licensed SingleStepTests data; see manifest.json and LICENSE."]
    with zipfile.ZipFile(archive) as z:
        prefix = f"sm83-{PIN}/"
        files = sorted(n for n in z.namelist() if n.startswith(prefix + "v1/") and n.endswith(".json"))
        if len(files) != 500:
            raise ValueError("unexpected source opcode inventory")
        for name in files:
            raw = z.read(name)
            relative = name.removeprefix(prefix)
            metadata["sources"].append({"path": relative, "sha256": hashlib.sha256(raw).hexdigest(),
                "git_blob": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()})
            stem = Path(name).stem
            opcode = 256 + int(stem[3:], 16) if stem.startswith("cb ") else int(stem, 16)
            selected = {}
            for index, case in enumerate(json.loads(raw)):
                flags = case["initial"]["f"]
                if flags & 15:
                    raise ValueError("source requires invalid F low nibble")
                selected.setdefault(flags >> 4, (index, case))
            absent = sorted(set(range(16)) - selected.keys())
            if absent:
                metadata["missing_flags"].append({"path": relative, "flags": absent})
            for flags, (index, case) in sorted(selected.items()):
                number = len(metadata["cases"])
                metadata["cases"].append({"source": relative, "index": index,
                                          "name": case["name"], "flags": flags})
                lines.append(f"vector_data[{number}] = 1024'h{pack(case, opcode, index):0256x};")
        license_bytes = z.read(prefix + "LICENSE")
    metadata["count"] = len(metadata["cases"])
    return {"vectors.svh": ("\n".join(lines) + "\n").encode(),
            "manifest.json": (json.dumps(metadata, indent=2) + "\n").encode(),
            "LICENSE": license_bytes}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, data in generate(args.archive).items():
        path = ROOT / name
        if args.check:
            if path.read_bytes() != data:
                raise SystemExit(f"generated fixture differs: {name}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print("PASS selected CPU fixture reproducibility" if args.check else "Generated selected CPU fixture")


if __name__ == "__main__":
    main()
