"""Carry one packaged ROM image in the bitstream, so a board runs with no host.

A target may declare `rom_image`, a `src/sw/targets.json` package name. The
builder runs that package's software build, hands the result to the existing
[preload packager](preload.py) and names the `.mif` it writes on the ROM store
instance through the QSF, exactly as the flash image is named on the flash
reader. The packager owns the length, digest and header/checksum checks, so this
module introduces no second way to describe a ROM: a failing image raises here
and the build records FAIL.

`n2m_intel_ram` takes the file as its `INIT_FILE` parameter and suppresses the
vendor power-up initialization only for a store that declares none, so one
declaration serves both simulation and synthesis. Reaching one instance through
a QSF parameter rather than a macro keeps every target that declares no image
byte-identical, in its generated project files and in its RTL preprocessing.
"""
import json
from pathlib import Path
import re
from types import SimpleNamespace

from . import fpga_flash
from . import generated_interfaces as abi
from . import preload
from .profiles import DIRECT_PROFILE_NAME
from .records import file_hash

SW_REGISTRY = "src/sw/targets.json"
# The packager's ROM file, the same name and shape the simulation preload loads.
MIF_NAME = "preload-rom.mif"
IMAGE_NAME = "program.gb"
# The wrapper parameter a QSF assignment names on one store instance.
INIT_PARAMETER = "INIT_FILE"
# The profile whose whole image is the ROM store's lower half. The loader
# profile and its flash library stay the DE10-Lite's path and are not carried
# here; a target declaring any other profile refuses the build by name.
CARRIED_PROFILE = DIRECT_PROFILE_NAME
# ROM store instance path under each registered top, from the top down. A top
# absent here cannot carry an image and refuses the declaration by name.
ROM_INSTANCES = {"n2m_memory_stores": ("rom",),
                 "de2_system_proof": ("u_system", "u_stores", "rom")}
PACKAGE_NAME = re.compile(r"[a-z0-9][a-z0-9_-]*")
# The ROM store's depth, which the packager's file addresses in full, and the
# addresses one fitted M9K block of it holds.
STORE_BYTES = abi.PROFILE_STORE_BYTES
BLOCK_ADDRESSES = 8192
# A MAX 10 configures itself from its own flash, and its configuration mode
# decides whether that flash carries embedded RAM contents at all: without ERAM
# the fitter refuses memory initialization outright (Quartus 16031). A family
# absent here states nothing extra, which is how a board that configures from an
# external device keeps the assignments it always had. The compressed image
# matches the mode the flash library already builds with.
CONFIGURATION_MODES = {"MAX 10": "Single Comp Image with ERAM"}
CONFIGURATION_SETTING = "INTERNAL_FLASH_UPDATE_MODE"
# Quartus reports the addresses a partial initialization file leaves out and the
# zero it writes there. The image occupies the store's first bytes, so the
# remainder is stated rather than discovered; both lines are checked verbatim
# against the declared image length.
UNINITIALIZED = ('Warning (113028): {absent} out of {depth} addresses are uninitialized. The Quartus Prime '
                 'software will initialize them to "0". There are 1 warnings found, and 1 warnings are '
                 'reported. File: {file} Line: 1')
UNINITIALIZED_RANGE = ("Warning (113027): Addresses ranging from {first} to {last} are not initialized "
                       "File: {file} Line: 1")

# Quartus writes each generated memory megafunction's parameters, as the RTL
# gave them, on the first line of the .tdf it generates for that shape. Its name
# is fitter-chosen, so the store that carries an image is found by its file.
MEGAFUNCTION = "db/altsyncram_*.tdf"
MEGAFUNCTION_PARAMETER = r'{name}="([^"]*)"'


def declared(target):
    """The declared package name, or None for a target that carries no image."""
    return target.get("rom_image")


