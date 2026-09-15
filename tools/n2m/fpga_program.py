"""Program a checked MAX 10 .sof onto the connected board; identity checked first."""
from pathlib import Path
import re

from .doctor import executable, execute, parse_jtag
from .progress import Progress, display_path
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


def wire_build_id(record):
    """Return the UART byte order for a checked build identity, when present."""
    build_id = record.get("build_id")
    if build_id is None:
        return None
    if not isinstance(build_id, str) or not re.fullmatch(r"[0-9a-f]{32}", build_id) or int(build_id, 16) == 0:
        raise ValueError("attempt record carries an invalid build_id")
    return bytes.fromhex(build_id)[::-1].hex()


def program(root, folder, sof, *, quartus_bin, cable=None, timeout=60, progress=None):
    """Verify the selected USB-Blaster reports the expected device, then program it.

    `sof` must be an existing file under `root`, in place beside the attempt
    record that lists it. A producing target carried by that record must be a
    valid target name; callers use it only for target-specific handoffs.
    Nothing here inspects the bitstream's own target device, so a `.sof` built
    for another device is refused by `quartus_pgm` itself, not by this check. Chain identity is
    re-read with a fresh `jtagconfig` immediately before `quartus_pgm` runs; a
    stale or ambiguous chain, or more than one matching chain, refuses to
    program.
    """
    progress = progress or Progress(False)
    folder = Path(folder)
    sof = Path(sof)
    label = "Check FPGA build record"
    started = progress.begin(label)
    try:
        if (not sof.is_file() or sof.suffix != ".sof" or sof.is_symlink()
                or not sof.resolve().is_relative_to(root.resolve())):
            raise ValueError("missing or unsafe .sof path")
        record = attempt_record(root, sof)
        on_wire = wire_build_id(record)
        fpga_target = record.get("target")
        if (fpga_target is not None
                and (not isinstance(fpga_target, str)
                     or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", fpga_target))):
            raise ValueError("attempt record carries an invalid FPGA target")
    except Exception as error:
        diagnostic = folder / "failure.log"
        diagnostic.write_text(str(error) + "\n", encoding="utf-8")
        progress.finish(label, started, "FAIL",
                        f"diagnostic: {display_path(root, diagnostic)}")
        raise
    else:
        progress.finish(label, started)
    with progress.stage("Discover JTAG chain", f"log: {display_path(root, folder / 'chain.log')}"):
        chain = parse_jtag(execute([executable(quartus_bin, "jtagconfig")], folder, "chain.log"), cable)
    index = chain["selected"]["index"]
    device_names = [device["name"] for device in chain["selected"]["devices"]]
    progress.line(f"JTAG: cable {index}; device {', '.join(device_names)}")
    with progress.stage("Program FPGA", f"log: {display_path(root, folder / 'program.log')}"):
        output = execute([executable(quartus_bin, "quartus_pgm"), "-c", index, "-m", "jtag",
                          "-o", f"p;{sof.resolve()}"], folder, "program.log", timeout)
    with progress.stage("Check programmer result", success="PASS"):
        if "Quartus Prime Programmer was successful. 0 errors, 0 warnings" not in output:
            raise RuntimeError("quartus_pgm did not report a successful configuration; see program.log")
    return {"devices": device_names,
            "cable": index, "sof": sof.relative_to(root).as_posix(),
            "chain": chain, "output": output.strip(),
            **({"build_id": record["build_id"], "wire_build_id": on_wire} if on_wire else {}),
            **({"fpga_target": fpga_target} if fpga_target else {}),
            "chain_log": display_path(root, folder / "chain.log"),
            "program_log": display_path(root, folder / "program.log"),
            "scope": "JTAG configuration only; does not itself prove UART or VGA behavior"}
