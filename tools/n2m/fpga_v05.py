"""Scoped v0.5 composition crossing reports using the existing VGA profile."""
from . import fpga_vga, fpga_controls

UART_CHAINS = (("uart", "uart_rx", "u_system|u_uart|u_serial_rx|rx_meta",
                "u_system|u_uart|u_serial_rx|rx_sync"),)
BOARD_INPUTS = {"clk_reference": "PIN_P11", "board_reset_n": "PIN_B8",
                "uart_rx": "PIN_AB5", "uart_tx": "PIN_AB6"}


def board_target(target):
    return target.get("top") == "v05_proof" and "uart_rx" in target.get("pins", {})


def validate_board(target):
    if (target.get("top") != "v05_proof"
            or any(target.get("pins", {}).get(port) != pin for port, pin in BOARD_INPUTS.items())
            or set(target.get("pins", {})) != set(BOARD_INPUTS) | set(fpga_vga.PORTS)
            or set(target.get("virtual_pins", [])) != {"paused", "fault", "display_sequence[*]", "display_epoch[*]"}):
        raise ValueError("v05-board requires physical UART/reset and diagnostic-only virtual outputs")


def hierarchy(text):
    return text.replace("u_bridge|", "u_system|u_bridge|")


def constraints(quote, *, board=False):
    text = fpga_vga.constraints(quote, lcd=True)
    return hierarchy(text) + (fpga_controls.constraints(quote, chains=UART_CHAINS) if board else "")


def audit(quote, *, board=False):
    return hierarchy(fpga_vga.audit(quote, lcd=True)) + (fpga_controls.audit(quote, chains=UART_CHAINS) if board else "")


def verify_paths(folder, *, system_clock):
    reports = {}
    for name in fpga_vga.required_reports(lcd=True):
        path = folder / "output" / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("missing composed VGA path evidence: " + name)
        reports[name] = path.read_text(encoding="utf-8")
    return fpga_vga.verify_paths(reports,lcd=True,system_clock=system_clock,bridge_prefix="u_system|u_bridge|")
