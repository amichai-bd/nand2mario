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

For the composed game, select the additive `v05-board` target and verify its
current fit, identity and UART crossing evidence. Its functional inputs have
physical pins; remaining virtual outputs are diagnostic only. The
[FPGA README](../../../../src/fpga/de10_lite/README.md) owns this distinction.
Use `quartus_pgm --help` from the installed Quartus directory to inspect actual
programming syntax; verified 25.1 help exposes cable, mode and operation options.
Help output is not evidence that a bitstream has been programmed. Keep concrete
programming commands and resulting device state in the physical run record.

Verified Quartus 25.1 volatile programming syntax is
`quartus_pgm -c <verified-cable> -m JTAG -o "P;<reviewed-sof>@<verified-device-index>"`.
Check the SOF hash against its producing evidence and verify the JTAG chain
before execution. Require zero exit status and affirmative configuration and
operation success messages; inspect errors and warnings. A host postprocessing
failure does not undo programming. Preserve the raw result and classify it
before deciding whether another hardware operation is necessary.

After programming, verify the wire build ID against the producing build. Then
use an immutable original software package for full upload/readback, loaded and
paused state, UART input writes, execution and snapshot checks. Compare pixels
with independent program expectations. Record diagnostic transport settings
separately; see the [UART timeout procedure](../../uart-host-tool/examples/scenarios.md#physical-timeout-diagnosis).

Verified CLI help: `python tools/build.py fpga build --help` describes building,
not programming; no FPGA programming subcommand exists. `host load --help`
requires an immutable `sw/build/<target>/runs/<attempt>/result.json` through
`--package`. `host status --help` exposes explicit UART port/VID/PID/identity
selection. These help checks do not prove programming or UART transmission.

Record subsequent tested tool/CLI/debug commands, tool versions and observed
pitfalls here or in a linked focused reference. Label untested steps as assumptions;
link the owning board contract for pins, voltage, clocks and reset behavior.
Do not promote a simulation or fit procedure into physical evidence.

Quartus 25.1 PLL generation on Windows can exit3 before HDL with a TBBmalloc
unknown `_msize` prologue diagnostic. Preserve the failure. Intel documents
[`TBB_MALLOC_DISABLE_REPLACEMENT=1`](https://www.intel.com/content/www/us/en/docs/onetbb/developer-guide-api-reference/2021-11/windows-os-c-c-dynamic-memory-interface.html)
to retain the standard allocator. A process-only setting was verified with
`python tools/build.py fpga build v05-board --quartus-bin <installed-bin> --timeout 600 --rebuild --tag <fresh-tag> --json`
under the existing 600-second supervisor and shared lock. Record the environment
override, restore it in `finally`, and require a fresh complete accepted fit.
This changes no DLL or security policy and does not relabel failed attempts.
