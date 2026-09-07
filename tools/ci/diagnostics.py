"""Exact expected clocking-invalid diagnostic chain; no generic error waiver."""
from collections import Counter
import re
from pathlib import Path
from tools.n2m import fpga, fpga_pll
from .model import require


def invalid_compile(text, attempt, quartus_directory, *, pll=None):
    sdc = (attempt / 'checked.sdc').as_posix()
    project = (attempt / 'design').as_posix()
    script = (Path(quartus_directory).parent / 'common/tcl/internal/qsh_flow.tcl').as_posix()
    coded = {
        '330000': ('warning', r'Timing-Driven Synthesis is skipped because it could not initialize the timing netlist'),
        '332174': ('warning', re.escape('Ignored filter at checked.sdc(1): u_clocking|u_reset|missing_register[0]|clrn could not be matched with a pin File: ' + sdc + ' Line: 1')),
        '332000': ('error', r'checked endpoint count mismatch: reset_0'),
        '332008': ('critical warning', r'Read_sdc failed due to errors in the SDC file'),
        '171000': ('error', r"Can't fit design in device"),
        '293001': ('error', r'Quartus Prime Full Compilation was unsuccessful\. 4 errors, 5 warnings'),
        '23031': ('error', re.escape('Evaluation of Tcl script ' + script + ' unsuccessful')),
        '292013': ('warning', fpga.CLASSIFIED['292013']),
        '169177': ('warning', fpga.CLASSIFIED['169177'].replace(r'\d+', '1', 1)),
    }
    summaries = {
        'fitter': r'Quartus Prime Fitter was unsuccessful\. 2 errors, 4 warnings',
        'shell': r'Quartus Prime Shell was unsuccessful\. 11 errors, 5 warnings',
        'project': re.escape('Flow compile (for project ' + project + ') was not successful'),
        'flow': re.escape('ERROR: Error(s) found while running an executable. See report file(s) for error message(s). Message log indicates which executable was run last.'),
        'memory': r'Peak virtual memory: [0-9]+ megabytes',
        'ended': r'Processing ended: (?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) [A-Za-z]{3} +[0-9]{1,2} [0-9]{2}:[0-9]{2}:[0-9]{2} [0-9]{4}',
        'elapsed': r'Elapsed time: [0-9]+:[0-9]{2}:[0-9]{2}',
        'cpu': r'Total CPU time \(on all processors\): [0-9]+:[0-9]{2}:[0-9]{2}',
    }
    if pll is not None and pll.get('system_divide') == 2:
        explained = fpga_pll.explained_diagnostics(text, attempt, pll)
        require(len(explained) == 1, 'missing exact parallel PLL diagnostic')
        coded['176127'] = ('warning', re.escape(explained[0]['text'].split(': ', 1)[1]))
        coded['293001'] = ('error', r'Quartus Prime Full Compilation was unsuccessful\. 4 errors, 6 warnings')
        summaries['fitter'] = r'Quartus Prime Fitter was unsuccessful\. 2 errors, 5 warnings'
        summaries['shell'] = r'Quartus Prime Shell was unsuccessful\. 11 errors, 6 warnings'
    counts = Counter()
    for raw in text.splitlines():
        line = raw.strip().replace('\\', '/')
        if not re.match(r'(?:Critical Warning|Warning|Error)(?:\s|:|\()', line, re.I):
            continue
        match = re.fullmatch(r'(Critical Warning|Warning|Error)(?: \(([0-9]+)\))?:\s*(.*)', line, re.I)
        require(match is not None, 'malformed invalid-target diagnostic')
        level, code, message = match.groups()
        if code:
            require(code in coded and level.lower() == coded[code][0] and
                    re.fullmatch(coded[code][1], message, re.I), 'unexplained invalid-target diagnostic: ' + raw)
            counts[code] += 1
        else:
            names = [name for name, pattern in summaries.items() if re.fullmatch(pattern, message, re.I)]
            require(level.lower() == 'error' and len(names) == 1, 'unexplained invalid-target summary: ' + raw)
            counts[names[0]] += 1
    expected = Counter({name: 1 for name in (*coded, *summaries)})
    expected.update({'memory': 1, 'ended': 1, 'elapsed': 1, 'cpu': 1})
    require(counts == expected, 'incomplete or duplicated invalid-target diagnostic chain')
    return dict(counts)
