"""Program a checked board image onto the connected device; identity checked first.

Two images, one rule set: the volatile `.sof` configures the device over JTAG;
the `.pof` of a flash image writes the compressed bitstream into CFM0 and the
game library into the user range (wiki/src/rtl/storage/MAS_flash_library.md,
"Programming the flash"). Both are accepted only in place beside the attempt
record that lists them with their current hash.

Which programmer performs the volatile configuration is decided by
[fpga_jtag](fpga_jtag.py) from the tools present and from what each one reads,
because Quartus's JTAG daemon cannot reach the boards on every host that can.
The flash image stays with `quartus_pgm`: openFPGALoader's only MAX 10 path
writes the internal flash, and writing flash is not something a backend may
choose.
"""
from pathlib import Path, PurePath
import re
import time

from . import fpga_jtag
from .doctor import enumeration_runner, executable, execute
from .progress import Progress, display_path
from .records import file_hash, read_json

SUCCESS_LINE = fpga_jtag.SUCCESS_LINES[fpga_jtag.QUARTUS][0]
# What the retained program.log proves about the board after an operation.
DEVICE_UNCHANGED = "unchanged"      # the programmer never ran
DEVICE_CHANGED = "changed"          # the programmer reported its success line
DEVICE_UNCONFIRMED = "unconfirmed"  # the programmer ran without its success line
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


def repository_relative(root, path):
    """The portable record form of a located artifact: relative to the checkout, forward slashes.

    Both arguments are already located (absolute, resolved) path objects of
    one flavour; the flavour is kept, so pure Windows paths behave as on the
    Windows host. A UNC checkout such as `\\\\wsl.localhost\\Ubuntu\\home\\...`
    keeps its share as the anchor on both sides, so the record never compares
    the Windows-relative input string with the checkout root. A path outside
    the root is a ValueError; callers raise it before any JTAG operation.
    """
    if not isinstance(root, PurePath) or not isinstance(path, PurePath):
        raise TypeError("repository_relative takes located path objects")
    return path.relative_to(root).as_posix()


def device_state_after(folder):
    """What the operation directory proves about the board once the command has failed.

    Without `program.log`, no programmer ran. With a backend's own success
    signature in it, the device or its flash was written and only the host
    record failed afterwards. Any other log means a programmer ran and did not
    confirm success. Nothing here replays the programmer; the operator decides.
    Both backends' signatures are read, because neither one's wording can
    appear in the other's output.
    """
    log = Path(folder) / "program.log"
    if not log.is_file():
        return DEVICE_UNCHANGED
    return (DEVICE_CHANGED if fpga_jtag.programmed(log.read_text(encoding="utf-8", errors="replace"))
            else DEVICE_UNCONFIRMED)


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
    relative = repository_relative(root.resolve(), image.resolve())
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


def expected_board(root, record, fpga_target):
    """The board the registry gives the target that produced this image.

    The registry is the source of truth for every board's device, so the check
    generalises to each supported board instead of naming one device. A record
    that names no registered target has no expected device and is refused: with
    nothing to compare, an image for one board could reach another. A record
    that carries its own `device` must agree with the registry, so a record
    edited after the build cannot move the expectation.
    """
    expected = fpga_jtag.expected_device(root, fpga_target)
    built = record.get("device")
    if built is not None and built != expected["device"]:
        raise ValueError(f"the attempt record's device {built} is not the {expected['board']} device "
                         f"{expected['device']} its target is registered with")
    return expected


def volatile_image(folder, quartus_bin, sof, timeout):
    """Derive the raw volatile image openFPGALoader loads from the checked `.sof`.

    openFPGALoader has no `.sof` reader. The raw image is derived by
    `quartus_cpf` from the already checked file into the operation directory,
    never beside the attempt, and the record carries its hash, so the chain of
    custody still starts at the attempt record. The conversion reads the `.sof`
    and touches no device.
    """
    rbf = Path(folder) / "design.rbf"
    output = execute(fpga_jtag.convert_command(executable(quartus_bin, "quartus_cpf"), sof, rbf),
                     folder, "convert.log", timeout)
    if fpga_jtag.CONVERT_SUCCESS_LINE not in output or not rbf.is_file() or not rbf.stat().st_size:
        raise RuntimeError("quartus_cpf did not produce a raw volatile image; see convert.log")
    return rbf


