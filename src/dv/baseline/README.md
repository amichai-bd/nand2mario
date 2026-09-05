# Baseline test plan

- **Contract:** [Verification baseline](../../../wiki/src/dv/baseline/SPEC.md).
- **DUT boundary:** original test-only byte accumulator in fixture.sv; synchronous reset, enabled addition modulo 256, disabled hold. No Game Boy behavior.
- **Stimulus:** eleven directed cycles then 64 xorshift32 cycles; drive on falling edges. Retain the requested seed, including zero.
- **Reference model:** integer transaction history and modulo arithmetic, independent of DUT registers. Literal checkpoints establish 128 on cycle 4 and zero on cycle 6.
- **Checks and assertions:** sampled transactions feed the scoreboard; independent local checks reject unknown values, bad reset and disabled-state changes. End check requires exactly 75 checked transactions and all eight coverage bits.
- **Normal cases:** additions, consecutive commands, enabled zero and disabled inputs.
- **Edge and error cases:** initial/reset-during-activity, reset wins over enable, operand 255, wrap at 256, seeded stimulus, watchdog. Broken fixture drops the operand MSB and must fail at cycle 6 with expected 0 and actual 128.
- **Coverage:** reset, reset+enable, enabled addition, operand zero, operand maximum, observed wrap, hold and reset-after-activity. These are fixture bins, not CPU coverage.
- **Failure artifacts:** seed and exact expected/actual/cycle in sim.log and transactions.csv; baseline.vcd, Questa WLF, input/tool fingerprints and raw exit in builder records. Good runs also emit coverage/bins.txt.

The [regression manifest](regression.json) selects fixed levels. Run through
`python tools/n2m/baseline.py --sim questa --level smoke --tag baseline-smoke`.
The broken target's simulator exit remains nonzero; the wrapper accepts only
that named defect and retains it. Extra/missing trace rows, mismatched seeds,
wrong failure values, missing waves and unexpected mismatches fail. Questa is the sole backend.
