"""Scoped v0.5 composition crossing reports using the existing VGA profile."""
from . import fpga_vga


def hierarchy(text):
    return text.replace("u_bridge|", "u_system|u_bridge|")


def constraints(quote):
    text = fpga_vga.constraints(quote, lcd=True)
    return hierarchy(text)


def audit(quote):
    return hierarchy(fpga_vga.audit(quote, lcd=True))


def verify_paths(folder, *, system_clock):
    reports = {}
    for name in fpga_vga.required_reports(lcd=True):
        path = folder / "output" / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("missing composed VGA path evidence: " + name)
        reports[name] = path.read_text(encoding="utf-8")
    return fpga_vga.verify_paths(reports,lcd=True,system_clock=system_clock,bridge_prefix="u_system|u_bridge|")
