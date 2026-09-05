# Unit simulation requirements

Provide reproducible evidence for the isolated
[display tile pixel unit](../../src/rtl/display/MAS_display.md), including normal
operation and detection of its deliberate corruption.

The [SPEC](SPEC.md) owns standalone runner behavior and shared builder usage,
including failure acceptance and retained artifacts. The
[ownership map](../../ownership.md) links host tests and the independent RTL
test plan. The [verification gap](../../preflight-gaps.md#gap-008-verification-baseline)
owns outstanding broader evidence; this unit does not establish a full PPU or
shared verification baseline.

Questa is the only supported simulator. Both the normal and corrupt cases need
actual licensed execution; hosted runner tests prove only the host contract.
The [CI boundary](../n2m/SPEC.md#ci-execution-boundary) owns the outstanding trusted route.
