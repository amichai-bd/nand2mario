# Scenarios

Good: Verify the USB-Blaster, `10M50DA` target, wiring, voltage, approval, and
lock before loading a test-card bitstream.

Bad: Ignore unconstrained paths or program the connected board because a build
succeeded.

Not a trigger: Portable RTL simulation with no Quartus or board concern.

## Verified procedures

Before selecting a programming image, inspect the target definition and generated
QSF for physical and virtual ports. The v0.5 proof target has virtual UART/control
ports and the [FPGA README](../../../../src/fpga/de10_lite/README.md)
explicitly excludes board programming. Its fitted SOF alone
does not establish a usable UART-connected board image.

Verified CLI help: `python tools/build.py fpga build --help` describes building,
not programming; no FPGA programming subcommand exists. `host load --help`
requires an immutable `sw/build/<target>/runs/<attempt>/result.json` through
`--package`. `host status --help` exposes explicit UART port/VID/PID/identity
selection. These help checks do not prove programming or UART transmission.

Record subsequent tested tool/CLI/debug commands, tool versions and observed
pitfalls here or in a linked focused reference. Label untested steps as assumptions;
link the owning board contract for pins, voltage, clocks and reset behavior.
Do not promote a simulation or fit procedure into physical evidence.
