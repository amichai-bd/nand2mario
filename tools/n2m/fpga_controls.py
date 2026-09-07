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
    def sinks(net):
        token = re.compile(r'(?<![A-Za-z0-9_$\\|~])' + re.escape(net) + r'(?![A-Za-z0-9_$|~\[])')
        if any(token.search(value) for value in rhs + lhs):
            raise ValueError('control crossing has an unexpected alias')
        return {(cell, port) for cell, (kind, ports) in cells.items()
                for port, value in ports.items() if port not in OUTPUTS[kind] and token.search(value)}

    def selected(register):
        ports = cells[register][1]
        if (ports.get('ena') != 'vcc' or ports.get('aload') != 'gnd'
                or ports.get('sclr') != 'gnd' or ports.get('prn') != 'vcc'
                or ports.get('devclrn') != 'devclrn' or ports.get('devpor') != 'devpor'
                or ports.get('clk') != r'\clk_sys~inputclkctrl_outclk'
                or ports.get('clrn') != r'\u_clocking|u_reset|sys_release[1]~clkctrl_outclk'
                or params.get(register) != {'is_wysiwyg': '"true"', 'power_up': '"low"'}):
            raise ValueError('control synchronizer clock/reset/load/enable differs')
        port = {'gnd': 'd', 'vcc': 'asdata'}.get(ports.get('sload'))
        if port is None:
            raise ValueError('control synchronizer has dynamic selected input')
        return port

    def path(source, register, inverted):
        """Accept one direct edge or one fully checked unary LUT, without fanout."""
        port = selected(register)
        target = cells[register][1][port]
        if target == source:
            if inverted or sinks(source) != {(register, port)}:
                raise ValueError('control direct path polarity or fanout differs')
            return []
        drivers = [(n, p) for n, (kind, p) in cells.items()
                   if kind == 'fiftyfivenm_lcell_comb' and p.get('combout') == target]
        if len(drivers) != 1:
            raise ValueError('control path does not have one unary LUT')
        cell, ports = drivers[0]
        mode = params.get(cell, {})
        if (set(mode) != {'lut_mask', 'sum_lutc_input'}
                or mode['sum_lutc_input'] != '"datac"'
                or not re.fullmatch(r"16'h[0-9a-fA-F]{4}", mode['lut_mask'])
                or ports.get('cin') != 'gnd' or ports.get('cout') != ''):
            raise ValueError('control unary LUT mode differs')
        inputs = [ports.get(p) for p in ('dataa', 'datab', 'datac', 'datad')]
        if source not in inputs or not set(inputs) <= {source, 'gnd', 'vcc'}:
            raise ValueError('control LUT has unrelated inputs')
        mask = int(mode['lut_mask'][4:], 16)
        for bit in (0, 1):
            values = {source: bit, 'gnd': 0, 'vcc': 1}
            index = sum(values[value] << i for i, value in enumerate(inputs))
            if ((mask >> index) & 1) != (bit ^ inverted):
                raise ValueError('control unary LUT polarity differs')
        expected = {(cell, p) for p, value in ports.items() if value == source}
        if sinks(source) != expected or sinks(target) != {(register, port)}:
            raise ValueError('control unary path has bypass fanout')
        return [cell]

    for name, external, first, second in CHAINS:
        if any(c not in cells or cells[c][0] != 'dffeas' for c in (first, second)):
            raise ValueError('missing control synchronizer register')
        buffer = external + '~input'
        if cells.get(buffer, (None,))[0] != 'fiftyfivenm_io_ibuf':
            raise ValueError('control external input buffer missing')
        ports = cells[buffer][1]
        if (ports != {'i': external, 'ibar': 'gnd', 'nsleep': 'vcc', 'o': '\\' + external + '~input_o'}
                or sinks(external) != {(buffer, 'i')}):
            raise ValueError('control external port has bypass or unexpected buffer')
        first_path = path(ports['o'], first, True)
        second_path = path(cells[first][1]['q'], second, False)
        result['first_stage_sinks'][name] = {'external_path': first_path,
                                            'second_path': second_path, 'capture': second}
    return result
