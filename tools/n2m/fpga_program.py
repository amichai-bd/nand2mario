"""Program a checked MAX 10 image onto the connected board; identity checked first.

Two images, one rule set: the volatile `.sof` configures the device over JTAG;
the `.pof` of a flash image writes the compressed bitstream into CFM0 and the
game library into the user range (wiki/src/rtl/storage/MAS_flash_library.md,
"Programming the flash"). Both are accepted only in place beside the attempt
record that lists them with their current hash.
"""
from pathlib import Path
import re
import time

from .doctor import executable, execute, parse_jtag
from .progress import Progress, display_path
from .records import file_hash, read_json

SUCCESS_LINE = "Quartus Prime Programmer was successful. 0 errors, 0 warnings"
# quartus_pgm operation letters for the flash image: program, verify and
# blank-check. `quartus_pgm --help=o` of Quartus Prime 25.1std Lite lists
# BPV among the valid combinations and gives "JTAG Program: -o pvb;file.pof"
# as its own example, so the letters are used in that documented order.
FLASH_OPERATION = "pvb"
CONFIGURATION_MODE = "Single Comp Image"
# The MAX 10 configuration guide (UG-M10CONFIG Table 4) gives 52.9 s for
# CFM0, 22.7 s for CFM1 and 30.2 s for CFM2 on the 10M50 before verify and
# system overhead; the whole pvb pass must finish inside this bound.
FLASH_TIMEOUT = 600
NEXT_STEP = ("Power-cycle the DE10-Lite with no host attached; a bitstream with the boot copier "
             "shows the menu from flash.")


def attempt_record(root, image):
    """The attempt record that produced `output/design.sof` or `output/design.pof`, or a refusal.

    Fails closed: a missing or malformed record, an image the record does not
    list with its current hash (copied, moved or altered), or a record whose
    BUILD_ID was pinned by `--build-id` all refuse programming.
    """
    record = read_json(image.parent.parent / "result.json")
    if not record:
        raise ValueError(f"no readable attempt record (result.json) beside the {image.suffix} output directory")
    listed = record.get("artifacts", {}) if isinstance(record.get("artifacts"), dict) else {}
    relative = image.resolve().relative_to(root.resolve()).as_posix()
    if listed.get(relative) != file_hash(image):
        raise ValueError(f"the {image.suffix} is not the artifact its attempt record lists; "
                         f"program only an unmodified design{image.suffix} in place")
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


