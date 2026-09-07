"""Scoped v0.5 composition crossing reports using the existing VGA profile."""
from . import fpga_vga


def hierarchy(text):
    return text.replace("u_bridge|", "u_system|u_bridge|")


def constraints(quote):
    text = fpga_vga.constraints(quote, lcd=True)
    # Readiness enters this proof as qualified reset ports. Only the first
    # synchronizer data pin is excepted; asynchronous reset pins remain timed.
    for name, port in (("pix_ready_sys", "reset_pix"),
                       ("sys_ready_pix", "reset_sys")):
        launch = dict(zip(fpga_vga.CHAINS, fpga_vga.LAUNCHES))[name]
        old = f'set launch_{name} [get_registers [list {quote(launch)}]]'
        new = f'set launch_{name} [get_ports [list {quote(port)}]]'
        if text.count(old) != 1:
            raise ValueError("v0.5 readiness constraint profile changed")
        text = text.replace(old, new)
    return hierarchy(text)


def audit(quote):
    return hierarchy(fpga_vga.audit(quote, lcd=True))
