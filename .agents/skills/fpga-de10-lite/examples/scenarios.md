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

After programming, verify the wire build ID against the producing build. The
fit record's `build_id` is the 128-bit `N2M_V05_BUILD_ID` macro; `host status`
reports it as four little-endian 32-bit words, so the wire string is that hex
value with its byte order reversed (verified: fit `575c14f1…8d5802bb` answered
`bb02588d…f1145c57`). Declare the programmer's global restart on the first host
command with `--endpoint-restarted`; the shared sequence counter continues. Then
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
unknown `_msize` prologue diagnostic. The tooling owns the remedy: `fpga build`
and the doctor's Quartus check launch every Quartus process with the
[allocator override](../../../../wiki/tools/n2m/SPEC.md#quartus-allocator-override)
`TBB_MALLOC_DISABLE_REPLACEMENT=1`, record it in the result's `environment`, and
print one `notice:` line. Do not set the variable by hand and do not describe a
fit as needing it; if the signature still appears with a nonzero exit, preserve
the failure and report it. This changes no DLL or security policy and does not
relabel failed attempts.

## Package constants in Quartus 25.1

Quartus 25.1std.0 Build 1129 reported error10162 for selected package-qualified
constants in instance expressions and one continuous-assignment LHS array index,
although the affected Questa simulations passed. This is the observed tool
limitation, not a ban on package qualification. Keep the mandatory
[RTL reference style](../../../../wiki/src/rtl-reference-style.md).

Use a module-local constant initialized from the qualified owning package where
this limitation occurs. Preserve the original enum or integer type, width,
signedness and value; use the alias only at the affected expression. For example:

```systemverilog
localparam n2m_memory_pkg::memory_store_t OAM_STORE = n2m_memory_pkg::STORE_OAM;
```

Do not substitute numeric copies or restore wildcard imports. Review the alias
against the original binding, including uses introduced by macros. The verified
fix used eleven typed aliases across twelve affected sites;
[PR229](https://github.com/amichai-bd/nand2mario/pull/229) owns the failed attempts,
exact commands, versions and passing synthesis/simulation evidence. The subsequent
[board check](https://github.com/amichai-bd/nand2mario/issues/225#issuecomment-5588100639)
qualified the reviewed image through bounded original-program checks.

When changing these constructs in product RTL, run actual affected Quartus HDL
compilation and the existing target's required fit/timing checks before claiming
synthesis acceptance. A passing Questa check alone does not establish that proof.
Preserve failed attempts and qualify reuse by the changed inputs and behavior.
This requirement does not add a full fit to pure DV or documentation changes.