def program(root, folder, sof, *, quartus_bin, cable=None, timeout=60, progress=None,
            programmer="auto", openfpgaloader_bin=None, probe_firmware=None):
    """Verify the attached chain is the board this image was built for, then program it.

    `sof` must be an existing file under `root`, in place beside the attempt
    record that lists it with its current hash. That record's target names the
    board, and the registry gives that board's device: the chain must report
    exactly one of them before anything is written, so a DE10-Lite image cannot
    reach a Cyclone V. Nothing here inspects the bitstream's own target device.

    The chain is re-read for this operation, never carried over from an earlier
    command, and the backend that read it is the backend that writes. Between
    the read and the write the openFPGALoader path derives its raw image with
    `quartus_cpf`, which reads the checked `.sof` and writes only into the
    operation directory; no device is touched until the write itself.
    """
    progress = progress or Progress(False)
    folder = Path(folder)
    sof = Path(sof)
    label = "Check FPGA build record"
    started = progress.begin(label)
    try:
        record, on_wire, fpga_target = checked_attempt(root, sof)
        expected = expected_board(root, record, fpga_target)
        # Every recorded path is derived here, before JTAG. The path is
        # checked as given (a link is refused unresolved) and recorded
        # resolved, so the record after a successful write needs no
        # further path arithmetic that could fail it.
        located = sof.resolve()
        raw_image = display_path(root, folder / "design.rbf")
        result = {"sof": repository_relative(Path(root).resolve(), located),
                  **({"build_id": record["build_id"], "wire_build_id": on_wire} if on_wire else {}),
                  **({"fpga_target": fpga_target} if fpga_target else {}),
                  "board": expected["board"], "family": expected["family"],
                  "expected_device": expected["device"],
                  "chain_log": display_path(root, folder / "chain.log"),
                  "program_log": display_path(root, folder / "program.log")}
    except Exception as error:
        diagnostic = folder / "failure.log"
        diagnostic.write_text(str(error) + "\n", encoding="utf-8")
        progress.finish(label, started, "FAIL",
                        f"diagnostic: {display_path(root, diagnostic)}")
        raise
    else:
        progress.finish(label, started)
    with progress.stage("Discover JTAG chain", f"log: {result['chain_log']}"):
        chain = fpga_jtag.enumerate_chain(
            root, folder, enumeration_runner(folder, fpga_jtag.DETECT_TIMEOUT, execute),
            programmer=programmer, quartus_bin=quartus_bin, openfpgaloader_bin=openfpgaloader_bin, cable=cable,
            probe_firmware=probe_firmware or fpga_jtag.firmware_path(quartus_bin), expected=expected)
    backend = chain["backend"]
    index = chain["index"]
    device_names = [device["name"] for device in chain["devices"] if device["name"]]
    progress.line(f"JTAG: backend {backend}; cable {index}; device {', '.join(device_names)}")
    extra = {}
    if backend == fpga_jtag.OPENFPGALOADER:
        if expected["family"] in fpga_jtag.FLASH_ONLY_FAMILIES:
            # Not a limit of this repository: openFPGALoader sends every MAX 10
            # to its internal-flash path before it looks at the file or the
            # requested mode, so there is no volatile configuration to ask for.
            raise RuntimeError(f"openFPGALoader has no volatile configuration for the {expected['family']} "
                               f"{expected['device']}; its only path for that family writes the internal "
                               "flash. Program this board with quartus_pgm.")
        with progress.stage("Derive raw volatile image", f"image: {raw_image}"):
            # The programmer identifies itself into the record before it writes:
            # nothing pins this tool, so the record has to say which one wrote.
            identity = fpga_jtag.version(execute(fpga_jtag.version_command(chain["tool"]),
                                                 folder, "version.log", fpga_jtag.DETECT_TIMEOUT))
            image = volatile_image(folder, quartus_bin, located, timeout)
            extra = {"volatile_image": raw_image, "volatile_image_sha256": file_hash(image),
                     "backend_version": identity["release"], "backend_banner": identity["banner"]}
        command = fpga_jtag.sram_command(chain["tool"], index, chain["position"], image,
                                         chain["probe_firmware"])
        scope = ("JTAG configuration only; openFPGALoader shifts the bitstream and reports Done without "
                 "reading CONF_DONE back, so it does not itself prove configuration completed, "
                 "UART or VGA behavior")
    else:
        command = [executable(quartus_bin, "quartus_pgm"), "-c", index, "-m", "jtag", "-o", f"p;{located}"]
        scope = "JTAG configuration only; does not itself prove UART or VGA behavior"
    with progress.stage("Program FPGA", f"log: {result['program_log']}"):
        output = execute(command, folder, "program.log", timeout)
    with progress.stage("Check programmer result", success="PASS"):
        if not all(fragment in output for fragment in fpga_jtag.SUCCESS_LINES[backend]):
            raise RuntimeError(f"{backend} did not report a successful configuration; see program.log")
    return {**result, **extra, "devices": device_names, "cable": index, "chain": chain,
            "backend": backend, "backend_tool": chain["tool"], "chain_position": chain["position"],
            "command": command, "output": output.strip(), "device_state": DEVICE_CHANGED, "scope": scope}