def checked_attempt(root, sof, suffix=".sof"):
    """Apply the programmer's complete pre-JTAG artifact checks."""
    root = Path(root)
    sof = Path(sof)
    if (not sof.is_file() or sof.suffix != suffix or sof.is_symlink()
            or not sof.resolve().is_relative_to(root.resolve())):
        raise ValueError(f"missing or unsafe {suffix} path")
    record = attempt_record(root, sof)
    on_wire = wire_build_id(record)
    fpga_target = record.get("target")
    if (fpga_target is not None
            and (not isinstance(fpga_target, str)
                 or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", fpga_target))):
        raise ValueError("attempt record carries an invalid FPGA target")
    return record, on_wire, fpga_target


def checked_flash_attempt(root, pof):
    """The `.sof` checks plus the flash image's own evidence.

    The record must be a passing build in the single compressed image mode
    whose `.pof` check matched the assembled library once and whose recorded
    `.pof` hash is the file's current hash; anything else refuses to write
    flash.
    """
    record, on_wire, fpga_target = checked_attempt(root, pof, suffix=".pof")
    if record.get("status") != "PASS":
        raise ValueError("refusing to program flash from an attempt that did not pass its checks")
    flash = record.get("evidence", {}).get("onchip_flash") if isinstance(record.get("evidence"), dict) else None
    if not isinstance(flash, dict):
        raise ValueError("attempt record carries no on-chip flash evidence; build a flash image target")
    if flash.get("configuration_mode") != CONFIGURATION_MODE:
        raise ValueError(f"attempt record does not show the {CONFIGURATION_MODE!r} configuration mode")
    evidence = flash.get("pof")
    if (not isinstance(evidence, dict) or evidence.get("user_range_match") is not True
            or evidence.get("sha256") != file_hash(pof)):
        raise ValueError("attempt record does not show a passing .pof check for this file")
    return record, on_wire, fpga_target, evidence


def flash_command(quartus_pgm, cable, pof):
    """The exact quartus_pgm argument list that programs, verifies and blank-checks the .pof."""
    return [quartus_pgm, "-c", cable, "-m", "jtag", "-o", f"{FLASH_OPERATION};{Path(pof).resolve()}"]


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
        record, on_wire, fpga_target = checked_attempt(root, sof)
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
        if SUCCESS_LINE not in output:
            raise RuntimeError("quartus_pgm did not report a successful configuration; see program.log")
    return {"devices": device_names,
            "cable": index, "sof": sof.relative_to(root).as_posix(),
            "chain": chain, "output": output.strip(),
            **({"build_id": record["build_id"], "wire_build_id": on_wire} if on_wire else {}),
            **({"fpga_target": fpga_target} if fpga_target else {}),
            "chain_log": display_path(root, folder / "chain.log"),
            "program_log": display_path(root, folder / "program.log"),
            "scope": "JTAG configuration only; does not itself prove UART or VGA behavior"}


def program_flash(root, folder, pof, *, quartus_bin, cable=None, timeout=FLASH_TIMEOUT, dry_run=False,
                  progress=None):
    """Write a checked flash image (`.pof`) into the MAX 10 internal flash over JTAG.

    The record checks of `checked_flash_attempt` run first and write
    `failure.log` on refusal. `dry_run` stops there: it writes the exact
    `quartus_pgm` command to `dry-run.log` with `<cable>` in place of the
    chain index and never runs `jtagconfig` or `quartus_pgm`. Otherwise the
    chain is re-read and must report exactly one USB-Blaster with a 10M50DA,
    then `quartus_pgm -m jtag -o "pvb;<pof>"` runs under `timeout`; the
    in-system programming time is measured around that call and the explicit
    success line is required.
    """
    progress = progress or Progress(False)
    folder = Path(folder)
    pof = Path(pof)
    label = "Check flash image record"
    started = progress.begin(label)
    try:
        record, on_wire, fpga_target, evidence = checked_flash_attempt(root, pof)
    except Exception as error:
        diagnostic = folder / "failure.log"
        diagnostic.write_text(str(error) + "\n", encoding="utf-8")
        progress.finish(label, started, "FAIL",
                        f"diagnostic: {display_path(root, diagnostic)}")
        raise
    else:
        progress.finish(label, started)
    result = {"pof": pof.relative_to(root).as_posix(), "pof_sha256": evidence["sha256"],
              "operation": FLASH_OPERATION, "configuration_mode": CONFIGURATION_MODE,
              "cfm0_used_bytes": evidence.get("cfm0_used_bytes"),
              "attempt_result": (pof.parent.parent / "result.json").relative_to(root).as_posix(),
              **({"build_id": record["build_id"], "wire_build_id": on_wire} if on_wire else {}),
              **({"fpga_target": fpga_target} if fpga_target else {}),
              "next_step": NEXT_STEP}
    if dry_run:
        command = flash_command("quartus_pgm", cable or "<cable>", pof)
        log = folder / "dry-run.log"
        log.write_text(" ".join(command) + "\n", encoding="utf-8")
        progress.line(f"Dry run: {' '.join(command)}")
        return {**result, "dry_run": True, "command": command, "dry_run_log": display_path(root, log),
                "scope": "record checks and command construction only; no JTAG access, flash unchanged"}
    with progress.stage("Discover JTAG chain", f"log: {display_path(root, folder / 'chain.log')}"):
        chain = parse_jtag(execute([executable(quartus_bin, "jtagconfig")], folder, "chain.log"), cable)
    index = chain["selected"]["index"]
    device_names = [device["name"] for device in chain["selected"]["devices"]]
    progress.line(f"JTAG: cable {index}; device {', '.join(device_names)}")
    command = flash_command(executable(quartus_bin, "quartus_pgm"), index, pof)
    with progress.stage("Program flash", f"log: {display_path(root, folder / 'program.log')}"):
        begun = time.monotonic()
        output = execute(command, folder, "program.log", timeout)
        isp_seconds = round(time.monotonic() - begun, 3)
    with progress.stage("Check programmer result", success="PASS"):
        if SUCCESS_LINE not in output:
            raise RuntimeError("quartus_pgm did not report a successful flash program, verify and blank-check; "
                               "see program.log")
    return {**result, "devices": device_names, "cable": index, "chain": chain, "command": command,
            "isp_seconds": isp_seconds, "output": output.strip(),
            "chain_log": display_path(root, folder / "chain.log"),
            "program_log": display_path(root, folder / "program.log"),
            "scope": "JTAG flash programming with verify and blank-check; the menu at power-up is the board check"}
