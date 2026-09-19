"""Which programmer reaches the board, and whether the chain is the expected device.

Two programmers exist. Quartus's `jtagconfig` and `quartus_pgm` own the MAX 10
internal flash path and the verified Windows configuration path.
`openFPGALoader` exists because Quartus's `jtagd` reads neither attached cable
on the Linux development host while `openFPGALoader` enumerates them; missing
shared libraries, device permissions, udev rules, stale daemon state and
interference from `openFPGALoader` were each ruled out by measurement, the two
cables fail with two different errors, and the daemon itself was never
diagnosed. Programming from Linux would otherwise be unavailable even though
the hardware is reachable.

Neither programmer is trusted to name the board. Both print a device string for
every chain position, and the expected device comes from the board registry of
the target that produced the image, so an image built for one board cannot be
written to another. `openFPGALoader --detect` returns success whatever it read,
including an empty chain and a garbled one, so the parsed and matched identity
is the only judge of what is attached.

Every function here is pure or takes the caller's runner: nothing in this
module launches a process, so the same selection and matching rules are read by
`doctor` read-only and by `fpga_program` before a write.
"""
import os
from pathlib import Path
import re
import shutil

from . import fpga

QUARTUS = "quartus"
OPENFPGALOADER = "openfpgaloader"
# Discovery order. Quartus owns the verified path and the flash image, so it is
# tried first and only an unusable chain falls through to openFPGALoader.
BACKENDS = (QUARTUS, OPENFPGALOADER)
PROGRAMMER_CHOICES = ("auto", *BACKENDS)
# openFPGALoader names cables, not chain indices. These are the two Altera
# cables the supported boards carry: the DE10-Lite and DE2-115 expose the
# FTDI-based USB-Blaster, the DE10-Nano a USB-Blaster II.
CABLES = ("usb-blaster", "usb-blasterII")
# How `jtagconfig` names those cables, measured on the attached hardware:
# `USB-Blaster [1-2]` for the FTDI-based cable, `DE-SoC [1-3.2]` for the
# USB-Blaster II Terasic builds into the SoC boards. A chain on any other
# hardware is not a programming cable of a supported board and is never
# selected, however the device on it reads.
PROBE_NAMES = ("USB-Blaster", "DE-SoC")
# The USB-Blaster II holds its FX2 firmware in volatile memory, so
# openFPGALoader has to upload it on every attach and refuses the cable without
# a path to it. Quartus ships the image beside its Linux executables.
PROBE_FIRMWARE = "blaster_6810.hex"
# A healthy enumeration answers in under a second. These bound a read
# independently of the write it precedes, so several cable attempts cannot spend
# a flash timeout between them. `jtagconfig` keeps the 60 seconds it has always
# had, because the slow case is a cold Windows `jtagd` and shortening it would
# change that host's behavior. `openFPGALoader --detect` gets less: it talks to
# the cable itself, and a probe that needs longer than this is failing.
CHAIN_TIMEOUT = 60
DETECT_TIMEOUT = 30

# What proves a device was written, per backend. `quartus_pgm` states its own
# result. openFPGALoader's SRAM load names the operation and then prints `Done`
# from its progress bar; it shifts the bitstream without reading CONF_DONE
# back, so `Done` proves the transfer, not that configuration completed.
SUCCESS_LINES = {QUARTUS: ("Quartus Prime Programmer was successful. 0 errors, 0 warnings",),
                 OPENFPGALOADER: ("Load SRAM", "Done")}
