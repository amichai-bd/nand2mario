# frog-bui verification observations

Inspected the owner-supplied local frog-bui checkout at committed revision
`da16dc841d50c6c48827225b91dac6b8716b4311`; the inspected files were unmodified.
This commit is unpublished and has no working upstream GitHub permalink.
These are method observations, not evidence that the reference passes simulation
or a nand2mario behavior contract. No source is imported; the
[provenance policy](../../../../wiki/tools/provenance.md) remains in force.

| Source | Observation and useful application |
|---|---|
| UART monitor | Reconstructs commands from raw received bytes with DV-owned CRC and decode calculations. Observe public inputs and derive expected transactions independently of DUT decoded fields. |
| UART checker | Compares validity alignment, unknowns and all public typed fields; reports detailed actual/expected values and counts. A data-only comparison can miss a lost or duplicated transaction. |
| Host smoke | Exercises parser, bridge and full serial paths with delayed responses. Layer local error/recovery checks and composed backpressure/ordering checks. Its watchdog prints failure then calls `$finish`; do not copy that completion policy. Require nonzero raw failure and an exact diagnostic. |
| Display smoke | Checks byte readback, contention, foreground/background selection, known outputs, sync widths and boundaries, with a fatal watchdog. Some checks use hierarchy; internal state is diagnostic context, not independent golden truth. |
| Assertion helpers | The hold check uses prior sampled control because a hold affects the next observed update. Derive sampling from the consuming contract, guard reset and valid history, and prove a deliberate failure. The project uses the reference argument order with original N2M helpers, fatal exits and explicit asynchronous history validity; no source is imported. |

The [skill](../SKILL.md) owns the working method; the
[baseline contract](../../../../wiki/src/dv/baseline/SPEC.md) owns the project's
executable separation, failure proof and evidence rules. Use Questa for new
simulation evidence. Reference packet formats, timings and CPU assumptions do
not define Game Boy behavior or nand2mario interfaces.

## Reproduce source inspection

From the supplied reference checkout, use
`git show da16dc841d50c6c48827225b91dac6b8716b4311:<path>` for each path below.
`git diff da16dc841d50c6c48827225b91dac6b8716b4311 -- <path>` must be empty
when comparing the inspected working file. These locators describe local
research; they do not imply that the source is published or licensed for reuse.

- UART monitor: `src/dv/uart_ctrl/tb/uart_ctrl_monitor.sv`
- UART checker: `src/dv/uart_ctrl/tb/uart_ctrl_checker.sv`
- Host smoke: `src/dv/uart_ctrl/tb/tb_uart_host_smoke.sv`
- Display smoke: `src/dv/rv_cpu/smoke/tb_vga_smoke.sv`
- Assertion helpers: `src/rtl/common/macros.svh`
