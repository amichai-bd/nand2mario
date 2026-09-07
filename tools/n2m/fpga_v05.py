"""Scoped v0.5 composition crossing reports using the existing VGA profile."""
from . import fpga_vga, fpga_controls, fpga_memory_stores

UART_CHAINS = (("uart", "uart_rx", "u_system|u_uart|u_serial_rx|rx_meta",
                "u_system|u_uart|u_serial_rx|rx_sync"),)
BOARD_INPUTS = {"clk_reference": "PIN_P11", "board_reset_n": "PIN_B8",
                "uart_rx": "PIN_AB5", "uart_tx": "PIN_AB6"}
BOARD_PINS = dict(BOARD_INPUTS, **dict(zip(fpga_vga.PORTS, (
    "PIN_AA1", "PIN_V1", "PIN_Y2", "PIN_Y1",
    "PIN_W1", "PIN_T2", "PIN_R2", "PIN_R1",
    "PIN_P1", "PIN_T1", "PIN_P4", "PIN_N2", "PIN_N3", "PIN_N1"))))


def board_target(target):
    return target.get("top") == "v05_proof" and "uart_rx" in target.get("pins", {})


def validate_board(target):
    if (target.get("top") != "v05_proof"
            or target.get("pins") != BOARD_PINS
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


def verify_memory(folder, *, system_net):
    """Partition the complete composition across existing memory checkers."""
    import re
    import os
    text = (folder / 'simulation/questa/design.vo').read_text(encoding='utf-8')
    fit = (folder / 'output/design.fit.rpt').read_text(encoding='cp1252' if os.name == 'nt' else 'utf-8')
    stores = {'u_system|u_stores|' + owner: shape for owner, shape in fpga_memory_stores.STORES.items()}
    stores.update({f'u_system|u_snapshot|banks[{bank}].u_{side}': (5760, 8)
                   for bank in range(2) for side in ('source', 'host')})
    backing = fpga_memory_stores.verify_netlist(text, stores=stores, system_clock=system_net, scoped=True)
    fpga_memory_stores.verify_rows(fit, stores=stores, scoped=True)
    vga = fpga_vga.verify_memory_netlist(text, lcd=True, system_net=system_net,
        bridge_prefix='u_system|u_bridge|', shade='u_system|u_ppu|source_shade')
    fpga_vga.verify_memory_rows(fit, bridge_prefix='u_system|u_bridge|')
    uart = fpga_controls.verify_uart_memory(text, fit, system_net=system_net,
        prefix='u_system|', top='v05_proof')
    names = re.findall(r'fiftyfivenm_ram_block\s+\\(\S+)\s*\(', text)
    uart_names = {name for name in names if name.startswith('u_system|u_uart|')}
    if (len(names) != 111 or len(set(names)) != 111
            or set(names) != set(backing) | set(vga) | uart_names):
        raise ValueError('composed memory atom partition differs')
    logical = [row for row in fpga_vga.rows(fit) if len(row) >= 24 and row[1] == 'M9K']
    if len(logical) != 20:
        raise ValueError('composed logical memory inventory differs')
    for label, expected in (('M9Ks', '111 /'), ('Total block memory bits', '761,704 /')):
        values = [row[1] for row in fpga_vga.rows(fit) if len(row) == 2 and row[0] == label]
        if len(values) != 1 or not values[0].startswith(expected):
            raise ValueError('composed memory capacity differs')
    return {'logical_stores': 20, 'atoms': 111, 'bits': 761704,
            'backing_atoms': len(backing), 'vga_atoms': len(vga), 'uart': uart}
