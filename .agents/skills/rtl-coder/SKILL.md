---
name: rtl-coder
description: Implement or review synthesizable nand2mario SystemVerilog from an approved contract. Use for RTL behavior; do not use for testbench-only, FPGA constraint, or host software work.
---

# RTL coder

Read the issue, linked specification, and nearby RTL before editing. Locate the
owner's MAS through the [ownership map](../../../wiki/ownership.md); keep its
requirements/design aligned with `src/rtl/`, verification, and evidence.

1. State ports, clocks, resets, state, timing, and invalid cases.
2. Keep modules small, synchronous intent explicit, and widths and signedness clear.
   Use the [product register convention](../../../wiki/src/rtl-reference-style.md#product-register-convention)
   for ordinary registers: `DFF`, `DFF_RST`, `DFF_RST_VAL`, `DFF_EN`, and
   `DFF_RST_EN(Q, D, CLK, EN, RST, RESET_VAL)`. Keep reset polarity, priority,
   enable holding and stage timing explicit. Use `DFF_ARST_VAL` or
   `DFF_ARST_N_VAL` for asynchronous resets, retaining declarations, names,
   power-up values and synchronizer attributes. Follow the
   [separate declaration and assignment rule](../../../wiki/src/rtl-reference-style.md#separate-declarations-and-assignments);
   use `logic` signal declarations instead of `wire`/`reg`, and never retain
   a declaration assignment. Use the initialized
   asynchronous forms only where the contract requires constant power-up state. Async reset or attributes alone do
   not justify a raw sequential block. An unavoidable inference exception needs
   a concrete reason beside the block and in its owner contract, plus review.
3. Avoid latches, implicit nets, unsafe crossings, and vendor logic outside FPGA
   wrappers.
4. Use the [named assertion convention](../../../wiki/src/rtl-reference-style.md#named-assertion-convention)
   for meaningful local invariants. Review argument order, reset polarity, prior
   sampled controls and asynchronous history invalidation. Prove a named fatal
   failure in Questa and synthesis exclusion; keep the independent oracle.
   Align wiki, assertions, and directed tests with behavior changes using the
   [review guide](../agent-flow/references/review.md).
5. Run the smallest compile and checked Questa simulation that prove the contract.
   Use Questa only for new simulation evidence; do not start Icarus runs.

Run `python .agents/skills/rtl-coder/scripts/check_sv_style.py` before review.
The lexical guard checks tracked SV/SVH built-in and locally typedef-named
declarations; review imported types and emitted source too.

Use [the checklist](templates/rtl-checklist.md) in review notes. Read
[the scenarios](examples/scenarios.md) for the skill boundary. Stop when the
contract, clocking, reset, or crossing behavior is undecided.

The [CI boundary](../../../wiki/tools/n2m/SPEC.md#ci-execution-boundary) distinguishes
hosted host checks from required actual local Questa evidence until #32.
