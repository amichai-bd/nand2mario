"""Program a checked MAX 10 .sof onto the connected board; identity checked first."""
from pathlib import Path

from .doctor import executable, execute, parse_jtag
from .fpga import DEVICE


def program(root, folder, sof, *, quartus_bin, cable=None, timeout=60):
    """Verify the selected USB-Blaster reports the expected device, then program it.

    `sof` must be an existing file under `root`. Identity is re-checked with a
    fresh `jtagconfig` read immediately before `quartus_pgm` runs; a stale or
    ambiguous chain, or more than one matching chain, refuses to program.
    """
    sof = Path(sof)
    if (not sof.is_file() or sof.suffix != ".sof" or sof.is_symlink()
            or not sof.resolve().is_relative_to(root.resolve())):
        raise ValueError("missing or unsafe .sof path")
    chain = parse_jtag(execute([executable(quartus_bin, "jtagconfig")], folder, "chain.log"), cable)
    index = chain["selected"]["index"]
    output = execute([executable(quartus_bin, "quartus_pgm"), "-c", index, "-m", "jtag",
                      "-o", f"p;{sof.resolve()}"], folder, "program.log", timeout)
    if "Quartus Prime Programmer was successful. 0 errors, 0 warnings" not in output:
        raise RuntimeError("quartus_pgm did not report a successful configuration; see program.log")
    return {"device": DEVICE, "cable": index, "sof": sof.relative_to(root).as_posix(),
            "chain": chain, "output": output.strip(),
            "scope": "JTAG configuration only; does not itself prove UART or VGA behavior"}