def validate(root, target):
    """Check the declaration before any tool runs; a bad one names itself."""
    package = declared(target)
    if not isinstance(package, str) or not PACKAGE_NAME.fullmatch(package):
        raise ValueError("invalid carried ROM image package name")
    if target["top"] not in ROM_INSTANCES:
        raise ValueError(f"top carries no ROM store to initialize: {target['top']}")
    if fpga_flash.flash_target(target):
        # Both want one MAX 10 internal configuration mode and would state two;
        # the flash library is the other way to reach a program without a host.
        raise ValueError("a target carries either a ROM image or the flash library, not both")
    definitions = json.loads((Path(root) / SW_REGISTRY).read_text(encoding="utf-8"))
    entry = definitions.get("targets", {}).get(package)
    if not isinstance(entry, dict) or entry.get("profile") != CARRIED_PROFILE:
        raise ValueError(f"carried ROM image must be a packaged {CARRIED_PROFILE} software target: {package}")


def rom_path(top):
    """QSF instance path of the ROM store under this top (`set_parameter -to`)."""
    if top not in ROM_INSTANCES:
        raise ValueError(f"top carries no ROM store to initialize: {top}")
    return "|".join(ROM_INSTANCES[top])


def init_assignment(top):
    """QSF parameter assignment naming the packager's .mif on the store instance."""
    return f'set_parameter -name {INIT_PARAMETER} "{MIF_NAME}" -to "{rom_path(top)}"'


def configuration_mode(family):
    """The configuration mode this family needs to carry memory contents, or None."""
    return CONFIGURATION_MODES.get(family)


def assignments(target):
    """QSF lines an image-carrying target adds: its configuration mode and the file."""
    mode = configuration_mode(target["family"])
    return ([f'set_global_assignment -name {CONFIGURATION_SETTING} "{mode}"'] if mode else
            []) + [init_assignment(target["top"])]


def explained_diagnostics(text, folder):
    """The two diagnostics a partial initialization file produces, stated exactly.

    The packager addresses the whole store and defines the image's own bytes, so
    Quartus names the remaining addresses and the zero it writes there. The
    expected counts come from the recorded image length, so a shorter or longer
    image changes the required text rather than passing quietly.
    """
    folder = Path(folder)
    record = json.loads((folder / "preload.json").read_text(encoding="utf-8"))
    image_bytes = record["image_bytes"]
    if not isinstance(image_bytes, int) or not 0 < image_bytes <= STORE_BYTES:
        raise ValueError("carried ROM image length is not inside the store")
    path = (folder / MIF_NAME).resolve().as_posix()
    required = [UNINITIALIZED.format(absent=STORE_BYTES - image_bytes, depth=STORE_BYTES, file=path),
                UNINITIALIZED_RANGE.format(first=image_bytes, last=STORE_BYTES - 1, file=path)]
    lines = [line.strip() for line in text.splitlines()]
    actual = [line for line in lines if re.match(r"Warning \((?:113027|113028)\):", line)]
    if actual != required:
        raise ValueError("carried ROM image initialization diagnostic text or count differs")
    return [{"code": re.match(r"Warning \((\d+)\)", line)[1], "text": line,
             "reason": "The carried image occupies the store's first bytes; Quartus initializes the rest to zero, "
                       "which is what an absent cartridge byte reads as."}
            for line in required]


def stage(root, build, folder, package, provenance, rebuild=False):
    """Build the declared package and write the packager's files into the attempt.

    The software build is the packager: its report carries the profile and the
    digest it recorded for the image on disk. `preload.prepare` then rechecks the
    exact length, that digest and the header and checksums before writing a file,
    so an image failing any of them refuses the build here.
    """
    from sw.rom_build import build_target

    root, folder = Path(root), Path(folder)
    report = build_target(root, build, SimpleNamespace(target=package, rebuild=rebuild), provenance)
    if report.get("status") != "PASS":
        raise ValueError(f"carried ROM image software build failed: {report.get('error', 'no error recorded')}")
    rom = root / report["rom"]
    if file_hash(rom) != report["artifacts"].get(report["rom"]):
        raise ValueError("carried ROM image differs from the digest its software build recorded")
    if report["profile"] != CARRIED_PROFILE:
        raise ValueError(f"carried ROM image must run in {CARRIED_PROFILE}")
    image = rom.read_bytes()
    record = write(folder, image, report["artifacts"][report["rom"]], profile=report["profile"])
    return {"package": package, "software_result": (rom.parent / "result.json").relative_to(root).as_posix(),
            "fingerprint": report["fingerprint"], **record}