def program_flash(root, folder, pof, *, quartus_bin, cable=None, timeout=FLASH_TIMEOUT, dry_run=False,
                  progress=None):
    """Write a checked flash image (`.pof`) into the MAX 10 internal flash over JTAG.

    The record checks of `checked_flash_attempt` run first and write
    `failure.log` on refusal. `dry_run` stops there: it writes the exact
    `quartus_pgm` command to `dry-run.log` with `<cable>` in place of the
    chain index and never runs `jtagconfig` or `quartus_pgm`. Otherwise the
    chain is re-read through `jtagconfig` and must report exactly one cable
    holding the device its target's board is registered with, then
    `quartus_pgm -m jtag -o "pvb;<pof>"` runs under `timeout`; the in-system
    programming time is measured around that call and the explicit success line
    is required. The backend is not chosen here: openFPGALoader's only MAX 10
    path writes the internal flash through its own POF parser, and a flash
    write follows the documented `quartus_pgm` operation letters and timing,
    not a substitute.
    """
    progress = progress or Progress(False)
    folder = Path(folder)
    pof = Path(pof)
    label = "Check flash image record"
    started = progress.begin(label)
    try:
        record, on_wire, fpga_target, evidence = checked_flash_attempt(root, pof)
        expected = expected_board(root, record, fpga_target)
        # Every recorded path is derived here, before JTAG; see `program`.
        located = pof.resolve()
        checkout = Path(root).resolve()
        result = {"pof": repository_relative(checkout, located), "pof_sha256": evidence["sha256"],
                  "operation": FLASH_OPERATION, "configuration_mode": CONFIGURATION_MODE,
                  "cfm0_used_bytes": evidence.get("cfm0_used_bytes"),
                  "attempt_result": repository_relative(checkout, located.parent.parent / "result.json"),
                  **({"build_id": record["build_id"], "wire_build_id": on_wire} if on_wire else {}),
                  **({"fpga_target": fpga_target} if fpga_target else {}),
                  "board": expected["board"], "family": expected["family"],
                  "expected_device": expected["device"], "next_step": NEXT_STEP}
        logs = {"chain_log": display_path(root, folder / "chain.log"),
                "program_log": display_path(root, folder / "program.log")}
    except Exception as error:
        diagnostic = folder / "failure.log"
        diagnostic.write_text(str(error) + "\n", encoding="utf-8")
        progress.finish(label, started, "FAIL",
                        f"diagnostic: {display_path(root, diagnostic)}")
        raise
    else:
        progress.finish(label, started)
    if dry_run:
        command = flash_command("quartus_pgm", cable or "<cable>", pof)
        log = folder / "dry-run.log"
        log.write_text(" ".join(command) + "\n", encoding="utf-8")
        progress.line(f"Dry run: {' '.join(command)}")
        return {**result, "dry_run": True, "command": command, "dry_run_log": display_path(root, log),
                "device_state": DEVICE_UNCHANGED,
                "scope": "record checks and command construction only; no JTAG access, flash unchanged"}
    with progress.stage("Discover JTAG chain", f"log: {logs['chain_log']}"):
        chain = fpga_jtag.enumerate_chain(
            root, folder, enumeration_runner(folder, fpga_jtag.DETECT_TIMEOUT, execute), programmer=fpga_jtag.QUARTUS,
            quartus_bin=quartus_bin, cable=cable, expected=expected)
    index = chain["index"]
    device_names = [device["name"] for device in chain["devices"] if device["name"]]
    progress.line(f"JTAG: backend {chain['backend']}; cable {index}; device {', '.join(device_names)}")
    command = flash_command(executable(quartus_bin, "quartus_pgm"), index, located)
    with progress.stage("Program flash", f"log: {logs['program_log']}"):
        begun = time.monotonic()
        output = execute(command, folder, "program.log", timeout)
        isp_seconds = round(time.monotonic() - begun, 3)
    with progress.stage("Check programmer result", success="PASS"):
        if SUCCESS_LINE not in output:
            raise RuntimeError("quartus_pgm did not report a successful flash program, verify and blank-check; "
                               "see program.log")
    return {**result, **logs, "devices": device_names, "cable": index, "chain": chain, "command": command,
            "backend": chain["backend"], "backend_tool": chain["tool"], "chain_position": chain["position"],
            "isp_seconds": isp_seconds, "output": output.strip(), "device_state": DEVICE_CHANGED,
            "scope": "JTAG flash programming with verify and blank-check; the menu at power-up is the board check"}
