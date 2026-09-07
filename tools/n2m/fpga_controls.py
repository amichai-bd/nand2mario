"""Checked external-control crossings for the combined board diagnostic."""
from . import fpga_vga

CHAINS = tuple((f"button{i}", f"buttons_n[{i}]", f"u_physical|u_buttons|button_meta[{i}]",
                f"u_physical|u_buttons|button_sync[{i}]") for i in range(4)) + (
    ("uart", "uart_rx", "u_uart|u_serial_rx|rx_meta", "u_uart|u_serial_rx|rx_sync"),)


def constraints(quote):
    lines = []
    for name, port, first, second in CHAINS:
        lines += fpga_vga.collection("ports", [port], "controls_" + name, quote)
        pins = " ".join(quote(first + "|" + pin) for pin in ("d", "asdata"))
        lines += [f"set controls_first_{name} [get_pins -nowarn [list {pins}]]",
                  f'if {{[get_collection_size $controls_first_{name}] != 1}} {{error "controls first-stage input mismatch: {name}"}}',
                  f"set_false_path -from $controls_{name} -to $controls_first_{name}"]
    return "\n".join(lines) + "\n"


def audit(quote):
    lines = []
    for corner, model, temperature in fpga_vga.CORNERS:
        lines += [f"set_operating_conditions -model {model} -voltage 1200 -temperature {temperature}", "update_timing_netlist"]
        for name, port, first, second in CHAINS:
            lines += fpga_vga.collection("registers", [first], "controls_launch_" + name, quote)
            lines += fpga_vga.collection("registers", [second], "controls_capture_" + name, quote)
            for check in ("setup", "hold"):
                lines += [f"report_timing -from $controls_launch_{name} -to $controls_capture_{name} -{check} -npaths 1 -detail full_path -file output/controls_{corner}_{name}_{check}.rpt"]
    return "\n".join(lines) + "\n"


def required_reports():
    return [f"controls_{corner}_{name}_{check}.rpt" for corner, _, _ in fpga_vga.CORNERS
            for name, _, _, _ in CHAINS for check in ("setup", "hold")]


def verify(folder):
    """Check every external-control synchronizer path and its sole first-stage sink."""
    from .fpga_lock import parse_netlist, OUTPUTS
    import re
    output = folder / 'output'
    result = {'paths': {}, 'first_stage_sinks': {}}
    for corner, _, _ in fpga_vga.CORNERS:
        for name, _, first, second in CHAINS:
            for check in ('setup', 'hold'):
                report = output / f'controls_{corner}_{name}_{check}.rpt'
                text = report.read_text()
                if not re.search(r'Report Timing: Found 1 ' + check + r' paths \(0 violated\)', text):
                    raise ValueError('missing or violated control synchronizer path')
                rows = [r for r in fpga_vga.rows(fpga_vga.summary(text)) if len(r) == 8 and r[0] != 'Slack']
                if (len(rows) != 1 or [fpga_vga.node(v) for v in rows[0][1:3]] != [first, second]
                        or rows[0][3:5] != ['clk_sys', 'clk_sys'] or fpga_vga.number(rows[0][0]) < 0):
                    raise ValueError('control synchronizer timing endpoints or clocks differ')
                result['paths'][report.name] = fpga_vga.number(rows[0][0])
    text = (folder / 'simulation/questa/design.vo').read_text()
    _, cells, params, declarations, rhs, lhs = parse_netlist(text, 'controls_proof')
    for name, _, first, second in CHAINS:
        if any(c not in cells or cells[c][0] != 'dffeas' for c in (first, second)):
            raise ValueError('missing control synchronizer register')
        first_ports, second_ports = cells[first][1], cells[second][1]
        q = first_ports.get('q')
        # Quartus may select either D or ASDATA, but no dynamic parallel load.
        selected = {'gnd': 'd', 'vcc': 'asdata'}.get(second_ports.get('sload'))
        if (not q or selected is None or second_ports.get(selected) != q
                or second_ports.get('ena') != 'vcc'
                or first_ports.get('clk') != second_ports.get('clk')):
            raise ValueError('control synchronizer selected input or enable differs')
        token = re.compile(r'(?<![A-Za-z0-9_$])' + re.escape(q) + r'(?![A-Za-z0-9_$])')
        sinks = [(cell, port) for cell, (kind, ports) in cells.items()
                 for port, value in ports.items() if port not in OUTPUTS[kind] and token.search(value)]
        if sinks != [(second, selected)] or any(token.search(value) for value in rhs + lhs):
            raise ValueError('control first stage has an unexpected sink or alias')
        result['first_stage_sinks'][name] = [second, selected]
    return result
