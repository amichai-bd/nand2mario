DE10-Lite target configurations and constraints belong here. The
[builder contract](../../../wiki/tools/n2m/SPEC.md#fpga-build) owns commands and
evidence; generated project files/databases stay under the build tag.

`builder-smoke` fits the original eight-bit counter fixture in `src/dv/builder/`.
Only the clock has a package pin; counter outputs are virtual. The clock pin
and nominal 20 ns period follow the [timing contract](../../../wiki/src/clocks-resets-cdc.md).
This fixture proves the tool flow, not board operation or the #79/#80 designs.
`builder-invalid` deliberately uses a negative clock period and must fail.
Neither fixture is a hardware acceptance image.
