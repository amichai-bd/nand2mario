"""Program a checked MAX 10 .sof onto the connected board; identity checked first."""
from pathlib import Path

from .doctor import executable, execute, parse_jtag
from .records import file_hash, read_json


def attempt_record(root, sof):
    """The attempt record that produced `output/design.sof`, or a refusal.

    Fails closed: a missing or malformed record, a `.sof` the record does not
    list with its current hash (copied, moved or altered), or a record whose
    BUILD_ID was pinned by `--build-id` all refuse programming.
    """
    record = read_json(sof.parent.parent / "result.json")
    if not record:
        raise ValueError("no readable attempt record (result.json) beside the .sof output directory")
    listed = record.get("artifacts", {}) if isinstance(record.get("artifacts"), dict) else {}
    relative = sof.resolve().relative_to(root.resolve()).as_posix()
    if listed.get(relative) != file_hash(sof):
        raise ValueError("the .sof is not the artifact its attempt record lists; program only an unmodified design.sof in place")
    if record.get("build_id_override"):
        raise ValueError("refusing to program a comparison-only build: its BUILD_ID was pinned by --build-id")
    return record


def program(root, folder, sof, *, quartus_bin, cable=None, timeout=60):
    """Verify the selected USB-Blaster reports the expected device, then program it.

    `sof` must be an existing file under `root`, in place beside the attempt
    record that lists it; nothing here inspects the bitstream's own target device, so a `.sof` built for another device is
    refused by `quartus_pgm` itself, not by this check. Chain identity is
    re-read with a fresh `jtagconfig` immediately before `quartus_pgm` runs; a
    stale or ambiguous chain, or more than one matching chain, refuses to
    program.
    """
    sof = Path(sof)
    if (not sof.is_file() or sof.suffix != ".sof" or sof.is_symlink()
            or not sof.resolve().is_relative_to(root.resolve())):
        raise ValueError("missing or unsafe .sof path")
    attempt_record(root, sof)
    chain = parse_jtag(execute([executable(quartus_bin, "jtagconfig")], folder, "chain.log"), cable)
    index = chain["selected"]["index"]
    output = execute([executable(quartus_bin, "quartus_pgm"), "-c", index, "-m", "jtag",
                      "-o", f"p;{sof.resolve()}"], folder, "program.log", timeout)
    if "Quartus Prime Programmer was successful. 0 errors, 0 warnings" not in output:
        raise RuntimeError("quartus_pgm did not report a successful configuration; see program.log")
    return {"devices": [device["name"] for device in chain["selected"]["devices"]],
            "cable": index, "sof": sof.relative_to(root).as_posix(),
            "chain": chain, "output": output.strip(),
            "scope": "JTAG configuration only; does not itself prove UART or VGA behavior"}
