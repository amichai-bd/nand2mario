# frog-bui verification observations

Inspected committed sources at `da16dc841d50c6c48827225b91dac6b8716b4311`.
These are method observations, not evidence that the reference passes simulation
or a nand2mario behavior contract. No source is imported; the
[provenance policy](../../../../wiki/tools/provenance.md) remains in force.

| Source | Observation and useful application |
|---|---|
| [UART monitor][monitor] | Reconstructs commands from raw received bytes with DV-owned CRC and decode calculations. Observe public inputs and derive expected transactions independently of DUT decoded fields. |
| [UART checker][checker] | Compares validity alignment, unknowns and all public typed fields; reports detailed actual/expected values and counts. A data-only comparison can miss a lost or duplicated transaction. |
| [Host smoke][host] | Exercises parser, bridge and full serial paths with delayed responses. Layer local error/recovery checks and composed backpressure/ordering checks. Its watchdog prints failure then calls `$finish`; do not copy that completion policy. Require nonzero raw failure and an exact diagnostic. |
| [Display smoke][display] | Checks byte readback, contention, foreground/background selection, known outputs, sync widths and boundaries, with a fatal watchdog. Some checks use hierarchy; internal state is diagnostic context, not independent golden truth. |
| [Assertion helpers][macros] | The hold check uses prior sampled control because a hold affects the next observed update. Derive sampling from the consuming contract, guard reset and valid history, and prove a deliberate failure. No reference assertion helper is adopted. |

The [skill](../SKILL.md) owns the working method; the
[baseline contract](../../../../wiki/src/dv/baseline/SPEC.md) owns the project's
executable separation, failure proof and evidence rules. Use Questa for new
simulation evidence. Reference packet formats, timings and CPU assumptions do
not define Game Boy behavior or nand2mario interfaces.

[monitor]: https://github.com/amichai-bd/frog-bui/blob/da16dc841d50c6c48827225b91dac6b8716b4311/src/dv/uart_ctrl/tb/uart_ctrl_monitor.sv
[checker]: https://github.com/amichai-bd/frog-bui/blob/da16dc841d50c6c48827225b91dac6b8716b4311/src/dv/uart_ctrl/tb/uart_ctrl_checker.sv
[host]: https://github.com/amichai-bd/frog-bui/blob/da16dc841d50c6c48827225b91dac6b8716b4311/src/dv/uart_ctrl/tb/tb_uart_host_smoke.sv
[display]: https://github.com/amichai-bd/frog-bui/blob/da16dc841d50c6c48827225b91dac6b8716b4311/src/dv/rv_cpu/smoke/tb_vga_smoke.sv
[macros]: https://github.com/amichai-bd/frog-bui/blob/da16dc841d50c6c48827225b91dac6b8716b4311/src/rtl/common/macros.svh