def write(folder, image, expected_sha256, profile=CARRIED_PROFILE):
    """The packager's checked output for one image, and the record naming it."""
    folder = Path(folder)
    if profile != CARRIED_PROFILE:
        raise ValueError(f"carried ROM image must run in {CARRIED_PROFILE}")
    record = preload.prepare(image, expected_sha256, folder, profile=profile)
    (folder / IMAGE_NAME).write_bytes(image)
    return {"profile": record["profile"], "image_sha256": record["image_sha256"],
            "image_bytes": record["image_bytes"], "image_crc32": f"{record['image_crc32']:08x}",
            "title": record["title"], "version": record["version"],
            "init_file": MIF_NAME, "files": record["files"]}


PREPARED = (MIF_NAME, IMAGE_NAME, "preload-presence.mif", "preload-crc.hex", "preload.json")


def cache_paths(folder):
    """Attempt files a reused result must still carry, this attempt's own.

    The generated megafunctions are included because `verify_megafunction` reads
    them back on reuse; their names are fitter-chosen, so they are listed from
    the folder rather than stated. What that adds is one direction only: a
    megafunction present in the folder but absent from the immutable record is no
    longer trusted. It does not catch a lost or altered one, because the listing
    is folder-derived, so a missing file simply drops out of it, and
    `verify_megafunction` accepts one carrying shape beside any one uninitialized
    shape. `records.cache_matches`, which `complete_cache` calls first, is the
    check that catches that: it hashes every artifact the record names.
    """
    folder = Path(folder)
    return [folder / name for name in PREPARED] + sorted(folder.glob(MEGAFUNCTION))


def store_init_files(target):
    """{store owner: initialization file} for the fit evidence of this target."""
    if declared(target) is None:
        return {}
    return {ROM_INSTANCES[target["top"]][-1]: MIF_NAME}


def verify(folder, target):
    """The attempt still carries the declared image and the QSF names it once."""
    folder = Path(folder)
    record = preload.verify(folder)
    qsf = (folder / "design.qsf").read_text(encoding="utf-8")
    for line in assignments(target):
        if qsf.count(line) != 1:
            raise ValueError("carried ROM image configuration or initialization assignment missing or duplicated")
    netlist = (folder / "simulation/questa/design.vo").read_text()
    contents = verify_contents(netlist, (folder / IMAGE_NAME).read_bytes(), rom_path(target["top"]))
    power_up = verify_megafunction(folder)
    return {"package": declared(target), "instance": rom_path(target["top"]), "init_file": MIF_NAME,
            "fitted_contents": contents, "power_up_uninitialized": power_up,
            "configuration_mode": configuration_mode(target["family"]) or "none; configured from an external device",
            "profile": record["profile"], "image_sha256": record["image_sha256"],
            "image_bytes": record["image_bytes"], "image_crc32": f"{record['image_crc32']:08x}",
            "title": record["title"], "files": record["files"]}


def bit_planes(image, depth=STORE_BYTES, width=8, addresses=BLOCK_ADDRESSES):
    """The one-bit block contents an image held in this store requires.

    A byte store fitted as one-bit blocks holds, in each block, one bit of a
    window of consecutive addresses, highest address first. Which window a block
    holds is a fitter decision recorded in the address decode rather than in the
    block, so the acceptance compares the multiset of block contents with the
    multiset the image requires: a different, altered or wrongly sized image
    cannot match it, down to one bit, while a permutation of the whole windows is
    not distinguished from the image itself. Addresses past the image read zero,
    which is what Quartus writes there and what an absent cartridge byte reads as.
    """
    if depth % addresses or len(image) > depth:
        raise ValueError("carried ROM image does not fit the store's whole-block windows")
    padded = bytes(image) + bytes(depth - len(image))
    return sorted("".join("1" if byte >> bit & 1 else "0" for byte in reversed(padded[base:base + addresses]))
                  for base in range(0, depth, addresses) for bit in range(width))