CONVERT_SUCCESS_LINE = "Quartus Prime Convert_programming_file was successful. 0 errors, 0 warnings"
SCOPE = "reported JTAG identity only; no wiring, voltage, or programming proof"
# openFPGALoader v1.1.1 `Altera::program` routes on family before it looks at the
# file or the requested mode: `if (_fpga_family == MAX10_FAMILY) {
# max10_program(offset); return; }`. So the `MEM_MODE` its constructor does set
# for an `.rbf` under `--write-sram` is discarded, and there is no volatile MAX 10
# path to select. `max10_program` then branches on the extension: only a `.pof`
# goes through `POFParser`, and anything else -- including the `.rbf` this backend
# builds -- goes to `max10_program_ufm`, which reads it with `RawParser` and,
# with no `--flash-sector` given, calls `max10_flow_erase` with mask `0x3` and
# `writeXFM`. That erases and rewrites UFM1+UFM0, the internal flash region this
# repository's game library lives in.
#
# On the DE10-Lite's own part that release aborts before any flash access, because
# `max10_memory_map` holds only `10M08SAU`, `10M16SA` and `10M25SA` and the
# 10M50's IDCODE `0x031050dd` is not among them: `Model not supported. Please
# update max10_memory_map.`. That makes this refusal necessary rather than
# redundant -- the only thing between a `.sof` and a UFM erase on the qualified
# board is a missing table entry any later release may fill -- so the family is
# refused outright and no release is trusted into that path. The MAX 10 stays
# with `quartus_pgm`.
FLASH_ONLY_FAMILIES = ("MAX 10",)
# A chain device name is a `/`-separated list of the ordering codes one IDCODE
# covers. `(...)` is a revision group and `*` stands for the package family
# letters: `jtagconfig` prints `10M50DA(.|ES)/10M50DC` and `openFPGALoader`
# prints `5CSE*A6/5CSX*6`.
REVISION_GROUP = re.compile(r"\([^()]*\)")
# The shortest real alternative is six characters: `10M50D`, and `5CSE*A6` once
# its package wildcard is removed. A shorter one is a truncated or garbled read,
# and must not prefix-match a legitimate ordering code.
ALTERNATIVE_LENGTH = 6


def locate(directory, name):
    """The resolved executable, or None when it is not there.

    `doctor.executable` is the same lookup in its raising form: an explicit
    directory first, then PATH, and never a fallback from an explicit
    selection. This form is the probe, used where an absent tool selects
    another backend rather than failing.
    """
    candidate = str(Path(directory) / (name + (".exe" if os.name == "nt" else ""))) if directory else name
    found = shutil.which(candidate)
    return str(Path(found).resolve()) if found else None


def device_matches(device, reported):
    """Whether one reported chain device is the board whose ordered part is `device`.

    An alternative matches when it is a prefix of the ordering code, because
    the ordering code continues with the package, speed and temperature grade
    no IDCODE carries: `10M50DA` is the DE10-Lite's `10M50DAF484C7G`, `5CSE*A6`
    is the DE10-Nano's `5CSEBA6U23I7`, and `EP4CE115` is the DE2-115's
    `EP4CE115F29C7`. Nothing here distinguishes two parts that share an
    IDCODE, because the device cannot either.
    """
    if not isinstance(device, str) or not re.fullmatch(r"[A-Za-z0-9]+", device):
        raise ValueError("invalid expected device")
    for alternative in str(reported).split("/"):
        stripped = REVISION_GROUP.sub("", alternative).strip()
        if (not re.fullmatch(r"[A-Za-z0-9*]+", stripped)
                or len(stripped.replace("*", "")) < ALTERNATIVE_LENGTH):
            continue
        pattern = "".join("[A-Za-z0-9]*" if part == "*" else re.escape(part)
                          for part in re.split(r"(\*)", stripped))
        if re.match(pattern, device, re.IGNORECASE):
            return True
    return False


def expected_device(root, target):
    """The board the registry gives the target that produced an image.

    The registry is the source of truth. A target the registry does not define
    has no expected device, so there is nothing to check the chain against and
    programming refuses.
    """
    if not isinstance(target, str) or not target:
        raise ValueError("the attempt record names no FPGA target, so the expected device is unknown")
    entry = fpga.board_registries(root).get(target)
    if entry is None:
        raise ValueError(f"the attempt record names an unregistered FPGA target: {target}")
    _, board, _ = entry
    return {"target": target, "board": board["name"], "family": board["family"], "device": board["device"]}


def registered_boards(root):
    """Every supported board, keyed by its device, for a check with no target."""
    boards = {}
    for _, board, _ in fpga.board_registries(root).values():
        boards[board["device"]] = {"board": board["name"], "family": board["family"], "device": board["device"]}
    return boards


def parse_jtagconfig(output):
    """Every chain `jtagconfig` printed, in order, with the devices it read.

    A cable whose chain could not be read still prints its header, so a chain
    with no devices is a real result and not a parse failure.
    """
    chains = []
    for line in str(output).splitlines():
        header = re.match(r"^\s*(\d+)\)\s+(.+)$", line)
        if header:
            chains.append({"index": header[1], "name": header[2].strip(), "devices": [],
                           "probe": any(name in header[2] for name in PROBE_NAMES)})
            continue
        device = re.match(r"^\s+([0-9a-fA-F]{8})\s+(.+)$", line)
        if device and chains:
            chains[-1]["devices"].append({"idcode": device[1].upper(), "name": device[2].strip()})
    return chains


