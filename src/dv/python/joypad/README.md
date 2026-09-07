# Independent Python joypad test plan

The [JOYP contract](../../../../wiki/src/rtl/joypad/MAS_joypad.md) defines expected
behavior. `test_joypad.py` independently drives and observes `n2m_joypad` public
ports; its model uses only applied inputs and previous expected state.
It does not import or translate SV drivers, stimulus, monitors or scoreboards.

| Obligation | Check |
| --- | --- |
| Matrix and active-low row mapping | Literal anchors plus all 256 button masks × four selections |
| Write bits | All 256 write bytes; only bits 5:4 affect the read matrix |
| Register commits and reads | Uncommitted writes and read commits hold state; off-address reads return zero |
| Host independence | INPUT replacement without gb_tick; host and select commits independently and together |
| Event transport | Release, repress, hold, selected held button, shared line, adjacent events and pulse clear |
| Reset | Both resets assert between edges; immediate profile observation and pending-event cancellation |
| Additional combinations | 128 locally seeded random commit/data combinations |
| Checker sensitivity | Separate DUT wrapper forces read line zero high; unchanged checker fails at cycle 3 |

Inputs are driven with the clock low. The checker samples applied public inputs
and settled outputs before the rising edge, then samples outputs in ReadOnly
after the edge. Expected state advances from the pre-edge observed inputs.
Unknown values fail explicitly. Every observation is flushed into a JSONL trace
before output comparison, with literal expected and actual values.

The test has a 100 us simulation timeout; the builder bounds Questa execution
to 60 seconds. The [usage guide](../README.md) defines commands and artifacts.
The builder requires one completed named Python test and complete wave/trace
evidence for PASS. A missing or failed XML result cannot inherit raw exit zero.

This tests the digital owner boundary only. It does not replace existing
acceptance, prove IF storage or CPU wake integration, model physical filtering,
or claim that any current product failure belongs to the RTL or the SV TB.
