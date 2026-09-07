"""Checked external-control crossings for the combined board diagnostic."""
from . import fpga_vga

CHAINS = tuple((f"button{i}", f"buttons_n[{i}]", f"u_physical|u_buttons|button_meta[{i}]",
                f"u_physical|u_buttons|button_sync[{i}]") for i in range(4)) + (
    ("uart", "uart_rx", "u_uart|u_serial_rx|rx_meta", "u_uart|u_serial_rx|rx_sync"),)


def verify_identity(folder, build_id, *, macro="N2M_CONTROLS_BUILD_ID"):
    import re
    if not isinstance(build_id, str) or not re.fullmatch('[0-9a-f]{32}', build_id) or int(build_id, 16) == 0:
        raise ValueError('controls proof requires its nonzero producing build identity')
    qsf = (folder / 'design.qsf').read_text()
    lines = [line for line in qsf.splitlines() if macro in line]
    if lines != [f'set_global_assignment -name VERILOG_MACRO "{macro}=128\'h{build_id}"']:
        raise ValueError('controls generated macro differs from producing identity')
    report = (folder / 'output/design.map.rpt').read_text()
    values = re.findall(r';\s*BUILD_ID\s*;\s*([01]+)\s*;\s*Unsigned Binary\s*;', report)
    if values != [f'{int(build_id, 16):0128b}']:
        raise ValueError('controls compiled 128-bit identity differs')
    return build_id


def verify_uart_memory(text, fit, *, system_net=r"\clk_sys~inputclkctrl_outclk"):
    """Account for the six existing UART stores alongside the three VGA banks."""
    from .fpga_lock import parse_netlist
    _, cells, params, *_ = parse_netlist(text, 'controls_proof')
    shapes = {'u_uart|u_packet_rx|stores|encoded': (270, 8, 1),
              'u_uart|u_packet_rx|stores|decoded': (268, 8, 1),
              'u_uart|u_commands|u_load|u_presence|u_presence': (32768, 1, 4)}
    shapes.update({f'u_uart|u_exchange|stores|banks[{i}].memory': (268, 8, 1) for i in range(3)})
    suffix = '|ram|auto_generated|'
    expected = {owner + suffix + f'ram_block1a{i}': (depth, width)
                for owner, (depth, width, count) in shapes.items() for i in range(count)}
    actual = {n for n, (kind, _) in cells.items() if kind == 'fiftyfivenm_ram_block' and not n.startswith('u_bridge|')}
    if actual != set(expected):
        raise ValueError('combined UART RAM atom inventory differs')
    for name, (depth, width) in expected.items():
        p, ports = params[name], cells[name][1]
        required = {'operation_mode': '"bidir_dual_port"', 'ram_block_type': '"M9K"',
                    'power_up_uninitialized': '"true"', 'mixed_port_feed_through_mode': '"old"',
                    'port_b_address_clock': '"clock0"', 'port_b_read_enable_clock': '"clock0"'}
        for side in ('a', 'b'):
            required.update({f'port_{side}_logical_ram_depth': str(depth), f'port_{side}_logical_ram_width': str(width),
                             f'port_{side}_data_out_clock': '"none"', f'port_{side}_address_clear': '"none"',
                             f'port_{side}_data_out_clear': '"none"', f'port_{side}_first_bit_number': '0',
                             f'port_{side}_data_width': '1' if width == 1 else '18',
                             f'port_{side}_address_width': '13' if width == 1 else '9',
                             f'port_{side}_read_during_write_mode': '"new_data_with_nbe_read"'})
        if any(p.get(k) != v for k, v in required.items()) or any(k.startswith(('mem_init', 'init_file')) for k in p):
            raise ValueError('combined UART RAM dimensions/latency/initialization differ')
        required_ports = {'clk0': system_net, 'clk1': 'gnd', 'clr0': 'gnd', 'clr1': 'gnd',
                          'portare': 'gnd', 'portbwe': 'gnd', 'portaaddrstall': 'gnd', 'portbaddrstall': 'gnd',
                          'portabyteenamasks': "1'b1", 'portbbyteenamasks': "1'b1"}
        if any(ports.get(k) != v for k, v in required_ports.items()):
            raise ValueError('combined UART RAM clock/reset/port role differs')
    rows = [r for r in fpga_vga.rows(fit) if len(r) > 4 and r[1:4] == ['M9K', 'True Dual Port', 'Single Clock']]
    if len(rows) != len(shapes):
        raise ValueError('combined UART fitted store count differs')
    seen = set()
    for row in rows:
        owner = fpga_vga.node(row[0]).removesuffix(suffix + 'ALTSYNCRAM')
        if owner not in shapes or owner in seen:
            raise ValueError('combined UART fitted owner differs')
        seen.add(owner)
        depth, width, count = shapes[owner]
        d, w, bits = str(depth), str(width), str(depth * width)
        if (len(row) != 27 or row[4:19] != [d, w, d, w, 'yes', 'no', 'yes', 'no', bits, d, w, d, w, bits, str(count)]
                or row[19] != 'None' or row[21:] != ['Old data', 'New data with NBE Read', 'New data with NBE Read', 'Off', 'No', 'No - Unknown']):
            raise ValueError('combined UART fitted shape/ports differ')
    return {'stores': len(shapes), 'atoms': len(expected), 'bits': sum(d*w for d,w,_ in shapes.values())}