def parse_detect(output, cable):
    """The one chain `openFPGALoader --detect` read on `cable`.

    Each position prints `index <n>:` and then either a known FPGA's `idcode`,
    `manufacturer`, `family`, `model` and `irlength`, or a known non-FPGA
    device's `idcode`, `type` and `irlength`. A position openFPGALoader does
    not know at all prints its header alone, and is kept as an unnamed device
    so it still occupies its place in the chain.
    """
    devices = []
    for line in str(output).splitlines():
        if re.match(r"^index\s+\d+:\s*$", line):
            devices.append({"idcode": "", "name": ""})
            continue
        field = re.match(r"^\s+(idcode|model|type)\s+(\S.*)$", line)
        if not field or not devices:
            continue
        value = field[2].strip()
        if field[1] == "idcode":
            devices[-1]["idcode"] = value.upper().removeprefix("0X").rjust(8, "0")
        else:
            devices[-1]["name"] = value
    return [{"index": cable, "name": cable, "devices": devices, "probe": True}]


def select(chains, expected, cable=None):
    """The one probe chain holding exactly one device of the expected board.

    Refuses zero and refuses more than one, on either axis: two cables that
    both report the board, or one chain that reports it twice, are ambiguous
    and no write follows. Other devices in the chain are allowed and keep
    their place, because a Cyclone V SoC chain also carries its ARM debug
    access port. The returned `position` is where the matched device sits, so
    the programmer addresses that position and not the tool's own guess.
    """
    matches = []
    for chain in chains:
        if not chain.get("probe") or (cable is not None and chain["index"] != cable):
            continue
        found = [i for i, device in enumerate(chain["devices"])
                 if device["name"] and device_matches(expected["device"], device["name"])]
        if len(found) == 1:
            matches.append({**chain, "position": found[0], "matched": chain["devices"][found[0]]})
        elif len(found) > 1:
            raise RuntimeError(f"chain {chain['index']} reports {expected['device']} "
                               f"({expected['board']}) at {len(found)} positions; refusing an ambiguous chain")
    if len(matches) != 1:
        named = ", ".join(match["index"] for match in matches)
        raise RuntimeError(f"expected exactly one cable reporting {expected['device']} "
                           f"({expected['board']}); found {len(matches)}"
                           + (f": {named}" if named else ""))
    return {**matches[0], "expected": expected, "scope": SCOPE}


def select_any(chains, boards, cable=None):
    """The one chain and the one supported board it reports, for a check with no target.

    `doctor` has no image and so no expected target. Exactly one registered
    board must be found, so a chain holding two supported devices, or none, is
    reported as the failure it is rather than resolved by preference order.
    """
    found = []
    for expected in boards.values():
        try:
            found.append(select(chains, expected, cable))
        except RuntimeError:
            continue
    if len(found) != 1:
        named = ", ".join(f"{one['expected']['device']} on {one['index']}" for one in found)
        raise RuntimeError("expected exactly one cable reporting exactly one supported board device "
                           f"({', '.join(sorted(boards))}); found {len(found)}"
                           + (f": {named}" if named else ""))
    return found[0]


# openFPGALoader prints `openFPGALoader v1.1.1`. The version is recorded rather
# than pinned: the repository does not ship this tool, and a record that cannot
# say which programmer wrote a board is not evidence. The MAX 10 refusal does not
# depend on the version, so a newer release is not trusted into that path either.
VERSION_BANNER = re.compile(r"openFPGALoader\s+v(\d+\.\d+(?:\.\d+)?)")


def version_command(tool):
    """The read-only banner that identifies the programmer for the record."""
    return [tool, "--Version"]


def version(output):
    """The recorded openFPGALoader release, or a refusal naming the banner."""
    found = VERSION_BANNER.search(str(output))
    if not found:
        raise RuntimeError("unrecognized openFPGALoader version banner; see version.log")
    return {"release": found[1], "banner": found[0]}


def detect_command(tool, cable, probe_firmware=None):
    """The read-only `openFPGALoader` enumeration for one cable."""
    return [tool, "-c", cable, *(["--probe-firmware", str(probe_firmware)] if probe_firmware else []), "--detect"]


