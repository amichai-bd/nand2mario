---
name: rtl-coder
description: Implement or review synthesizable nand2mario SystemVerilog from an approved contract. Use for RTL behavior; do not use for testbench-only, FPGA constraint, or host software work.
---

# RTL coder

Read the issue, linked specification, and nearby RTL before editing.

1. State ports, clocks, resets, state, timing, and invalid cases.
2. Keep modules small, synchronous intent explicit, and widths signedness clear.
3. Avoid latches, implicit nets, unsafe crossings, and vendor logic outside FPGA
   wrappers.
4. Align wiki, assertions, and directed tests with behavior changes using the
   [review guide](../agent-flow/references/review.md).
5. Run the smallest compile and simulation that prove the contract.

Use [the checklist](templates/rtl-checklist.md) in review notes. Read
[the scenarios](examples/scenarios.md) for the skill boundary. Stop when the
contract, clocking, reset, or crossing behavior is undecided.
