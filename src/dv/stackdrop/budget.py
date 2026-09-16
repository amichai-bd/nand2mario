"""Simulated-time budget for the Stackdrop cocotb targets.

Simulated time is deterministic, so a cocotb timeout derives from the
scenario's own dot bound plus a stated margin instead of a literal. The
README records the derived values beside the wall budget.
"""
import math

DOT_HZ = 4194304  # n2m_timebase: 65536/390625 of the 25 MHz system clock per dot.
HOST_MS = 10  # identify, preload adoption, RUN and HALT over the simulated UART: 5.69 ms measured in every target.
MARGIN = 0.25  # headroom over the scenario's dots for growth its bound does not yet name.
UNIT_BOUND = 500000  # dots; the unit's STACKDROP_PROGRESS limit from the README bound.


def timeout_ms(dots):
    """Whole milliseconds a scenario bounded at `dots` may simulate before cocotb stops it."""
    return math.ceil(dots*(1+MARGIN)*1000/DOT_HZ)+HOST_MS