def sram_command(tool, cable, position, image, probe_firmware=None):
    """The exact `openFPGALoader` argument list that configures the device volatile.

    `--file-type rbf` names the raw configuration image explicitly rather than
    leaving it to the file name, `--index-chain` addresses the matched chain
    position instead of openFPGALoader's own first-FPGA guess, and
    `--write-sram` asks for the volatile load. No flash option is ever
    constructed here.
    """
    return [tool, "-c", cable, *(["--probe-firmware", str(probe_firmware)] if probe_firmware else []),
            "--index-chain", str(position), "--file-type", "rbf", "--write-sram",
            "--bitstream", str(Path(image).resolve())]


def convert_command(quartus_cpf, sof, rbf):
    """The exact `quartus_cpf` argument list that derives the raw volatile image.

    openFPGALoader has no `.sof` reader: its Altera device accepts `svf`, `rbf`
    and `rpd`, and refuses any other extension under `--write-sram`. The raw
    image is derived from the already checked `.sof` into the operation
    directory, and the record carries its hash, so the chain of custody still
    starts at the attempt record.
    """
    return [quartus_cpf, "-c", str(Path(sof).resolve()), str(Path(rbf).resolve())]


def programmed(output):
    """Whether a retained programmer log carries a backend's own success signature.

    Both signatures are read because the log alone decides what a failed
    operation proves about the device, and no signature of one backend can
    appear in the other's output.
    """
    text = str(output)
    return any(all(fragment in text for fragment in fragments) for fragments in SUCCESS_LINES.values())


def firmware_path(quartus_bin):
    """Quartus's FX2 firmware image beside its Linux executables, when it is there."""
    if not quartus_bin:
        return None
    candidate = Path(quartus_bin).parent / "linux64" / PROBE_FIRMWARE
    return str(candidate) if candidate.is_file() else None


# Everything an enumeration prints as chain data, so none of it is mistaken for a
# complaint: `openFPGALoader`'s position header and its fields, `jtagconfig`'s
# cable header and its device lines, and openFPGALoader's bare `empty` notice for
# a cable list it could not fill.
CHAIN_DATA = (re.compile(r"^index\s+\d+:\s*$"),
              re.compile(r"^\s*\d+\)\s+\S"),
              re.compile(r"^\s+(?:idcode|manufacturer|family|model|type|irlength)\s"),
              re.compile(r"^\s+[0-9a-fA-F]{8}\s+\S"),
              re.compile(r"^empty\s*$"))


# Words the tools use when a read went wrong. This only picks which retained line
# to quote in a refusal a person reads; nothing branches on it, and the whole log
# is kept either way.
TROUBLE = re.compile(r"unable|cannot|error|fail|missing|broken|not attached|not supported|problem",
                     re.IGNORECASE)


def complaint(output):
    """The tool's own complaint about a read, or nothing when it did not make one.

    Chain data never explains a failure: the garbled probe's last line is
    `irlength 8`, and `jtagconfig` prints `Unable to read device chain` indented
    where a device line would sit. Neither does an info line the tool prints on
    its way: that probe announces its firmware version before the `FX2 write
    error` that actually explains it, so a line naming trouble is preferred over
    the first line. A read that succeeded and was merely not selected has no
    complaint to make, and says so by returning nothing.
    """
    lines = [line.strip() for line in str(output).splitlines()
             if line.strip() and not any(shape.match(line) for shape in CHAIN_DATA)]
    return next((line for line in lines if TROUBLE.search(line)), lines[0] if lines else "")


def _reason(backend, error, reads):
    """One line naming why a backend was not used, with each read's own complaint.

    `reads` pairs each cable, where the backend names one, with that
    enumeration's output, so a backend rejected across several cables says what
    each cable answered rather than only the last.
    """
    details = []
    for label, output in reads:
        line = complaint(output)
        if line:
            details.append(f"{label}: {line}" if label else line)
    return f"{backend}: {error}" + (f" ({'; '.join(details)})" if details else "")