def block_contents(words, addresses=BLOCK_ADDRESSES):
    """One fitted block's power-up bits, highest address first, from its mem_init words.

    Quartus splits a block into `mem_init0` upward, the lowest addresses first,
    each a sized hex literal. The words must be the complete contiguous set and
    must together state exactly the block's addresses.
    """
    if sorted(words) != sorted(f"mem_init{index}" for index in range(len(words))):
        raise ValueError("fitted block initialization words are not a complete set")
    bits = []
    for index in reversed(range(len(words))):
        match = re.fullmatch(r"(\d+)'h([0-9A-Fa-f]+)", words[f"mem_init{index}"])
        if match is None or int(match[1]) % 4 or len(match[2]) != int(match[1]) // 4:
            raise ValueError("unsupported fitted block initialization literal")
        bits.append(bin(int(match[2], 16))[2:].zfill(int(match[1])))
    joined = "".join(bits)
    if len(joined) != addresses:
        raise ValueError("fitted block initialization does not state the block's addresses")
    return joined


def megafunction_parameters(folder):
    """{generated .tdf name: its declared parameters} for every memory shape in the attempt."""
    found = {}
    for path in sorted(Path(folder).glob(MEGAFUNCTION)):
        head = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
        found[path.name] = {name: (match[1] if (match := re.search(MEGAFUNCTION_PARAMETER.format(name=name), head)) else None)
                            for name in ("INIT_FILE", "POWER_UP_UNINITIALIZED")}
    return found


def verify_megafunction(folder):
    """One store powers up holding the image and every other one powers up uninitialized.

    This reads the parameters the wrapper actually passed, so it states both
    halves of the rule the memory contract gives `power_up_uninitialized` in one
    attempt: `FALSE` beside the declared file, `TRUE` everywhere else.
    """
    found = megafunction_parameters(folder)
    carrying = sorted(name for name, values in found.items() if values["INIT_FILE"] == MIF_NAME)
    others = {name: values for name, values in found.items() if name not in carrying}
    if len(carrying) != 1:
        raise ValueError("the generated memory megafunctions do not name the carried image exactly once")
    if found[carrying[0]]["POWER_UP_UNINITIALIZED"] != "FALSE":
        raise ValueError("the store carrying an image still declares an uninitialized power-up")
    if not others or any(values["INIT_FILE"] is not None or values["POWER_UP_UNINITIALIZED"] != "TRUE"
                         for values in others.values()):
        raise ValueError("a store declaring no image lost its uninitialized power-up")
    return {"carrying": {carrying[0]: found[carrying[0]]}, "uninitialized": others}


def verify_contents(text, image, instance):
    """The fitted blocks of this store hold exactly the declared image."""
    atoms = {}
    pattern = (r"defparam\s+\\(" + re.escape(instance) +
               r"\|ram\|auto_generated\|ram_block\w+)\s+\.(mem_init\d+)\s*=\s*(\S+);")
    for name, word, value in re.findall(pattern, text):
        atoms.setdefault(name, {})[word] = value
    if not atoms:
        raise ValueError("no fitted block of the ROM store carries power-up contents")
    if sorted(block_contents(words) for words in atoms.values()) != bit_planes(image):
        raise ValueError("the fitted ROM store does not hold the declared image")
    return {"blocks": len(atoms), "addresses_per_block": BLOCK_ADDRESSES,
            "reconstruction": "each fitted one-bit block holds one bit plane of one window of consecutive "
                              "addresses; the multiset of block contents is the image's own"}
