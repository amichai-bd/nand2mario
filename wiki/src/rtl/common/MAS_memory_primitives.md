# Intel memory primitives

All product RAM and ROM backing stores must use the explicit Intel `altsyncram`
boundary in [`n2m_intel_ram`](../../../../src/rtl/common/n2m_intel_ram.sv).
The wrapper has two backing models behind one instance name and one set of
public ports:

- Synthesis model: Quartus always sees the vendor `altsyncram` instance and its
  parameters, in the wrapper's `else` branch.
- Simulation model: under the predefined `VERILATOR` macro the wrapper selects
  the repository double
  [`n2m_sim_dual_port_ram`](../../../../src/rtl/common/n2m_sim_dual_port_ram.sv),
  a separate source listed by each Verilator target. The double implements
  every rule on this page: one request edge of latency with unregistered
  output, per-lane enables for the supported shapes, `NEW_DATA_NO_NBE_READ`
  same-port behavior, `OLD_DATA` single-clock and unspecified dual-clock
  mixed-port behavior, seeded random power-up contents and `INIT_FILE`
  preload. It uses an `n2m_sim_` name; no repository HDL defines `altsyncram`.

[`tb_sim_ram_double`](../../../../src/dv/common/tb_sim_ram_double.sv) is the
double's unit test under the [common test plan](../../../../src/dv/common/README.md#intel-memory-doubles);
[`tb_intel_ram`](../../../../src/dv/common/tb_intel_ram.sv) is the wrapper
fixture. Verilator has no `X`: data the vendor leaves undefined comes from the
run's seeded random stream, so an uninitialized or forbidden read fails by value
mismatch, not by an `X` check. Four-state assertions in memory consumers are
removed during migration as an authorized behavior change. Register files,
peripheral state and small control registers may remain flops; independent
reference models may use arrays. Every SystemVerilog and Python target that
reaches the wrapper lists the double as a source and keeps its recorded
synthesis binding (`vendor_model: "intel-memory"` or `"intel-controls"`).
Targets that include `questa` in their capability list use the checked
installed Intel model and exact diagnostic inventory under the builder's
[simulator policy](../../../tools/n2m/SPEC.md#simulator-field).

## Supported ports and timing

One narrow wrapper supports the current owners. Port A reads or writes;
port B only reads. A uses `clk_a`. B uses `clk_a` in single-clock mode and
`clk_b` in dual-clock mode. The unused primitive `clock1` is tied high in
single-clock mode, as required by its unused-port convention. The current width/lane configurations are 1/1, 2/1,
8/1, 16/1 and 32/4. Depth and address width are explicit, and requests must
stay within the declared depth even when the address encoding has spare values.
The one-bit shape serves the UART ROM-presence bitmap; the two-bit shape serves
frame shades; byte stores serve system memory; the
32-bit shape provides four byte enables. This is not a mapper or
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
or load writes and prevent reads until their data is initialized. A store that
declares no image has `init_file=UNUSED` and `power_up_uninitialized=TRUE`, and
the double fills every word from `$urandom` at time zero.

`INIT_FILE` names one memory initialization file for both backing models, so one
declaration serves a simulation and a fit. It is a declared module parameter, not
access to vendor internals: the
[simulation preload](../../dv/preload/SPEC.md) sets it by `defparam` and a board
image names it on one store instance through its
[generated project](../../../tools/n2m/SPEC.md#carried-rom-image).
`power_up_uninitialized` follows from that declaration rather than being fixed:
`TRUE` with no file, `FALSE` with one, because a store that powers up
uninitialized cannot also power up holding a program. Both states are checked in
[the wrapper's own unit](../../../../src/dv/common/tb_sim_ram_double.sv) and in
fitted MAX 10 evidence, where Quartus states either the attribute or the
initialization: an initialized block carries `init_file`, `init_file_layout` and
its `mem_init` words and no `power_up_uninitialized`, and an uninitialized one
carries `power_up_uninitialized=true` and none of them. The double supports `.mif`
(the `DEPTH`/`WIDTH`/radix header and `address : value;` or
`[first..last] : value;` rows written by `tools/n2m/preload.py`) through its own
parser; any other name is read as plain `$readmemh` text, one hex word per
line, which is not the Intel HEX record format of a Quartus `.hex` file. Files
are read 1 ps after time zero so a testbench may write them at time zero. A missing file, a header that
disagrees with the instance shape or a malformed row is a named fatal failure.
Product owners still initialize through real writes; reset does not reload any
array.

## Writes and collisions

Enabled A writes update only enabled lanes. The single-lane configurations
enable the whole word; the sixteen-bit whole-word enable is replicated to the
primitive's two required eight-bit lanes. 32/4 maps lane zero to bits 7:0.
The one- and two-bit whole-word enables gate physical write enable; their unused physical
byte-enable port is tied high because Intel byte sizes are eight or nine bits.
The primitive lane count is the width rounded up in units of eight bits, with
all B lanes tied enabled on its read-only port. A same-port simultaneous
read/write is supported only with all lanes enabled and returns the new word
at that edge. The primitive selects `NEW_DATA_NO_NBE_READ`; the double returns
the enabled lanes as new data and unspecified masked lanes. Partial writes
must disable A reading and can be observed with a subsequent enabled read.
An assertion rejects partial-lane simultaneous read/write.

Cross-port read/write collisions are forbidden in both clock modes. The
primitive selects mixed-port `OLD_DATA` for one clock and `DONT_CARE` for
different clocks. The double returns the old word for a single-clock same-edge
collision and unspecified data when a dual-clock B read samples the address A
is writing. This parameter does not authorize a collision
or promise a deterministic value for unrelated clocks. The wrapper checks at
both port clocks that an active A write
request and B read request do not target the same address. This deliberately
strong request-window rule is only a local diagnostic: owners must also enforce
bank/address ownership across unrelated clocks, including physical timing
windows. Simultaneous reads are allowed. There is no B write port.

Hardware requires `DONT_CARE` for different clocks; Quartus critical warning
15003 remains a failure. Questa uses the checked installed model and classifies
its reviewed time-zero coercion diagnostic through the target's
`intel_mixed_mode_instances` inventory. A target may declare that inventory
only when its capability list includes Questa. Verilator ignores the inventory
and its double emits no coercion diagnostic. Both backends check the collision
rule through the wrapper's `INTEL_RAM_MIXED_PORT_A/B` assertions, which
`intel-memory-collision` witnesses.

The MAX 10 guide documents [read-enable holding](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/read-enable?contentId=LsRwx_P_1NO6gEMewkvOBQ),
[same-port new data](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/same-port-read-during-write-mode?contentId=mPC_Y0bBM58cJ0SN~2R3EA),
and [undefined mixed-port results with different clocks](https://docs.altera.com/r/docs/683431/current/max-10-embedded-memory-user-guide/mixed-port-read-during-write-operation-with-dual-clocks?contentId=qTPrC0GKoRk~icc6UE585A).
These document683431 sections were read at revision2025-12-15. Simulation data
alone does not establish collision safety or the fitted device configuration.

## Vendor family selection

The vendor instance names one device family and one block type, and they are the
only device-dependent values in the wrapper. MAX 10 is the default text: family
`MAX 10`, block `M9K`. A Cyclone V build defines `N2M_RAM_CYCLONEV`, and the
wrapper then states family `Cyclone V` and block `M10K`, because Cyclone V has no
M9K block and naming one there is a fitter substitution warning rather than a
placement. The selection is textual, so a MAX 10 build preprocesses to the same
tokens as before and nothing else in the wrapper changes. The
[builder contract](../../../tools/n2m/SPEC.md#de10-nano-uart-endpoint-image)
defines the macro from the target's board family, and the same contract keeps the
[accepted simulation-model requirement](../../../tools/n2m/SPEC.md#accepted-vendor-sources)
on every family but the one that compiles no simulation model.

## Build and ownership

The [builder contract](../../../tools/n2m/SPEC.md) owns simulation compile
options and the FPGA build. Vendor source stays in the Quartus installation;
the FPGA build records the installed `altsyncram` definition, declaration and
model hashes, and checks the model against the digest that installation
[has accepted](../../../tools/n2m/SPEC.md#accepted-vendor-sources); the licence and
originating installation stay in [the dependency record](../../../../tools/n2m/dependencies.json),
and evidence stays under the build tag. Selecting the double must not change
any FPGA target's resource summary or primitive hierarchy rows; that identity
is proved by rebuilding every target before and after a wrapper change with
`tools/fpga_netlist_compare.py`. This foundation changes no Game Boy bus,
clock, host command or framebuffer ownership contract.

| Consumer | Required shape | Implementation owner |
|---|---|---|
| System ROM/RAM | Single-clock A read/write and B read, one request edge | [Memory stores](../../../../src/rtl/memory/n2m_memory_stores.sv) |
| VGA frame storage | Dual-clock A write and B read, two-bit shades, one request edge | [Frame RAM](../../../../src/rtl/vga/n2m_frame_ram.sv) |
| Host snapshots | Frozen frame copy and host read service | [Snapshot storage](../../../../src/rtl/snapshot/n2m_frame_snapshot.sv) |

Independent wrapper fixtures must prove first/last addresses, enable holding,
defined writes and byte lanes, reset visibility and actual-port initialization.
Deliberate data/latency defects and prohibited collisions must fail with exact
nonzero diagnostics. A constrained MAX 10 target must retain actual primitive
parameters, block resources and timing; source arithmetic is not a resource proof.