def constraints(quote, *, chains=CHAINS):
    lines = []
    for name, port, first, second in chains:
        lines += fpga_vga.collection("ports", [port], "controls_" + name, quote)
        pins = " ".join(quote(first + "|" + pin) for pin in ("d", "asdata"))
        lines += [f"set controls_first_{name} [get_pins -nowarn [list {pins}]]",
                  f'if {{[get_collection_size $controls_first_{name}] != 1}} {{error "controls first-stage input mismatch: {name}"}}',
                  f"set_false_path -from $controls_{name} -to $controls_first_{name}"]
    return "\n".join(lines) + "\n"


def audit(quote, *, chains=CHAINS):
    lines = []
    for corner, model, temperature in fpga_vga.CORNERS:
        lines += [f"set_operating_conditions -model {model} -voltage 1200 -temperature {temperature}", "update_timing_netlist"]
        for name, port, first, second in chains:
            lines += fpga_vga.collection("registers", [first], "controls_launch_" + name, quote)
            lines += fpga_vga.collection("registers", [second], "controls_capture_" + name, quote)
            for check in ("setup", "hold"):
                lines += [f"report_timing -from $controls_launch_{name} -to $controls_capture_{name} -{check} -npaths 1 -detail full_path -file output/controls_{corner}_{name}_{check}.rpt"]
    return "\n".join(lines) + "\n"


def required_reports(*, chains=CHAINS):
    return [f"controls_{corner}_{name}_{check}.rpt" for corner, _, _ in fpga_vga.CORNERS
            for name, _, _, _ in chains for check in ("setup", "hold")]


def verify(folder, *, system_clock="clk_sys", system_net=r"\clk_sys~inputclkctrl_outclk", chains=CHAINS, top="controls_proof"):
    """Check every external-control synchronizer path and its sole first-stage sink."""
    from .fpga_lock import parse_netlist, OUTPUTS
    import re
    output = folder / 'output'
    result = {'paths': {}, 'first_stage_sinks': {}}
    for corner, _, _ in fpga_vga.CORNERS:
        for name, _, first, second in chains:
            for check in ('setup', 'hold'):
                report = output / f'controls_{corner}_{name}_{check}.rpt'
                text = report.read_text()
                if not re.search(r'Report Timing: Found 1 ' + check + r' paths \(0 violated\)', text):
                    raise ValueError('missing or violated control synchronizer path')
                rows = [r for r in fpga_vga.rows(fpga_vga.summary(text)) if len(r) == 8 and r[0] != 'Slack']
                if (len(rows) != 1 or [fpga_vga.node(v) for v in rows[0][1:3]] != [first, second]
                        or rows[0][3:5] != [system_clock, system_clock] or fpga_vga.number(rows[0][0]) < 0):
                    raise ValueError('control synchronizer timing endpoints or clocks differ')
                result['paths'][report.name] = fpga_vga.number(rows[0][0])
    text = (folder / 'simulation/questa/design.vo').read_text()
    _, cells, params, declarations, rhs, lhs = parse_netlist(text, top)
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
                or ports.get('clk') != system_net
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

    for name, external, first, second in chains:
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
