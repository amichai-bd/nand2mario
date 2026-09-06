# Intel memory primitives

Proposed under [#137](https://github.com/amichai-bd/nand2mario/issues/137).
All product RAM and ROM backing stores must use the explicit Intel `altsyncram`
boundary in [`n2m_intel_ram`](../../../../src/rtl/common/n2m_intel_ram.sv).
Questa compiles the installed Intel model for the same instance and parameters
used by MAX 10 synthesis. A behavioral replacement, stub or black box cannot
provide product-memory acceptance. Register files, peripheral state and small
control registers may remain flops; independent reference models may use arrays.

## Supported ports and timing

One narrow wrapper supports the current owners. Port A reads or writes;
port B only reads. A uses `clk_a`. B uses `clk_a` in single-clock mode and
`clk_b` in dual-clock mode. The unused primitive `clock1` is tied high in
single-clock mode, as required by its unused-port convention. The current width/lane configurations are 2/1,
8/1, 16/1 and 32/4. Depth and address width are explicit, and requests must
stay within the declared depth even when the address encoding has spare values.
The two-bit shape serves frame shades; byte stores serve system memory; the
32-bit shape proves the issue's four byte enables. This is not a mapper or
general memory-generator interface.

At an enabled port's rising edge, the primitive captures the address and read
control. Data becomes visible after that edge, before the next consuming edge.
`outdata_reg_a/b` are `UNREGISTERED`; the internal input/address stage still
makes the externally observed read synchronous. No second output stage is
permitted. Disabling a read retains the last read data and deasserts valid
after the next port edge. Before any initialized read the data is unspecified.
The wrapper's valid bits are ordinary shared-macro registers.

`reset_a/b` immediately mask the corresponding valid output and inhibit that
port's accesses; reset does not clear the array or data output. Each domain's
owner must release reset synchronously. Owners initialize through real clear
or load writes and prevent reads until their data is initialized. There is no
MIF/HEX input, portable branch, private vendor-array loading or fabricated
power-up fill. `power_up_uninitialized` is `TRUE`, and `init_file` is `UNUSED`.

## Writes and collisions

Enabled A writes update only enabled lanes. The single-lane configurations
enable the whole word; the sixteen-bit whole-word enable is replicated to the
primitive's two required eight-bit lanes. 32/4 maps lane zero to bits 7:0.
The two-bit whole-word enable gates physical write enable; its unused physical
byte-enable port is tied high because Intel byte sizes are eight or nine bits.
The primitive lane count is the width rounded up in units of eight bits, with
all B lanes tied enabled on its read-only port. A same-port simultaneous
read/write is supported only with all lanes enabled and returns the new word
at that edge. The primitive selects `NEW_DATA_NO_NBE_READ`; partial writes
must disable A reading and can be observed with a subsequent enabled read.
An assertion rejects partial-lane simultaneous read/write.

Cross-port read/write collisions are forbidden in both clock modes. The
primitive explicitly selects mixed-port `OLD_DATA`, matching the installed
model's MAX 10 family handling. This parameter does not authorize a collision
or promise a deterministic value for unrelated clocks. The wrapper checks at
both port clocks that an active A write
request and B read request do not target the same address. This deliberately
strong request-window rule is only a local diagnostic: owners must also enforce
bank/address ownership across unrelated clocks, including physical timing
windows. Simultaneous reads are allowed. There is no B write port.

The MAX 10 guide documents [read-enable holding](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/read-enable?contentId=LsRwx_P_1NO6gEMewkvOBQ),
[same-port new data](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/same-port-read-during-write-mode?contentId=mPC_Y0bBM58cJ0SN~2R3EA),
and [undefined mixed-port results with different clocks](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/mixed-port-read-during-write-operation-with-dual-clocks?contentId=qTPrC0GKoRk~icc6UE585A).
These document683431 sections were read at revision2025-12-15. Simulation data
alone does not establish collision safety or the fitted device configuration.

## Build and ownership

The [builder contract](../../../tools/n2m/SPEC.md) owns installed-model discovery,
hashes, compile options and explicit library binding. The authoritative version
and model source hash are in [the dependency record](../../../../tools/n2m/dependencies.json).
Vendor source remains in the licensed tool installation; compiled libraries and
evidence stay under the build tag. This foundation changes no Game Boy bus,
clock, host command or framebuffer ownership contract.

| Consumer | Required shape | Migration owner |
|---|---|---|
| System ROM/RAM | Single-clock A read/write and B read, one request edge | [#130](https://github.com/amichai-bd/nand2mario/issues/130); its earlier inferred-memory draft is not acceptance for this boundary. |
| VGA frame storage | Dual-clock A write and B read, two-bit shades, one request edge | [#138](https://github.com/amichai-bd/nand2mario/issues/138); current inferred frame arrays remain tracked migration debt. |
| Host snapshots | Frozen frame copy and host read service | [#93](https://github.com/amichai-bd/nand2mario/issues/93); consumer defines its ownership and port schedule before implementation. |

Independent wrapper fixtures must prove first/last addresses, enable holding,
defined writes and byte lanes, reset visibility and actual-port initialization.
Deliberate data/latency defects and prohibited collisions must fail with exact
nonzero diagnostics. A constrained MAX 10 target must retain actual primitive
parameters, block resources and timing; source arithmetic is not a resource proof.
