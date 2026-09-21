"""Fitter report fragments host tests feed to the checkers that read them.

The `No Clock` table is read from inside its own table rather than by matching a
reason anywhere in the report
([fpga_lock.reported_no_clock_rows](../fpga_lock.py)), so a fixture has to carry
the table and not only its rows. This builds it in the shape `quartus_sta`
writes, padded columns and all, so one place states that shape for every unit
that needs it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from n2m import fpga_lock

HEADING = "Port or Register"


def no_clock_table(rows):
    """The `No Clock` table reporting exactly `rows`, each a node or (node, reason).

    A bare node means the register reason, which is the one every vendor lock
    synchronizer carries. No row means no table, which is what a fit with nothing
    to report writes.
    """
    rows = [(row, fpga_lock.REGISTER_REASON) if isinstance(row, str) else tuple(row) for row in rows]
    if not rows:
        return ""
    nodes = [HEADING, *(node for node, _ in rows)]
    reasons = ["Reason", *(reason for _, reason in rows)]
    width, reason_width = max(map(len, nodes)), max(map(len, reasons))
    rule = "+" + "-" * (width + 2) + "+" + "-" * (reason_width + 2) + "+\n"
    text = "+" + "-" * (width + reason_width + 5) + "+\n"
    text += "; " + "No Clock".ljust(width + reason_width + 3) + " ;\n" + rule
    for node, reason in zip(nodes, reasons):
        text += f"; {node.ljust(width)} ; {reason.ljust(reason_width)} ;\n"
        if node == HEADING:
            text += rule
    return text + rule
