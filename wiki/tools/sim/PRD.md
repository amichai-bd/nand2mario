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

Verilator on WSL is the only supported simulator under the builder's
[simulator policy](../n2m/SPEC.md#simulator-policy); no license is consulted.
Both the normal and corrupt cases need actual simulator execution; the local
host tests prove only the host contract. Until the tile targets migrate, the
[SPEC](SPEC.md#simulator) names the unmigrated path they still use.
The [CI boundary](../n2m/SPEC.md#ci-execution-boundary) owns the outstanding trusted route.