def _attempts(programmer, quartus_bin, openfpgaloader_bin, cable, probe_firmware):
    """Every enumeration this host can attempt, grouped by backend in discovery order.

    One group is one backend's complete view of the host: `jtagconfig` prints
    every chain in one command, while `openFPGALoader` reads one cable per
    command, so its group holds one attempt per cable. A backend is judged on
    its whole group, never on the first cable that answers. A backend whose tool
    is absent contributes no group and its own reason, so a host with neither
    tool is refused by name rather than by operating system.

    One `--jtag-cable` serves both backends because each names cables its own
    way: an openFPGALoader cable name selects that backend and that cable, and
    any other value is a `jtagconfig` chain index. Omitted, every cable is
    enumerated and the one reporting the expected board is selected.
    """
    groups, missing = [], []
    if programmer in ("auto", QUARTUS) and cable not in CABLES:
        tool = locate(quartus_bin, "jtagconfig")
        if tool:
            groups.append((QUARTUS, [{"log": "chain-quartus.log", "cable": None, "argv": [tool],
                                      "tool": tool, "timeout": CHAIN_TIMEOUT}]))
        else:
            missing.append("jtagconfig (Quartus)")
    if programmer in ("auto", OPENFPGALOADER):
        tool = locate(openfpgaloader_bin, "openFPGALoader")
        if tool:
            groups.append((OPENFPGALOADER,
                           [{"log": f"chain-openfpgaloader-{name}.log", "cable": name, "tool": tool,
                             "timeout": DETECT_TIMEOUT,
                             "argv": detect_command(tool, name, probe_firmware)}
                            for name in ([cable] if cable in CABLES else CABLES)]))
        else:
            missing.append("openFPGALoader")
    return groups, missing


def enumerate_chain(root, folder, run, *, programmer="auto", quartus_bin=None, openfpgaloader_bin=None,
                    cable=None, probe_firmware=None, expected=None):
    """Read the chain through the first backend whose whole view reports the expected board.

    Every cable a backend can reach is enumerated before anything is selected,
    so `exactly one cable` means the same on either backend: two cables that
    both hold the board are ambiguous and refused, not resolved by read order.
    Reading every cable is what makes that refusal possible, and an enumeration
    is read-only, so it costs nothing a write depends on.

    `run(argv, log, timeout)` returns the command's output whether it succeeded
    or not: `openFPGALoader --detect` returns success whatever it read, and a
    probe that failed has already written its own reason into its log. Only the
    parsed and matched identity selects a backend, so a Quartus daemon that
    answers without reading a chain falls through instead of being trusted.

    `expected` is the board the image was built for. Without it, as in the
    read-only doctor check, exactly one registered board must be reported.
    The selected chain's own log becomes `chain.log`: it is the enumeration the
    programmer acted on, and every other read keeps its own name.
    """
    # A pinned backend and a cable the other one names is a contradiction, not a
    # preference: silently ignoring either half would program through a
    # programmer or a cable the operator did not choose.
    if programmer == QUARTUS and cable in CABLES:
        raise ValueError(f"--jtag-cable {cable} names an openFPGALoader cable, "
                         "but --programmer quartus selects a jtagconfig chain index")
    if programmer == OPENFPGALOADER and cable is not None and cable not in CABLES:
        raise ValueError(f"--jtag-cable {cable} is not an openFPGALoader cable; "
                         "use one of " + ", ".join(CABLES))
    # With an image there is one expected board; without one, every registered
    # board is a candidate and the registry is read for them.
    boards = registered_boards(root) if expected is None else {}
    groups, missing = _attempts(programmer, quartus_bin, openfpgaloader_bin, cable, probe_firmware)
    if not groups:
        raise RuntimeError("no JTAG programmer found: missing " + " and ".join(missing)
                           + "; select a tool directory explicitly")
    reasons = [f"{name}: not found on this host" for name in missing]
    for backend, group in groups:
        # Read the backend's every cable first. Selecting inside the loop would
        # return on the first cable that matched and never read the second, so
        # two cables holding the board would be accepted here and refused by
        # `jtagconfig`, which prints them both in one command.
        chains, reads, source = [], [], {}
        for attempt in group:
            output = run(attempt["argv"], attempt["log"], attempt["timeout"])
            reads.append((attempt["cable"], output))
            read = (parse_jtagconfig(output) if backend == QUARTUS
                    else parse_detect(output, attempt["cable"]))
            for chain in read:
                source[chain["index"]] = attempt
            chains += read
        wanted = cable if backend == QUARTUS else (cable if cable in CABLES else None)
        try:
            selected = (select(chains, expected, wanted) if expected
                        else select_any(chains, boards, wanted))
        except (RuntimeError, ValueError) as error:
            reasons.append(_reason(backend, error, reads))
            continue
        attempt = source[selected["index"]]
        used = Path(folder) / attempt["log"]
        if used.is_file():
            os.replace(used, Path(folder) / "chain.log")
        return {**selected, "backend": backend, "tool": attempt["tool"],
                "command": attempt["argv"], "chains": chains,
                "probe_firmware": probe_firmware if backend == OPENFPGALOADER else None,
                "rejected": reasons}
    raise RuntimeError("no JTAG programmer reported the expected device; " + "; ".join(reasons))
